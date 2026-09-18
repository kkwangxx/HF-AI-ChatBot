"""在已配置的项目根里做关键词代码搜索。"""

from __future__ import annotations

from pathlib import Path

from app.plugins.mom.paths import iter_code_files

_MAX_FILE_BYTES = 1024 * 1024
_MAX_LINE_CHARS = 300


def search_code(
    projects: list[tuple[str, Path]],
    query: str,
    *,
    project: str | None = None,
    limit: int = 8,
) -> dict:
    text = (query or "").strip()
    if not text:
        return {"success": False, "error": "query 不能为空"}
    if not projects:
        return {"success": False, "error": "未配置 MOM_PROJECTS，不能搜索代码。"}

    roots = projects
    if project:
        roots = [item for item in projects if item[0] == project]
        if not roots:
            return {"success": False, "error": f"未知项目：{project}"}

    missing = [name for name, root in roots if not root.is_dir()]
    needles = [part.lower() for part in text.split() if part.strip()] or [text.lower()]
    results: list[dict] = []
    for name, root in roots:
        if not root.is_dir():
            continue
        for path in iter_code_files(root):
            match = _first_match(path, needles)
            if match is None:
                continue
            line_no, line = match
            results.append(
                {
                    "project": name,
                    "file": path.resolve().relative_to(root.resolve()).as_posix(),
                    "line": line_no,
                    "content": line,
                }
            )
            if len(results) >= limit:
                return _ok(results, missing)
    return _ok(results, missing)


def _ok(results: list[dict], missing: list[str]) -> dict:
    messages: list[str] = []
    if missing:
        messages.append(f"以下项目目录不存在，已跳过：{', '.join(missing)}")
    if not results:
        messages.append("没有找到匹配代码。不要据此编造实现位置。")
    payload: dict = {"success": True, "results": results}
    if messages:
        payload["message"] = " ".join(messages)
    return payload


def _first_match(path: Path, needles: list[str]) -> tuple[int, str] | None:
    try:
        if path.stat().st_size > _MAX_FILE_BYTES:
            return None
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line_no, line in enumerate(handle, start=1):
                if line_no == 1 and "\x00" in line:
                    return None
                lowered = line.lower()
                if any(needle in lowered for needle in needles):
                    return line_no, line.strip()[:_MAX_LINE_CHARS]
                if line_no >= 20000:
                    break
    except OSError:
        return None
    return None
