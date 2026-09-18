"""MOM 插件：知识、代码、只读数据库。项目列表全部来自配置。"""

from __future__ import annotations

from typing import Any

from app.agent.types import ToolSpec
from app.config import Settings
from app.plugins.mom.code_search import search_code
from app.plugins.mom.database import query_database
from app.plugins.mom.file_reader import read_code_file
from app.plugins.mom.knowledge import search_knowledge
from app.plugins.mom.sql_guard import SqlRejected, validate_sql

_QUERY = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "关键词，中英文均可"},
        "limit": {"type": "integer", "description": "返回条数，默认 5"},
    },
    "required": ["query"],
}


def _limit(value: Any, default: int, upper: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return min(max(number, 1), upper)


class MomPlugin:
    """第一个内置插件。其他系统仿照本类实现自己的 Plugin。"""

    name = "mom"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def available(self) -> bool:
        if self._settings.project_roots() or self._settings.db_configured():
            return True
        root = self._settings.knowledge_root()
        return root.is_dir() and any(root.rglob("*.md"))

    def tool_specs(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="search_business_knowledge",
                description="搜索业务流程、业务规则和术语。回答规则类问题前应先调用。",
                parameters=_QUERY,
            ),
            ToolSpec(
                name="search_operation_guide",
                description="搜索操作步骤，例如某个单据如何创建、投产、报工。",
                parameters=_QUERY,
            ),
            ToolSpec(
                name="search_code",
                description="在已配置的项目代码中搜索类名、方法、接口、错误提示、表名或中文关键词。",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "project": {"type": "string", "description": "项目标识，可空表示全部项目"},
                        "limit": {"type": "integer"},
                    },
                    "required": ["query"],
                },
            ),
            ToolSpec(
                name="read_code_file",
                description="读取搜索命中的源码文件。路径必须属于已配置项目，禁止读取密钥文件。",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "相对项目根的路径，或该根下的绝对路径"},
                        "project": {"type": "string"},
                        "start_line": {"type": "integer"},
                        "end_line": {"type": "integer"},
                    },
                    "required": ["path"],
                },
            ),
            ToolSpec(
                name="query_database",
                description="对业务库执行只读 SELECT。禁止任何写入。SQL 会在服务端再次校验。",
                parameters={
                    "type": "object",
                    "properties": {
                        "sql": {"type": "string", "description": "单条 SELECT，不要 SELECT * 大表全表扫描"},
                    },
                    "required": ["sql"],
                },
            ),
        ]

    def system_prompt(self) -> str:
        lines = ["已接入的代码项目（search_code / read_code_file 的 project 参数用左侧标识）："]
        projects = self._settings.project_roots()
        if projects:
            for name, path in projects:
                state = "目录存在" if path.is_dir() else "目录不存在"
                lines.append(f"- {name}: {path}（{state}）")
        else:
            lines.append("- 未配置项目，不要调用代码搜索或读文件。")
        if self._settings.db_configured():
            lines.append(
                "数据库已配置，库名="
                f"{self._settings.mom_db_name}，主机={self._settings.mom_db_host}。"
                "只能 SELECT。"
            )
        else:
            lines.append("数据库未配置，不要调用 query_database，也不要编造查询结果。")
        lines.append(f"知识库目录：{self._settings.knowledge_root()}")
        return "\n".join(lines)

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        projects = self._settings.project_roots()
        if name == "search_business_knowledge":
            return search_knowledge(
                self._settings.knowledge_root(),
                str(arguments.get("query") or ""),
                subdirs=["business", "rules", "glossary.md"],
                limit=_limit(arguments.get("limit"), 5, 8),
            )
        if name == "search_operation_guide":
            return search_knowledge(
                self._settings.knowledge_root(),
                str(arguments.get("query") or ""),
                subdirs=["operation"],
                limit=_limit(arguments.get("limit"), 5, 8),
            )
        if name == "search_code":
            return search_code(
                projects,
                str(arguments.get("query") or ""),
                project=_optional_text(arguments.get("project")),
                limit=_limit(arguments.get("limit"), 8, 15),
            )
        if name == "read_code_file":
            end_line = arguments.get("end_line")
            return read_code_file(
                projects,
                str(arguments.get("path") or ""),
                project=_optional_text(arguments.get("project")),
                start_line=_limit(arguments.get("start_line"), 1, 100000),
                end_line=int(end_line) if end_line not in (None, "") else None,
            )
        if name == "query_database":
            return self._query(str(arguments.get("sql") or ""))
        return {"success": False, "error": f"未知工具：{name}"}

    def _query(self, sql: str) -> dict[str, Any]:
        try:
            validate_sql(sql)
        except SqlRejected as exc:
            return {"success": False, "error": exc.message}
        return query_database(self._settings, sql)


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
