"""按行读取已配置项目中的源码文件。"""

from __future__ import annotations

from pathlib import Path

from app.plugins.mom.paths import PathRejected, resolve_project_file

_MAX_LINES = 200


def read_code_file(
    projects: list[tuple[str, Path]],
    path: str,
    *,
    project: str | None = None,
    start_line: int = 1,
    end_line: int | None = None,
) -> dict:
    try:
        project_name, file_path = resolve_project_file(projects, path, project)
    except PathRejected as exc:
        return {"success": False, "error": exc.message}

    start = max(1, start_line)
    stop = start + _MAX_LINES - 1 if end_line is None else end_line
    if stop < start:
        return {"success": False, "error": "end_line 不能小于 start_line"}
    if stop - start + 1 > _MAX_LINES:
        stop = start + _MAX_LINES - 1

    lines: list[str] = []
    try:
        with file_path.open("r", encoding="utf-8", errors="replace") as handle:
            for line_no, line in enumerate(handle, start=1):
                if line_no < start:
                    continue
                if line_no > stop:
                    break
                lines.append(line.rstrip("\n"))
    except OSError as exc:
        return {"success": False, "error": f"读取失败：{exc}"}

    root = next(root for name, root in projects if name == project_name)
    return {
        "success": True,
        "project": project_name,
        "file": file_path.resolve().relative_to(root.resolve()).as_posix(),
        "start_line": start,
        "end_line": start + len(lines) - 1 if lines else start,
        "content": "\n".join(lines),
    }
