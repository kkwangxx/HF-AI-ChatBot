"""知识库关键词检索。不做向量，只扫 Markdown。"""

from __future__ import annotations

from pathlib import Path


def search_knowledge(
    root: Path,
    query: str,
    *,
    subdirs: list[str] | None = None,
    limit: int = 5,
) -> dict:
    """在知识目录中按关键词找文档。找不到时明确返回空列表。"""
    text = (query or "").strip()
    if not text:
        return {"success": False, "error": "query 不能为空"}
    if not root.is_dir():
        return {
            "success": True,
            "documents": [],
            "message": "知识目录不存在，无法确认该问题。不要编造业务规则。",
        }

    files = _collect_files(root, subdirs)
    fallback = False
    if subdirs and not files:
        files = _collect_files(root, None)
        fallback = True

    needles = [part.lower() for part in text.split() if part.strip()] or [text.lower()]
    scored: list[tuple[int, Path, str]] = []
    for path in files:
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        haystack = f"{path.name}\n{content}".lower()
        score = sum(haystack.count(needle) for needle in needles)
        if score <= 0:
            continue
        scored.append((score, path, content))

    scored.sort(key=lambda item: item[0], reverse=True)
    documents = [
        {
            "title": _title(path, content),
            "path": _relative(root, path),
            "content": _snippet(content, needles),
        }
        for _, path, content in scored[:limit]
    ]
    result: dict = {"success": True, "documents": documents}
    if not documents:
        result["message"] = "知识库中没有匹配文档。不要据此编造规则。"
    elif fallback:
        result["message"] = "指定分类下没有文档，已退回整个知识库检索。"
    return result


def _collect_files(root: Path, subdirs: list[str] | None) -> list[Path]:
    if not subdirs:
        return sorted(path for path in root.rglob("*.md") if path.is_file())
    found: list[Path] = []
    for name in subdirs:
        target = root / name
        if target.is_file() and target.suffix.lower() == ".md":
            found.append(target)
        elif target.is_dir():
            found.extend(path for path in target.rglob("*.md") if path.is_file())
    return found


def _title(path: Path, content: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip() or path.stem
    return path.stem


def _relative(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.name


def _snippet(content: str, needles: list[str], width: int = 700) -> str:
    lower = content.lower()
    index = -1
    for needle in needles:
        index = lower.find(needle)
        if index >= 0:
            break
    if index < 0:
        return content[:width]
    start = max(0, index - 120)
    return content[start : start + width].strip()
