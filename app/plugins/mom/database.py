"""MySQL 只读查询。连接池复用，不在每次查询时新建连接。"""

from __future__ import annotations

import logging
import queue
import threading
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import pymysql
from pymysql.cursors import DictCursor

from app.config import Settings
from app.plugins.mom.sql_guard import SqlRejected, validate_sql

logger = logging.getLogger(__name__)

_POOL_SIZE = 3
_pool: "ConnectionPool | None" = None
_pool_lock = threading.Lock()


def query_database(settings: Settings, sql: str) -> dict[str, Any]:
    """执行已通过校验的 SELECT。未配置或失败时返回结构化错误，不抛给聊天层。"""
    if not settings.db_configured():
        return {
            "success": False,
            "error": "未配置 MOM 数据库。请设置 MOM_DB_HOST、MOM_DB_NAME、MOM_DB_USER。",
        }
    try:
        checked = validate_sql(sql)
    except SqlRejected as exc:
        logger.info("[Agent] SQL rejected: %s", exc.message)
        return {"success": False, "error": exc.message}

    logger.info("[Agent] SQL: %s", checked[:500])
    try:
        rows = _get_pool(settings).query(checked)
    except pymysql.Error as exc:
        logger.error("数据库查询失败，原因：%s", exc)
        return {"success": False, "error": "数据库查询失败，请检查 SQL 或连接配置。"}
    return {
        "success": True,
        "row_count": len(rows),
        "rows": rows,
        "sql": checked,
    }


class ConnectionPool:
    """固定大小的连接池。借出失败或断开时丢弃并补建。"""

    def __init__(self, settings: Settings, size: int = _POOL_SIZE) -> None:
        self._settings = settings
        self._size = size
        self._idle: queue.Queue[Any] = queue.Queue(maxsize=size)
        self._created = 0
        self._lock = threading.Lock()

    def query(self, sql: str) -> list[dict[str, Any]]:
        connection = self._acquire()
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql)
                rows = cursor.fetchmany(100)
            return [_jsonable_row(row) for row in rows]
        except pymysql.Error:
            self._discard(connection)
            connection = None
            raise
        finally:
            if connection is not None:
                self._release(connection)

    def _acquire(self) -> Any:
        try:
            return self._idle.get_nowait()
        except queue.Empty:
            with self._lock:
                if self._created < self._size:
                    self._created += 1
                    return self._connect()
        return self._idle.get(timeout=10)

    def _release(self, connection: Any) -> None:
        try:
            connection.ping(reconnect=True)
            self._idle.put_nowait(connection)
        except Exception:  # noqa: BLE001
            self._discard(connection)

    def _discard(self, connection: Any) -> None:
        try:
            connection.close()
        except Exception:  # noqa: BLE001
            pass
        with self._lock:
            self._created = max(0, self._created - 1)

    def _connect(self) -> Any:
        return pymysql.connect(
            host=self._settings.mom_db_host,
            port=self._settings.mom_db_port,
            user=self._settings.mom_db_user,
            password=self._settings.mom_db_password,
            database=self._settings.mom_db_name,
            charset="utf8mb4",
            cursorclass=DictCursor,
            connect_timeout=5,
            read_timeout=30,
            autocommit=True,
        )


def _get_pool(settings: Settings) -> ConnectionPool:
    global _pool
    with _pool_lock:
        if _pool is None:
            _pool = ConnectionPool(settings)
        return _pool


def _jsonable_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: _jsonable(value) for key, value in row.items()}


def _jsonable(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value
