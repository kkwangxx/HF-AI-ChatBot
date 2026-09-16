# AI Chat Bot

基于 [One-Chat](https://github.com/ImMrShervin/One-Chat) UI 改造的 ChatGPT 风格聊天应用。  
后端使用 FastAPI，代理 OpenAI 兼容的流式 Chat Completions API。

## 技术栈

- Python 3.14+ / FastAPI / Uvicorn / httpx / pydantic-settings
- Jinja2 + 原生 HTML/CSS/JS（复用 One-Chat 布局与交互）
- marked + highlight.js（Markdown / 代码高亮）
- localStorage 持久化会话（一阶段无数据库）

## 快速开始

```bash
python -m venv .venv
# Windows
.\.venv\Scripts\activate
# Linux / macOS
# source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env   # Linux: cp .env.example .env
```

编辑 `.env`：

```env
AI_API_BASE_URL=https://apiclaude.cc
AI_API_KEY=你的密钥
AI_MODEL=claude-sonnet-5[1M]
AI_MODELS=claude-sonnet-5[1M],claude-opus-4-8[1M]
AI_API_PROTOCOL=anthropic
```

也可从当前 CC Switch（Claude）配置一键同步：

```bash
python scripts/sync_cc_switch_env.py
```

> Claude Code 走 Anthropic `/v1/messages`，因此 `AI_API_PROTOCOL` 需设为 `anthropic`。  
> 若你的供应商支持 OpenAI Chat Completions，可改为 `openai`。  
> WebUI 顶栏可切换 `AI_MODELS` 中的模型（仅切模型，不切供应商）。

启动：

```bash
uvicorn app.main:app --reload
# 或
python -m app.main
```

浏览器访问：

- 介绍页：<http://localhost:8000>
- 聊天页：<http://localhost:8000/chat>

## 本地 Mock AI（可选）

若暂时没有真实 AI 服务，可另开终端启动：

```bash
python scripts/mock_ai.py
```

默认监听 `http://127.0.0.1:8080`，与 `.env.example` 中的 `AI_API_BASE_URL` 一致。

## 项目结构

```text
app/
├── main.py                 # FastAPI 入口，渲染首页
├── config.py               # pydantic-settings 配置
├── api/chat.py             # POST /api/chat（SSE）
├── services/ai_client.py   # AI Client（唯一上游调用入口）
├── models/chat.py          # 请求模型
├── templates/index.html
└── static/
    ├── css/chat.css
    └── js/
        ├── chatStorage.js  # localStorage 抽象
        ├── sseClient.js    # SSE 解析
        ├── markdown.js
        └── app.js
```

## 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 产品介绍落地页 |
| GET | `/chat` | 聊天工作台 |
| POST | `/api/chat` | 流式对话（`text/event-stream`） |
| GET | `/api/models` | 可选模型列表 |

请求体：

```json
{
  "messages": [
    { "role": "user", "content": "你好" }
  ]
}
```

## 更换 AI API

只需修改 `.env` 中的：

- `AI_API_BASE_URL`
- `AI_API_KEY`
- `AI_MODEL`

或调整 `app/services/ai_client.py`。前端不接触 API Key。

## 模板来源

UI 参考并改造自：https://github.com/ImMrShervin/One-Chat  
主要改动：中文界面、经 FastAPI 代理 SSE、API Key 不下发浏览器、会话按今天/昨天分组、`chatStorage.js` / `sseClient.js` 职责拆分。
