"""AI 客户端协议转换与模型校验单元测试。"""

import json

import pytest

from app.config import Settings
from app.services.ai_client import AIClient, AIClientError


def build_client(**overrides) -> AIClient:
    return AIClient(Settings(_env_file=None, **overrides))


def test_split_system_messages_merges_system_and_drops_unknown_role() -> None:
    system, converted = AIClient._split_system_messages(
        [
            {"role": "system", "content": "规则一"},
            {"role": "system", "content": "规则二"},
            {"role": "user", "content": "你好"},
            {"role": "tool", "content": "应被忽略"},
        ]
    )
    assert system == "规则一\n\n规则二"
    assert converted == [{"role": "user", "content": "你好"}]


def test_to_anthropic_content_builds_base64_image_block() -> None:
    blocks = AIClient._to_anthropic_content(
        [
            {"type": "text", "text": "看图"},
            {"type": "image", "media_type": "image/png", "data": "QUJD"},
        ],
        role="user",
    )
    assert blocks[0] == {"type": "text", "text": "看图"}
    assert blocks[1]["source"] == {
        "type": "base64",
        "media_type": "image/png",
        "data": "QUJD",
    }


def test_to_anthropic_content_keeps_assistant_text_only() -> None:
    content = AIClient._to_anthropic_content(
        [
            {"type": "text", "text": "历史回复"},
            {"type": "image", "media_type": "image/png", "data": "QUJD"},
        ],
        role="assistant",
    )
    assert content == "历史回复"


def test_to_openai_messages_converts_image_to_data_url() -> None:
    messages = AIClient._to_openai_messages(
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "看图"},
                    {"type": "image", "media_type": "image/png", "data": "QUJD"},
                ],
            }
        ]
    )
    parts = messages[0]["content"]
    assert parts[0] == {"type": "text", "text": "看图"}
    assert parts[1]["image_url"]["url"] == "data:image/png;base64,QUJD"


def test_extract_anthropic_text_reads_text_delta() -> None:
    data = json.dumps(
        {
            "type": "content_block_delta",
            "delta": {"type": "text_delta", "text": "你好"},
        }
    )
    assert AIClient._extract_anthropic_text(data) == "你好"


def test_extract_anthropic_text_ignores_non_delta_event() -> None:
    assert AIClient._extract_anthropic_text(json.dumps({"type": "message_start"})) is None


def test_extract_anthropic_text_ignores_invalid_json() -> None:
    assert AIClient._extract_anthropic_text("not-json") is None


def test_extract_anthropic_text_raises_on_error_event() -> None:
    data = json.dumps({"type": "error", "error": {"message": "额度不足"}})
    with pytest.raises(AIClientError):
        AIClient._extract_anthropic_text(data)


def test_resolve_model_rejects_model_outside_whitelist() -> None:
    client = build_client(ai_model="a", ai_models="a,b")
    with pytest.raises(AIClientError) as exc_info:
        client._resolve_model("c")
    assert exc_info.value.status_code == 400


def test_resolve_model_falls_back_to_default() -> None:
    client = build_client(ai_model="a", ai_models="a,b")
    assert client._resolve_model(None) == "a"
