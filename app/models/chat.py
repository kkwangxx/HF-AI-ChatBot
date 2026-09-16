"""聊天相关请求 / 响应模型。"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, field_validator, model_validator


class TextContentPart(BaseModel):
    """文本内容块。"""

    type: Literal["text"] = "text"
    text: str = Field(..., min_length=1)


class ImageContentPart(BaseModel):
    """图片内容块（base64，不含 data: 前缀）。"""

    type: Literal["image"] = "image"
    media_type: str = Field(..., description="如 image/png")
    data: str = Field(..., min_length=1, description="纯 base64 数据")
    name: str | None = None

    @field_validator("media_type")
    @classmethod
    def validate_media_type(cls, value: str) -> str:
        allowed = {"image/jpeg", "image/png", "image/gif", "image/webp"}
        normalized = value.lower().strip()
        if normalized not in allowed:
            raise ValueError(f"不支持的图片类型：{value}")
        return normalized


class DocumentContentPart(BaseModel):
    """文档内容块（当前支持 PDF base64）。"""

    type: Literal["document"] = "document"
    media_type: str = Field(default="application/pdf")
    data: str = Field(..., min_length=1)
    name: str | None = None

    @field_validator("media_type")
    @classmethod
    def validate_media_type(cls, value: str) -> str:
        normalized = value.lower().strip()
        if normalized != "application/pdf":
            raise ValueError("文档目前仅支持 application/pdf")
        return normalized


ContentPart = Annotated[
    Union[TextContentPart, ImageContentPart, DocumentContentPart],
    Field(discriminator="type"),
]


class ChatMessage(BaseModel):
    """单条对话消息。content 可为纯文本或多模态内容块列表。"""

    role: Literal["system", "user", "assistant"]
    content: str | list[ContentPart]

    @model_validator(mode="after")
    def validate_content_not_empty(self) -> ChatMessage:
        if isinstance(self.content, str):
            if not self.content.strip():
                raise ValueError("消息内容不能为空")
            return self
        if not self.content:
            raise ValueError("消息内容不能为空")
        return self


class ChatRequest(BaseModel):
    """前端发起的聊天请求。"""

    messages: list[ChatMessage] = Field(..., min_length=1)
    model: str | None = Field(default=None, description="可选，覆盖默认模型")


class ModelsResponse(BaseModel):
    """可选模型列表。"""

    default: str
    models: list[str]
