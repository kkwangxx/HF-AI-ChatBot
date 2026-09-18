"""AI 服务客户端封装。"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.agent.parse import (
    AnthropicToolStreamParser,
    OpenAIToolStreamParser,
    StreamParseError,
)
from app.agent.types import ToolSpec
from app.config import Settings


class AIClientError(Exception):
    """AI API 调用失败。"""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class AIClient:
    """调用上游 AI，并统一产出 OpenAI 风格 SSE data 载荷。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base_url = settings.ai_api_base_url.rstrip("/")
        self._api_key = settings.ai_api_key
        self._model = settings.ai_model
        self._protocol = settings.ai_api_protocol
        self._max_tokens = settings.ai_max_tokens
        self._timeout = settings.ai_timeout_seconds

    def _openai_headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def _anthropic_headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "anthropic-version": "2023-06-01",
        }
        if self._api_key:
            # 官方用 x-api-key；多数中转站同时认 Bearer
            headers["x-api-key"] = self._api_key
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    @staticmethod
    def _friendly_http_error(status_code: int, body: str) -> str:
        hints = {
            400: "请求参数有误，请检查消息内容后重试。",
            401: "AI 服务鉴权失败，请检查 API Key 配置。",
            403: "没有权限访问该 AI 服务。",
            404: "AI 接口地址不存在，请检查 AI_API_BASE_URL。",
            429: "请求过于频繁，请稍后再试。",
            500: "AI 服务内部错误，请稍后再试。",
            502: "AI 服务网关错误，请稍后再试。",
            503: "AI 服务暂时不可用，请稍后再试。",
        }
        hint = hints.get(status_code, f"AI 服务返回错误（HTTP {status_code}）。")
        detail = body.strip().replace("\n", " ")[:200]
        if detail:
            return f"{hint} 详情：{detail}"
        return hint

    @staticmethod
    def _friendly_network_error(exc: Exception) -> str:
        text = str(exc).lower()
        if "connect" in text or "refused" in text:
            return "无法连接 AI 服务，请确认服务已启动且地址正确。"
        if "timeout" in text or "timed out" in text:
            return "连接 AI 服务超时，请稍后重试。"
        if "reset" in text:
            return "与 AI 服务的连接被重置，请重试。"
        return f"网络异常：{exc}"

    @staticmethod
    def _to_openai_delta(text: str) -> str:
        return json.dumps(
            {"choices": [{"delta": {"content": text}, "index": 0}]},
            ensure_ascii=False,
        )

    @staticmethod
    def _split_system_messages(
        messages: list[dict[str, Any]],
    ) -> tuple[str | None, list[dict[str, Any]]]:
        system_parts: list[str] = []
        converted: list[dict[str, Any]] = []
        for message in messages:
            role = message.get("role")
            content = message.get("content")
            if role == "system":
                text = AIClient._content_as_plain_text(content)
                if text:
                    system_parts.append(text)
                continue
            if role not in {"user", "assistant"}:
                continue
            converted.append(
                {
                    "role": role,
                    "content": AIClient._to_anthropic_content(content, role=role),
                }
            )
        system = "\n\n".join(system_parts) if system_parts else None
        return system, converted

    @staticmethod
    def _content_as_plain_text(content: Any) -> str:
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text = str(item.get("text") or "").strip()
                    if text:
                        parts.append(text)
            return "\n".join(parts)
        return ""

    @staticmethod
    def _to_anthropic_content(content: Any, role: str) -> str | list[dict[str, Any]]:
        """将前端 content 转为 Anthropic Messages 格式。"""
        if isinstance(content, str):
            return content
        if not isinstance(content, list):
            return str(content or "")

        # assistant 侧历史只保留文本，避免无效图片回传
        if role == "assistant":
            text = AIClient._content_as_plain_text(content)
            return text or ""

        blocks: list[dict[str, Any]] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            part_type = item.get("type")
            if part_type == "text":
                text = str(item.get("text") or "")
                if text:
                    blocks.append({"type": "text", "text": text})
            elif part_type == "image":
                media_type = str(item.get("media_type") or "")
                data = str(item.get("data") or "")
                if media_type and data:
                    blocks.append(
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": data,
                            },
                        }
                    )
            elif part_type == "document":
                media_type = str(item.get("media_type") or "application/pdf")
                data = str(item.get("data") or "")
                if data:
                    blocks.append(
                        {
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": data,
                            },
                        }
                    )
        if not blocks:
            return ""
        if len(blocks) == 1 and blocks[0].get("type") == "text":
            return blocks[0]["text"]
        return blocks

    @staticmethod
    def _to_openai_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """将前端 content 转为 OpenAI Chat Completions 多模态格式。"""
        result: list[dict[str, Any]] = []
        for message in messages:
            role = message.get("role")
            content = message.get("content")
            if role not in {"system", "user", "assistant"}:
                continue
            if isinstance(content, str) or role != "user":
                result.append(
                    {
                        "role": role,
                        "content": AIClient._content_as_plain_text(content)
                        if not isinstance(content, str)
                        else content,
                    }
                )
                continue

            parts: list[dict[str, Any]] = []
            for item in content if isinstance(content, list) else []:
                if not isinstance(item, dict):
                    continue
                part_type = item.get("type")
                if part_type == "text":
                    text = str(item.get("text") or "")
                    if text:
                        parts.append({"type": "text", "text": text})
                elif part_type == "image":
                    media_type = str(item.get("media_type") or "")
                    data = str(item.get("data") or "")
                    if media_type and data:
                        parts.append(
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{media_type};base64,{data}",
                                },
                            }
                        )
                elif part_type == "document":
                    # OpenAI chat 不统一支持 PDF block，降级为说明文本
                    name = item.get("name") or "document.pdf"
                    parts.append(
                        {
                            "type": "text",
                            "text": f"[已附加 PDF 文件：{name}，当前 OpenAI 兼容模式无法直接解析 PDF]",
                        }
                    )
            if not parts:
                continue
            if len(parts) == 1 and parts[0].get("type") == "text":
                result.append({"role": role, "content": parts[0]["text"]})
            else:
                result.append({"role": role, "content": parts})
        return result

    def _resolve_model(self, model: str | None) -> str:
        allowed = set(self._settings.model_list())
        if model and model.strip():
            name = model.strip()
            if allowed and name not in allowed:
                raise AIClientError(
                    f"不支持的模型：{name}。可选：{', '.join(self._settings.model_list())}",
                    status_code=400,
                )
            return name
        return self._model

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
    ) -> AsyncIterator[str]:
        """流式调用上游 AI，逐段产出 OpenAI 风格 JSON 字符串。"""
        resolved = self._resolve_model(model)
        if self._protocol == "anthropic":
            async for chunk in self._stream_anthropic(messages, resolved):
                yield chunk
            return
        async for chunk in self._stream_openai(messages, resolved):
            yield chunk

    async def _stream_openai(
        self,
        messages: list[dict[str, Any]],
        model: str,
    ) -> AsyncIterator[str]:
        url = f"{self._base_url}/v1/chat/completions"
        payload: dict[str, Any] = {
            "model": model,
            "messages": self._to_openai_messages(messages),
            "stream": True,
        }
        async for data in self._iter_sse_data(url, self._openai_headers(), payload):
            if data == "[DONE]":
                break
            yield data

    async def _stream_anthropic(
        self,
        messages: list[dict[str, Any]],
        model: str,
    ) -> AsyncIterator[str]:
        url = f"{self._base_url}/v1/messages"
        system, converted = self._split_system_messages(messages)
        if not converted:
            raise AIClientError("消息列表为空，无法调用 AI。", status_code=400)

        payload: dict[str, Any] = {
            "model": model,
            "messages": converted,
            "max_tokens": self._max_tokens,
            "stream": True,
        }
        if system:
            payload["system"] = system

        async for data in self._iter_sse_data(url, self._anthropic_headers(), payload):
            if data == "[DONE]":
                break
            text = self._extract_anthropic_text(data)
            if text:
                yield self._to_openai_delta(text)

    @staticmethod
    def _extract_anthropic_text(data: str) -> str | None:
        try:
            event = json.loads(data)
        except json.JSONDecodeError:
            return None

        event_type = event.get("type")
        if event_type == "content_block_delta":
            delta = event.get("delta") or {}
            if delta.get("type") == "text_delta":
                text = delta.get("text")
                return text if isinstance(text, str) and text else None
        if event_type == "error":
            err = event.get("error") or {}
            message = err.get("message") or data
            raise AIClientError(f"AI 服务返回错误：{message}")
        return None

    async def _iter_sse_data(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> AsyncIterator[str]:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                async with client.stream(
                    "POST",
                    url,
                    headers=headers,
                    json=payload,
                ) as response:
                    if response.status_code >= 400:
                        body = (await response.aread()).decode("utf-8", errors="replace")
                        raise AIClientError(
                            self._friendly_http_error(response.status_code, body),
                            status_code=response.status_code,
                        )

                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        if line.startswith("event:"):
                            continue
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if not data:
                            continue
                        yield data
        except AIClientError:
            raise
        except httpx.TimeoutException as exc:
            raise AIClientError(self._friendly_network_error(exc)) from exc
        except httpx.HTTPError as exc:
            raise AIClientError(self._friendly_network_error(exc)) from exc

    async def stream_with_tools(
        self,
        messages: list[dict[str, Any]],
        model: str | None,
        tools: list[ToolSpec],
    ) -> AsyncIterator[tuple[str, Any]]:
        """流式产出 ('text', 片段)，结束时产出 ('done', tool_calls)。"""
        resolved = self._resolve_model(model)
        if self._protocol == "anthropic":
            parser: OpenAIToolStreamParser | AnthropicToolStreamParser = (
                AnthropicToolStreamParser()
            )
            url = f"{self._base_url}/v1/messages"
            headers = self._anthropic_headers()
            payload = self._anthropic_tool_payload(messages, resolved, tools)
        else:
            parser = OpenAIToolStreamParser()
            url = f"{self._base_url}/v1/chat/completions"
            headers = self._openai_headers()
            payload = self._openai_tool_payload(messages, resolved, tools)

        try:
            async for data in self._iter_sse_data(url, headers, payload):
                try:
                    text = parser.feed(data)
                except StreamParseError as exc:
                    raise AIClientError(exc.message) from exc
                if text:
                    yield ("text", text)
        except AIClientError:
            raise
        yield ("done", parser.finish())

    def _openai_tool_payload(
        self,
        messages: list[dict[str, Any]],
        model: str,
        tools: list[ToolSpec],
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": self._agent_openai_messages(messages),
            "stream": True,
        }
        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    },
                }
                for tool in tools
            ]
            payload["tool_choice"] = "auto"
        return payload

    def _anthropic_tool_payload(
        self,
        messages: list[dict[str, Any]],
        model: str,
        tools: list[ToolSpec],
    ) -> dict[str, Any]:
        system, converted = self._agent_anthropic_messages(messages)
        if not converted:
            raise AIClientError("消息列表为空，无法调用 AI。", status_code=400)
        payload: dict[str, Any] = {
            "model": model,
            "messages": converted,
            "max_tokens": self._max_tokens,
            "stream": True,
        }
        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.parameters,
                }
                for tool in tools
            ]
        return payload

    def _agent_openai_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        pending: list[dict[str, Any]] = []
        result: list[dict[str, Any]] = []
        for message in messages:
            role = message.get("role")
            if role == "tool" or (role == "assistant" and message.get("tool_calls")):
                if pending:
                    result.extend(self._to_openai_messages(pending))
                    pending = []
                if role == "tool":
                    result.append(
                        {
                            "role": "tool",
                            "tool_call_id": message.get("tool_call_id"),
                            "content": str(message.get("content") or ""),
                        }
                    )
                else:
                    result.append(self._openai_assistant_tool_message(message))
                continue
            pending.append(message)
        if pending:
            result.extend(self._to_openai_messages(pending))
        return result

    @staticmethod
    def _openai_assistant_tool_message(message: dict[str, Any]) -> dict[str, Any]:
        tool_calls = []
        for call in message.get("tool_calls") or []:
            arguments = call.get("arguments")
            if not isinstance(arguments, str):
                arguments = json.dumps(arguments or {}, ensure_ascii=False)
            tool_calls.append(
                {
                    "id": call.get("id"),
                    "type": "function",
                    "function": {
                        "name": call.get("name"),
                        "arguments": arguments,
                    },
                }
            )
        return {
            "role": "assistant",
            "content": message.get("content") or "",
            "tool_calls": tool_calls,
        }

    def _agent_anthropic_messages(
        self,
        messages: list[dict[str, Any]],
    ) -> tuple[str | None, list[dict[str, Any]]]:
        system_parts: list[str] = []
        converted: list[dict[str, Any]] = []
        tool_results: list[dict[str, Any]] = []

        def flush_tool_results() -> None:
            if tool_results:
                converted.append({"role": "user", "content": list(tool_results)})
                tool_results.clear()

        for message in messages:
            role = message.get("role")
            if role == "system":
                text = self._content_as_plain_text(message.get("content"))
                if text:
                    system_parts.append(text)
                continue
            if role == "tool":
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": message.get("tool_call_id"),
                        "content": str(message.get("content") or ""),
                    }
                )
                continue
            flush_tool_results()
            if role == "assistant" and message.get("tool_calls"):
                blocks: list[dict[str, Any]] = []
                content = message.get("content")
                if isinstance(content, str) and content:
                    blocks.append({"type": "text", "text": content})
                for call in message.get("tool_calls") or []:
                    blocks.append(
                        {
                            "type": "tool_use",
                            "id": call.get("id"),
                            "name": call.get("name"),
                            "input": call.get("arguments") or {},
                        }
                    )
                if blocks:
                    converted.append({"role": "assistant", "content": blocks})
                continue
            if role == "user":
                converted.append(
                    {
                        "role": "user",
                        "content": self._to_anthropic_content(
                            message.get("content"),
                            role="user",
                        ),
                    }
                )
        flush_tool_results()
        system = "\n\n".join(system_parts) if system_parts else None
        return system, converted
