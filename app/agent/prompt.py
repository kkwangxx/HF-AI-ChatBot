"""MOM Agent 系统提示词。具体项目信息由插件追加，不写死路径。"""

from __future__ import annotations

from typing import Any

BASE_PROMPT = """你是 MOM 系统智能助手。

你的任务是帮助用户理解所接入业务系统的：
1. 业务流程
2. 操作步骤
3. 操作结果
4. 业务规则
5. 系统校验
6. 代码实现
7. 当前业务数据

回答问题时优先使用工具获取真实信息。
不要凭经验猜测业务规则。
如果业务文档和代码存在冲突，优先指出冲突，并分别说明来源。
如果无法找到依据，明确告诉用户无法从当前资料中确认，不要把猜测说成事实。
回答普通业务用户时优先使用业务语言，不要大量展示代码。
用户明确询问代码时，可以展示相关代码、类、方法和文件位置。
涉及代码规则、校验、系统行为或数据结果时，尽量说明依据来自哪份文档、哪个文件、哪个方法。
查询数据库时只能使用只读查询，不要执行任何修改数据的操作。
没有配置对应工具或工具返回未配置时，不要编造查询结果。
"""


def format_context(context: dict[str, Any] | None) -> str:
    """把宿主传入的页面上下文写成提示词。没有上下文时明确说没有。"""
    if not context:
        return "当前没有页面或业务对象上下文。不要假设用户正在看哪张单据。"

    lines = ["当前宿主上下文："]
    page = context.get("page") or {}
    if isinstance(page, dict) and any(page.get(key) for key in ("module", "menu", "page")):
        lines.append(
            "页面：模块={module}，菜单={menu}，页面={page}".format(
                module=page.get("module") or "未知",
                menu=page.get("menu") or "未知",
                page=page.get("page") or "未知",
            )
        )
    business = context.get("business") or {}
    if isinstance(business, dict) and any(business.get(key) for key in ("type", "id", "code")):
        lines.append(
            "业务对象：类型={type}，id={id}，单号={code}".format(
                type=business.get("type") or "未知",
                id=business.get("id") or "未知",
                code=business.get("code") or "未知",
            )
        )
    if len(lines) == 1:
        return "当前没有页面或业务对象上下文。不要假设用户正在看哪张单据。"
    lines.append("用户询问“这个单据 / 当前页面”时，优先使用以上上下文，不要再向用户索要已经给出的单号。")
    return "\n".join(lines)
