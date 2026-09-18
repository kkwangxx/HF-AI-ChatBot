"""只读 SQL 校验。不信任模型生成的语句。"""

from __future__ import annotations

import re

_COMMENT_BLOCK = re.compile(r"/\*.*?\*/", re.DOTALL)
_COMMENT_LINE = re.compile(r"(--|#).*?$", re.MULTILINE)
_FORBIDDEN = re.compile(
    r"\b("
    r"insert|update|delete|drop|alter|truncate|create|grant|revoke|"
    r"replace|merge|call|execute|exec|into\s+outfile|load_file|"
    r"sleep|benchmark|for\s+update|lock\s+in\s+share\s+mode"
    r")\b",
    re.IGNORECASE,
)
_LEADING = re.compile(r"^(select|with)\b", re.IGNORECASE)
_LIMIT = re.compile(r"\blimit\s+\d+\b", re.IGNORECASE)

DEFAULT_LIMIT = 100


class SqlRejected(Exception):
    """SQL 未通过只读检查。"""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def strip_sql_comments(sql: str) -> str:
    without_block = _COMMENT_BLOCK.sub(" ", sql)
    return _COMMENT_LINE.sub(" ", without_block)


def validate_sql(sql: str, limit: int = DEFAULT_LIMIT) -> str:
    """返回可执行的单条 SELECT。危险语句直接拒绝。"""
    cleaned = strip_sql_comments(sql or "").strip().rstrip(";").strip()
    if not cleaned:
        raise SqlRejected("SQL 不能为空。")
    if ";" in cleaned:
        raise SqlRejected("不允许多条 SQL。")
    if not _LEADING.match(cleaned):
        raise SqlRejected("只允许 SELECT 查询。")
    if _FORBIDDEN.search(cleaned):
        raise SqlRejected("SQL 包含禁止的写入或危险关键字。")
    if not _LIMIT.search(cleaned):
        cleaned = f"{cleaned} LIMIT {limit}"
    return cleaned
