"""代码搜索、读文件与知识检索。使用临时目录，不碰真实项目。"""

from pathlib import Path

from app.plugins.mom.code_search import search_code
from app.plugins.mom.file_reader import read_code_file
from app.plugins.mom.knowledge import search_knowledge
from app.plugins.mom.paths import is_sensitive_path


def test_sensitive_path_blocks_env_and_profile(tmp_path: Path) -> None:
    assert is_sensitive_path(tmp_path / ".env")
    assert is_sensitive_path(tmp_path / ".env.production")
    assert is_sensitive_path(tmp_path / "application-dev.yml")
    assert is_sensitive_path(tmp_path / "application-prod.yml")
    assert not is_sensitive_path(tmp_path / "WorkOrderService.java")


def test_search_code_finds_line_and_skips_secret_file(tmp_path: Path) -> None:
    source = tmp_path / "src" / "WorkOrderService.java"
    source.parent.mkdir()
    source.write_text("class WorkOrderService {\n  // 报工数量不能超过工单数量\n}\n", encoding="utf-8")
    secret = tmp_path / "application-dev.yml"
    secret.write_text("password: 报工数量\n", encoding="utf-8")

    result = search_code([("backend", tmp_path)], "报工数量")
    assert result["success"] is True
    assert len(result["results"]) == 1
    assert result["results"][0]["file"] == "src/WorkOrderService.java"
    assert result["results"][0]["line"] == 2


def test_search_code_skips_node_modules(tmp_path: Path) -> None:
    skipped = tmp_path / "node_modules" / "lib.js"
    skipped.parent.mkdir()
    skipped.write_text("hiddenKeyword\n", encoding="utf-8")
    result = search_code([("ui", tmp_path)], "hiddenKeyword")
    assert result["results"] == []


def test_read_code_file_rejects_path_escape(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    outside = tmp_path / "outside.java"
    outside.write_text("secret\n", encoding="utf-8")
    result = read_code_file([("backend", root)], str(outside))
    assert result["success"] is False


def test_read_code_file_rejects_env_file(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("AI_API_KEY=abc\n", encoding="utf-8")
    result = read_code_file([("backend", tmp_path)], ".env")
    assert result["success"] is False


def test_read_code_file_returns_line_range(tmp_path: Path) -> None:
    source = tmp_path / "A.java"
    source.write_text("one\ntwo\nthree\n", encoding="utf-8")
    result = read_code_file([("backend", tmp_path)], "A.java", start_line=2, end_line=2)
    assert result["success"] is True
    assert result["content"] == "two"
    assert result["project"] == "backend"


def test_search_knowledge_returns_matching_document(tmp_path: Path) -> None:
    doc = tmp_path / "operation" / "report.md"
    doc.parent.mkdir()
    doc.write_text("# 报工\n\n进入生产管理后点击报工。\n", encoding="utf-8")
    result = search_knowledge(tmp_path, "报工", subdirs=["operation"])
    assert result["documents"][0]["title"] == "报工"
    assert "点击报工" in result["documents"][0]["content"]


def test_search_knowledge_empty_means_unknown(tmp_path: Path) -> None:
    result = search_knowledge(tmp_path, "不存在的规则")
    assert result["documents"] == []
    assert "不要" in result["message"]
