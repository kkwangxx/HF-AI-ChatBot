# MOM 接入说明

本文说明安亿美 MOM 如何使用本服务的 Agent。密钥只留在本服务，MOM 前端不要接触上游 API Key，也不要自己调用模型。

## 1. 现在已经接上的部分

代码目录和数据库通过环境变量配置，不写死在代码里，也不写入仓库。实际路径和库账号只放在本地 `.env`。

因此，配好之后在本服务聊天页直接提问，Agent 就可以搜索已配置的代码、只读查询数据库。这一步不需要改 MOM。

配置格式：

```env
AGENT_ENABLED=true
AGENT_MAX_ROUNDS=6
MOM_PROJECTS=backend=D:/mom/server;api=D:/mom/api;app=D:/mom/app;ui=D:/mom/ui
MOM_KNOWLEDGE_ROOT=mom_knowledge
MOM_DB_HOST=
MOM_DB_PORT=3306
MOM_DB_NAME=
MOM_DB_USER=
MOM_DB_PASSWORD=
```

`MOM_PROJECTS` 用分号分隔，每项是 `标识=绝对路径`。`MOM_DB_HOST` 留空则不启用数据库工具。`AGENT_ENABLED=false` 时恢复纯聊天。

## 2. 页面助手怎么接

用户正开着某张单据时，MOM 必须把当前页面传过来。否则用户问“为什么不能报工”，Agent 不知道是哪一张工单。

调用方是 MOM 的 Web 或 App，协议是 HTTP，不是在 MOM 里再嵌一套模型。

### 2.1 先登录

`/chat` 和全部 `/api/*` 需要登录。默认账号在 `.env` 的 `AUTH_USERNAME` / `AUTH_PASSWORD`，初始值为 `admin / admin`。

```http
POST /login
Content-Type: application/x-www-form-urlencoded

username=admin&password=admin&next=/chat
```

成功返回 `303`，并写入 HttpOnly Cookie `chat_session`。之后请求都带上这个 Cookie。

未登录时：

- 打开页面会 `303` 到 `/login?next=...`
- 调接口返回 `401`，正文为 `{"error":{"message":"登录已失效，请重新登录。"}}`

### 2.2 发对话

```http
POST /api/chat
Content-Type: application/json
Accept: text/event-stream
Cookie: chat_session=...
```

```json
{
  "messages": [
    { "role": "user", "content": "为什么不能报工？" }
  ],
  "model": "可选，不传用服务端默认模型",
  "context": {
    "page": {
      "module": "生产管理",
      "menu": "生产工单",
      "page": "工单详情"
    },
    "business": {
      "type": "WORK_ORDER",
      "id": "单据主键",
      "code": "WO20260918001"
    }
  }
}
```

`messages` 至少一条。`context` 整个可以不传，字段也都可以空。有上下文时，用户说“这个单据”就按 `business.code` 理解，不要再让用户重复报单号。

`page.module`、`page.menu`、`page.page` 用 MOM 菜单上的中文名。`business.type` 用稳定的业务类型，例如 `WORK_ORDER`，不要用会变的页面标题。

多轮对话由 MOM 自己带上历史 `messages`。本服务不存会话，现有聊天页的历史在浏览器 `localStorage`。

### 2.3 读 SSE

响应类型是 `text/event-stream`。只认下面两种数据：

```text
data: {"choices":[{"delta":{"content":"文本片段"},"index":0}]}

data: [DONE]
```

把每个 `delta.content` 追加到当前回复。遇到 `[DONE]` 结束。

出错也在流里，不靠中途改 HTTP 状态码：

```text
data: {"error":{"message":"错误说明","status_code":401}}

data: [DONE]
```

工具执行时可能插入 `{"agent":{"tool":"search_code","status":"start"}}`。旧页面会忽略它。MOM 若要显示“正在查代码”，可以识别 `agent.tool`，不要把它当成回答正文。

解析可以参照 `app/static/js/sseClient.js`。

### 2.4 不要跨域直连

本服务当前没有开 CORS。MOM 页面和本服务不是同一个源时，浏览器会拦住 `fetch`，Cookie 也带不过来。

上线时用反向代理，把 `/login`、`/api`、`/chat` 挂到 MOM 的同一域名下。不要把本服务单独暴露到公网。它代理的是上游 API Key，未设强密码时等于把 Key 交出去。

服务默认只监听 `127.0.0.1`。

## 3. Agent 会用哪些工具

模型自己决定调用哪些工具，不是每个问题都查代码。

| 工具 | 用途 |
|------|------|
| `search_operation_guide` | 操作步骤，读 `mom_knowledge/operation/` |
| `search_business_knowledge` | 流程、规则、术语，读 `business/`、`rules/`、`glossary.md` |
| `search_code` | 在 `MOM_PROJECTS` 里搜类名、接口、报错文案、表名 |
| `read_code_file` | 读取搜到的源码，不能超出已配置目录 |
| `query_database` | 只读 `SELECT`，服务端会再校验 |

限制：

- 最多 `AGENT_MAX_ROUNDS` 轮，默认 6。
- SQL 只允许单条 `SELECT`。注释、多语句、`INSERT` / `UPDATE` / `DELETE` / `DROP` 等会被拒绝，并自动补 `LIMIT 100`。
- 不读取 `.env`、`application-*.yml`、密钥文件，避免把数据库密码送给模型。
- 工具失败不会让聊天接口崩溃，模型会拿到结构化错误。
- 知识、代码、数据库都没有依据时，必须回答无法确认，不能编造规则。

## 4. 业务文档怎么补

代码和数据库回答不了操作路径、流程说明。这类内容写在 `mom_knowledge/`，格式见 [mom_knowledge/README.md](../mom_knowledge/README.md)。

```text
mom_knowledge/
├── business/      业务流程
├── operation/     操作步骤
├── rules/         业务规则
└── glossary.md    术语
```

每个文件用 Markdown，第一行是标题。只写已经确认的规则，并注明来源。不要把大段源码复制进来，实现以仓库为准。

目录目前只有说明，没有业务正文。补文档之前，操作类问题会回答“资料不足”。

## 5. 要加 MOM 自己的工具

扫描代码和只读 SQL 不够时，在本服务里加插件，不要改 Agent 循环，也不要在 MOM 前端调模型。

实现 `app/agent/registry.py` 中的四个成员：

- `name`：插件名
- `tool_specs()`：工具名、说明、JSON Schema
- `system_prompt()`：给模型的项目说明，禁止写密码
- `call(name, arguments)`：返回 `{"success": true, ...}` 或 `{"success": false, "error": "..."}`

然后在 `app/plugins/loader.py` 的 `load_plugins()` 里 `registry.register(...)`。工具名不能和现有工具重复。

现有实现可参考 `app/plugins/mom/plugin.py`。

## 6. 建议的落地顺序

1. 先用本服务聊天页验证代码搜索和数据库查询。
2. 把已确认的操作步骤、流程、规则补进 `mom_knowledge/`。
3. MOM 用反向代理接到同一域名，登录后调用 `/api/chat`。
4. 在工单、报工、领料等详情页带上 `context`。
5. 需要实时单据状态时，优先让模型调用 `query_database`，用 `context.business.code` 作为条件，而不是把整张单据塞进前端请求。
