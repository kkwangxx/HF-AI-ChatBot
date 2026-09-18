"""Agent 循环。没有可用插件时退回原来的流式聊天。"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from app.agent.prompt import BASE_PROMPT, format_context
from app.agent.registry import ToolRegistry
from app.agent.types import ToolCall
from app.config import Settings
from app.plugins.loader import load_plugins
from app.services.ai_client import AIClient, AIClientError

logger = logging.getLogger(__name__)

_MAX_TOOL_CHARS = 12000


async def stream_reply(
    client: AIClient,
    settings: Settings,
    messages: list[dict[str, Any]],
    model: str | None,
    context: dict[str, Any] | None = None,
    registry: ToolRegistry | None = None,
) -> AsyncIterator[str]:
    """产出与 chat_stream 相同的 OpenAI delta JSON。工具状态用 agent 事件，旧前端会忽略。"""
    tools_registry = registry if registry is not None else load_plugins(settings)
    specs = tools_registry.tool_specs()
    if not specs:
        async for chunk in client.chat_stream(messages, model=model):
            yield chunk
        return

    question = _last_user_text(messages)
    logger.info("[Agent] User question: %s", question[:300])
    conversation: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": "\n\n".join(
                part
                for part in (
                    BASE_PROMPT.strip(),
                    tools_registry.system_prompt(),
                    format_context(context),
                )
                if part
            ),
        },
        *messages,
    ]

    max_rounds = max(2, settings.agent_max_rounds)
    for round_index in range(max_rounds):
        allow_tools = round_index < max_rounds - 1
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        try:
            async for kind, payload in client.stream_with_tools(
                conversation,
                model,
                specs if allow_tools else [],
            ):
                if kind == "text":
                    text_parts.append(str(payload))
                    yield AIClient._to_openai_delta(str(payload))
                elif kind == "done":
                    tool_calls = list(payload)
        except AIClientError as exc:
            if round_index == 0 and not text_parts:
                logger.warning("工具调用不可用，回退普通对话：%s", exc.message)
                async for chunk in client.chat_stream(messages, model=model):
                    yield chunk
                return
            raise

        if not tool_calls:
            logger.info("[Agent] Final answer generated")
            if not text_parts:
                yield AIClient._to_openai_delta("模型没有返回内容，请重试。")
            return

        answer = "".join(text_parts)
        conversation.append(
            {
                "role": "assistant",
                "content": answer,
                "tool_calls": [
                    {"id": call.id, "name": call.name, "arguments": call.arguments}
                    for call in tool_calls
                ],
            }
        )
        for call in tool_calls:
            logger.info("[Agent] Tool: %s", call.name)
            yield _agent_event(call.name, "start")
            result = tools_registry.call(call.name, call.arguments)
            logger.info("[Agent] Result: %s", _summarize(result))
            conversation.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "name": call.name,
                    "content": _dump_result(result),
                }
            )
            yield _agent_event(call.name, "done")


def _agent_event(name: str, status: str) -> str:
    return json.dumps(
        {"agent": {"tool": name, "status": status}},
        ensure_ascii=False,
    )


def _dump_result(result: dict[str, Any]) -> str:
    text = json.dumps(result, ensure_ascii=False, default=str)
    if len(text) <= _MAX_TOOL_CHARS:
        return text
    return text[:_MAX_TOOL_CHARS] + "...(truncated)"


def _summarize(result: dict[str, Any]) -> str:
    if result.get("documents") is not None:
        return f"{len(result['documents'])} documents"
    if result.get("results") is not None:
        return f"{len(result['results'])} files"
    if result.get("row_count") is not None:
        return f"{result['row_count']} rows"
    if result.get("file"):
        return str(result["file"])
    if result.get("error"):
        return f"error={result['error']}"
    return "ok" if result.get("success") else "failed"


def _last_user_text(messages: list[dict[str, Any]]) -> str:
    for message in reversed(messages):
        if message.get("role") != "user":
            continue
        return AIClient._content_as_plain_text(message.get("content"))
    return ""
