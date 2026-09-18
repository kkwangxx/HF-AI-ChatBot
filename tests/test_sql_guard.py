"""SQL 只读校验。"""

import pytest

from app.plugins.mom.sql_guard import SqlRejected, validate_sql


def test_validate_sql_appends_limit() -> None:
    assert validate_sql("SELECT id FROM work_order") == (
        "SELECT id FROM work_order LIMIT 100"
    )


def test_validate_sql_keeps_existing_limit() -> None:
    sql = "SELECT id FROM work_order LIMIT 10"
    assert validate_sql(sql) == sql


def test_validate_sql_allows_with_query() -> None:
    sql = validate_sql("WITH t AS (SELECT 1 AS id) SELECT id FROM t")
    assert sql.endswith("LIMIT 100")


def test_validate_sql_rejects_multiple_statements() -> None:
    with pytest.raises(SqlRejected):
        validate_sql("SELECT 1; DELETE FROM work_order")


def test_validate_sql_rejects_write_hidden_in_comment() -> None:
    with pytest.raises(SqlRejected):
        validate_sql("SELECT 1; /* */ DELETE FROM work_order")


def test_validate_sql_strips_comment_then_rejects_keyword() -> None:
    with pytest.raises(SqlRejected):
        validate_sql("/* ok */ UPDATE work_order SET status = 1")


def test_validate_sql_rejects_into_outfile() -> None:
    with pytest.raises(SqlRejected):
        validate_sql("SELECT id FROM work_order INTO OUTFILE '/tmp/x'")


def test_validate_sql_rejects_for_update() -> None:
    with pytest.raises(SqlRejected):
        validate_sql("SELECT id FROM work_order FOR UPDATE")
