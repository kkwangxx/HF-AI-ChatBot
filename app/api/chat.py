"""聊天 API：SSE 流式代理上游 AI。"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.agent.runner import stream_reply
from app.config import get_settings
from app.models.chat import ChatRequest, ModelsResponse
from app.services.ai_client import AIClient, AIClientError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])


def _sse(data: str) -> str:
    return f"data: {data}\n\n"


@router.get("/models", response_model=ModelsResponse)
async def list_models() -> ModelsResponse:
    """返回当前供应商下可选模型列表。"""
    settings = get_settings()
    models = settings.model_list()
    return ModelsResponse(default=settings.ai_model, models=models)


@router.post("/chat")
async def chat(request: Request, body: ChatRequest) -> StreamingResponse:
    """接收多轮 messages，以 SSE 转发上游 AI 流式结果。"""
    settings = get_settings()
    client = AIClient(settings)
    messages = [m.model_dump(exclude_none=True) for m in body.messages]
    model = body.model.strip() if body.model else None
    context = body.context.model_dump(exclude_none=True) if body.context else None

    logger.info(
        "收到聊天请求，message_count=%s, model=%s",
        len(messages),
        model or settings.ai_model,
    )

    async def event_generator() -> AsyncIterator[str]:
        try:
            async for chunk in stream_reply(
                client,
                settings,
                messages,
                model,
                context,
            ):
                if await request.is_disconnected():
                    logger.info("客户端已断开，停止转发 SSE")
                    break
                yield _sse(chunk)
            yield _sse("[DONE]")
        except AIClientError as exc:
            logger.error(
                "AI 调用失败，status=%s, reason=%s",
                exc.status_code,
                exc.message,
            )
            payload = json.dumps(
                {
                    "error": {
                        "message": exc.message,
                        "status_code": exc.status_code,
                    }
                },
                ensure_ascii=False,
            )
            yield _sse(payload)
            yield _sse("[DONE]")
        except Exception as exc:  # noqa: BLE001
            logger.error("SSE 转发异常：%s", exc, exc_info=True)
            payload = json.dumps(
                {"error": {"message": "服务内部错误，请稍后重试。"}},
                ensure_ascii=False,
            )
            yield _sse(payload)
            yield _sse("[DONE]")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
