"""流式工具调用解析，不访问网络。"""

import json

import pytest

from app.agent.parse import (
    AnthropicToolStreamParser,
    OpenAIToolStreamParser,
    StreamParseError,
)
from app.agent.types import ToolCall


def test_openai_parser_joins_tool_call_fragments() -> None:
    parser = OpenAIToolStreamParser()
    first = {
        "choices": [
            {
                "delta": {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call_1",
                            "function": {"name": "search_code", "arguments": ""},
                        }
                    ]
                }
            }
        ]
    }
    second = {
        "choices": [
            {
                "delta": {
                    "tool_calls": [
                        {"index": 0, "function": {"arguments": '{"query":"报工"}'}}
                    ]
                },
                "finish_reason": "tool_calls",
            }
        ]
    }
    assert parser.feed(json.dumps(first)) is None
    assert parser.feed(json.dumps(second)) is None
    calls = parser.finish()
    assert calls == [ToolCall(id="call_1", name="search_code", arguments={"query": "报工"})]


def test_openai_parser_returns_text() -> None:
    parser = OpenAIToolStreamParser()
    data = json.dumps({"choices": [{"delta": {"content": "你好"}, "index": 0}]})
    assert parser.feed(data) == "你好"


def test_anthropic_parser_reads_tool_use() -> None:
    parser = AnthropicToolStreamParser()
    start = {
        "type": "content_block_start",
        "index": 0,
        "content_block": {"type": "tool_use", "id": "toolu_1", "name": "query_database"},
    }
    delta = {
        "type": "content_block_delta",
        "index": 0,
        "delta": {"type": "input_json_delta", "partial_json": '{"sql":"SELECT 1"}'},
    }
    assert parser.feed(json.dumps(start)) is None
    assert parser.feed(json.dumps(delta)) is None
    assert parser.feed(json.dumps({"type": "message_delta", "delta": {"stop_reason": "tool_use"}})) is None
    calls = parser.finish()
    assert calls[0].name == "query_database"
    assert calls[0].arguments == {"sql": "SELECT 1"}


def test_anthropic_parser_raises_on_error_event() -> None:
    parser = AnthropicToolStreamParser()
    with pytest.raises(StreamParseError):
        parser.feed(json.dumps({"type": "error", "error": {"message": "bad"}}))
