"""Agent 与插件共用的数据结构。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolSpec:
    """一个可被模型调用的工具。parameters 为 JSON Schema。"""

    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class ToolCall:
    """模型决定调用的一次工具。"""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class StreamParseState:
    """流式解析过程中累积的文本与工具调用。"""

    text_parts: list[str] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)
