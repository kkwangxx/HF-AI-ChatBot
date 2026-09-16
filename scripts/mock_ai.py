"""本地 Mock AI：OpenAI 兼容流式 /v1/chat/completions，便于联调。"""

from __future__ import annotations

import asyncio
import json

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI(title="Mock AI")


@app.post("/v1/chat/completions", response_model=None)
async def chat_completions(request: Request):
    body = await request.json()
    messages = body.get("messages") or []
    last = messages[-1]["content"] if messages else ""
    stream = bool(body.get("stream"))

    # 多轮演示：记住名字
    name = None
    for m in messages:
        if m.get("role") == "user" and "名字叫" in m.get("content", ""):
            name = m["content"].split("名字叫")[-1].strip(" 。.!！")
            break

    if "叫什么" in last and name:
        reply = f"你的名字是{name}。"
    elif "```" in last or "代码" in last or "python" in last.lower() or "java" in last.lower():
        reply = (
            "好的，这是一个示例：\n\n"
            "```python\n"
            "def hello(name: str) -> str:\n"
            "    return f\"Hello, {name}!\"\n"
            "\n"
            "print(hello(\"World\"))\n"
            "```\n\n"
            "以及表格：\n\n"
            "| 语言 | 用途 |\n"
            "|---|---|\n"
            "| Python | 脚本 / AI |\n"
            "| Java | 后端服务 |\n"
        )
    else:
        reply = f"你好！我收到了：{last}\n\n这是 **Markdown** 回复，支持列表：\n\n- 流式输出\n- 多轮上下文\n- 代码高亮"

    if not stream:
        return JSONResponse(
            {
                "choices": [
                    {"message": {"role": "assistant", "content": reply}},
                ]
            }
        )

    async def event_stream():
        for ch in reply:
            if await request.is_disconnected():
                break
            chunk = {
                "choices": [
                    {"delta": {"content": ch}, "index": 0},
                ]
            }
            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.015)
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8080)
