"""Agent 循环：无插件走原聊天，有插件时执行工具再继续。"""

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from app.agent.registry import ToolRegistry
from app.agent.runner import stream_reply
from app.agent.types import ToolCall, ToolSpec
from app.config import Settings
from app.services.ai_client import AIClient, AIClientError


class EchoPlugin:
    name = "echo"

    def tool_specs(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="echo",
                description="echo",
                parameters={"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]},
            )
        ]

    def system_prompt(self) -> str:
        return "echo"

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return {"success": True, "echo": arguments.get("q")}


class ScriptedClient:
    def __init__(self, rounds: list[list[tuple[str, Any]]]) -> None:
        self.rounds = rounds
        self.index = 0
        self.plain = False

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
    ) -> AsyncIterator[str]:
        self.plain = True
        yield AIClient._to_openai_delta("plain")

    async def stream_with_tools(
        self,
        messages: list[dict[str, Any]],
        model: str | None,
        tools: list[ToolSpec],
    ) -> AsyncIterator[tuple[str, Any]]:
        events = self.rounds[self.index]
        self.index += 1
        for event in events:
            yield event


def build_settings() -> Settings:
    return Settings(
        _env_file=None,
        auth_secret_key="x",
        agent_enabled=True,
        agent_max_rounds=4,
        ai_model="m",
    )


def _collect(source: AsyncIterator[str]) -> list[str]:
    async def _run() -> list[str]:
        return [chunk async for chunk in source]

    return asyncio.run(_run())


def test_stream_reply_without_tools_uses_plain_chat() -> None:
    client = ScriptedClient([])
    chunks = _collect(
        stream_reply(
            client,  # type: ignore[arg-type]
            build_settings(),
            [{"role": "user", "content": "你好"}],
            None,
            registry=ToolRegistry(),
        )
    )
    assert client.plain is True
    assert "plain" in chunks[0]


def test_stream_reply_runs_tool_then_answers() -> None:
    client = ScriptedClient(
        [
            [
                ("text", "先查一下"),
                (
                    "done",
                    [ToolCall(id="call_1", name="echo", arguments={"q": "工单"})],
                ),
            ],
            [("text", "查完了"), ("done", [])],
        ]
    )
    registry = ToolRegistry()
    registry.register(EchoPlugin())
    chunks = _collect(
        stream_reply(
            client,  # type: ignore[arg-type]
            build_settings(),
            [{"role": "user", "content": "这个工单呢"}],
            None,
            context={"business": {"type": "WORK_ORDER", "code": "WO1"}},
            registry=registry,
        )
    )
    text = "".join(chunks)
    assert "先查一下" in text
    assert "查完了" in text
    assert "echo" in text


def test_stream_reply_falls_back_when_tools_rejected() -> None:
    class FailingClient(ScriptedClient):
        async def stream_with_tools(self, messages, model, tools):  # type: ignore[no-untyped-def]
            raise AIClientError("tools unsupported", status_code=400)
            yield ("done", [])  # pragma: no cover

    client = FailingClient([])
    registry = ToolRegistry()
    registry.register(EchoPlugin())
    chunks = _collect(
        stream_reply(
            client,  # type: ignore[arg-type]
            build_settings(),
            [{"role": "user", "content": "你好"}],
            None,
            registry=registry,
        )
    )
    assert client.plain is True
    assert "plain" in chunks[0]
