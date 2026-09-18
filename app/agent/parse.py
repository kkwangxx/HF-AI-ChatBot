"""把上游 SSE 解析成文本增量或工具调用。不发起网络请求。"""

from __future__ import annotations

import json
from typing import Any

from app.agent.types import ToolCall


class StreamParseError(Exception):
    """上游在流里返回了错误事件。"""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _loads_object(raw: str) -> dict[str, Any]:
    if not raw or not raw.strip():
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {"_raw": raw}
    if isinstance(value, dict):
        return value
    return {"value": value}


class OpenAIToolStreamParser:
    """解析 OpenAI Chat Completions 流，含 tool_calls 分片。"""

    def __init__(self) -> None:
        self._slots: dict[int, dict[str, str]] = {}
        self._finished = False
        self.tool_calls: list[ToolCall] = []

    def feed(self, data: str) -> str | None:
        if data == "[DONE]":
            self.finish()
            return None
        try:
            event = json.loads(data)
        except json.JSONDecodeError:
            return None
        if not isinstance(event, dict):
            return None
        error = event.get("error")
        if isinstance(error, dict) and error.get("message"):
            raise StreamParseError(str(error["message"]))

        choices = event.get("choices") or []
        if not choices or not isinstance(choices[0], dict):
            return None
        choice = choices[0]
        delta = choice.get("delta") or {}
        if not isinstance(delta, dict):
            delta = {}
        for call in delta.get("tool_calls") or []:
            if isinstance(call, dict):
                self._merge(call)
        if choice.get("finish_reason"):
            self.finish()
        text = delta.get("content")
        return text if isinstance(text, str) and text else None

    def finish(self) -> list[ToolCall]:
        if self._finished:
            return self.tool_calls
        self._finished = True
        for index in sorted(self._slots):
            slot = self._slots[index]
            name = slot["name"].strip()
            if not name:
                continue
            self.tool_calls.append(
                ToolCall(
                    id=slot["id"] or f"call_{index}",
                    name=name,
                    arguments=_loads_object(slot["arguments"]),
                )
            )
        return self.tool_calls

    def _merge(self, call: dict[str, Any]) -> None:
        index = int(call.get("index") or 0)
        slot = self._slots.setdefault(index, {"id": "", "name": "", "arguments": ""})
        if call.get("id"):
            slot["id"] = str(call["id"])
        function = call.get("function") or {}
        if isinstance(function, dict):
            if function.get("name"):
                slot["name"] += str(function["name"])
            if function.get("arguments"):
                slot["arguments"] += str(function["arguments"])


class AnthropicToolStreamParser:
    """解析 Anthropic Messages 流，含 text_delta 与 tool_use。"""

    def __init__(self) -> None:
        self._blocks: dict[int, dict[str, str]] = {}
        self._finished = False
        self.tool_calls: list[ToolCall] = []

    def feed(self, data: str) -> str | None:
        if data == "[DONE]":
            self.finish()
            return None
        try:
            event = json.loads(data)
        except json.JSONDecodeError:
            return None
        if not isinstance(event, dict):
            return None

        event_type = event.get("type")
        if event_type == "error":
            err = event.get("error") or {}
            message = err.get("message") if isinstance(err, dict) else data
            raise StreamParseError(str(message or "AI 服务返回错误"))

        if event_type == "content_block_start":
            self._start_block(event)
            return None
        if event_type == "content_block_delta":
            return self._delta(event)
        if event_type in {"message_delta", "message_stop"}:
            self.finish()
        return None

    def finish(self) -> list[ToolCall]:
        if self._finished:
            return self.tool_calls
        self._finished = True
        for index in sorted(self._blocks):
            block = self._blocks[index]
            if block["type"] != "tool_use" or not block["name"]:
                continue
            self.tool_calls.append(
                ToolCall(
                    id=block["id"] or f"toolu_{index}",
                    name=block["name"],
                    arguments=_loads_object(block["json"]),
                )
            )
        return self.tool_calls

    def _start_block(self, event: dict[str, Any]) -> None:
        index = int(event.get("index") or 0)
        content = event.get("content_block") or {}
        if not isinstance(content, dict):
            return
        self._blocks[index] = {
            "type": str(content.get("type") or ""),
            "id": str(content.get("id") or ""),
            "name": str(content.get("name") or ""),
            "json": "",
        }

    def _delta(self, event: dict[str, Any]) -> str | None:
        index = int(event.get("index") or 0)
        delta = event.get("delta") or {}
        if not isinstance(delta, dict):
            return None
        delta_type = delta.get("type")
        if delta_type == "text_delta":
            text = delta.get("text")
            return text if isinstance(text, str) and text else None
        if delta_type == "input_json_delta":
            block = self._blocks.setdefault(
                index,
                {"type": "tool_use", "id": "", "name": "", "json": ""},
            )
            block["json"] += str(delta.get("partial_json") or "")
        return None
