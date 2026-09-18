"""项目根目录与敏感文件判断。搜索和读文件共用，避免两套规则。"""

from __future__ import annotations

from pathlib import Path

SKIP_DIR_NAMES = frozenset(
    {
        ".git",
        ".idea",
        ".venv",
        ".svn",
        "node_modules",
        "target",
        "dist",
        "build",
        "unpackage",
        "logs",
        "xxljoblog",
        "__pycache__",
        "coverage",
        ".pytest_cache",
    }
)

CODE_SUFFIXES = frozenset(
    {
        ".java",
        ".xml",
        ".vue",
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
        ".sql",
        ".md",
        ".yml",
        ".yaml",
        ".html",
        ".scss",
        ".css",
        ".properties",
        ".json",
    }
)

SKIP_FILE_NAMES = frozenset(
    {
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
    }
)

_NAME_NEEDLES = (
    "secret",
    "password",
    "credential",
    "token",
    "api-key",
    "apikey",
    "id_rsa",
)


class PathRejected(Exception):
    """路径不在允许范围内，或命中敏感文件。"""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def is_sensitive_path(path: Path) -> bool:
    """拒绝密钥、环境文件和生产配置。这些文件里经常有数据库密码。"""
    name = path.name.lower()
    if name.startswith(".env"):
        return True
    if name.startswith("application-") and name.endswith((".yml", ".yaml", ".properties")):
        return True
    if name in {"application-prod.yml", "application-production.yml"}:
        return True
    if path.suffix.lower() in {".pem", ".key", ".p12", ".jks"}:
        return True
    return any(needle in name for needle in _NAME_NEEDLES)


def iter_code_files(root: Path):
    """遍历项目内源码文件，跳过依赖目录和敏感文件。"""
    if not root.is_dir():
        return
    for current, dir_names, file_names in root.walk():
        dir_names[:] = [name for name in dir_names if name not in SKIP_DIR_NAMES and name != ".git"]
        for file_name in file_names:
            if file_name in SKIP_FILE_NAMES:
                continue
            path = current / file_name
            if path.suffix.lower() not in CODE_SUFFIXES:
                continue
            if is_sensitive_path(path):
                continue
            yield path


def resolve_project_file(
    projects: list[tuple[str, Path]],
    path_text: str,
    project: str | None,
) -> tuple[str, Path]:
    """把模型给出的路径限制在已配置项目根内。"""
    if not projects:
        raise PathRejected("未配置 MOM_PROJECTS，不能读取代码。")
    raw = (path_text or "").strip()
    if not raw:
        raise PathRejected("文件路径不能为空。")

    candidates = projects
    if project:
        candidates = [item for item in projects if item[0] == project]
        if not candidates:
            raise PathRejected(f"未知项目：{project}")

    requested = Path(raw)
    if requested.is_absolute():
        resolved = requested.resolve()
        for name, root in candidates:
            root_resolved = root.resolve()
            if _within(resolved, root_resolved):
                _ensure_readable(resolved)
                return name, resolved
        raise PathRejected("路径超出已配置的项目目录。")

    matches: list[tuple[str, Path]] = []
    for name, root in candidates:
        root_resolved = root.resolve()
        resolved = (root_resolved / requested).resolve()
        if not _within(resolved, root_resolved):
            continue
        if resolved.is_file():
            _ensure_readable(resolved)
            matches.append((name, resolved))
    if not matches:
        raise PathRejected("文件不存在，或不在允许的项目目录内。")
    if len(matches) > 1:
        names = ", ".join(item[0] for item in matches)
        raise PathRejected(f"多个项目都有该文件，请指定 project。涉及：{names}")
    return matches[0]


def _within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return ".git" not in path.parts


def _ensure_readable(path: Path) -> None:
    if is_sensitive_path(path):
        raise PathRejected("该文件可能包含密钥，已拒绝读取。")
    if not path.is_file():
        raise PathRejected("文件不存在。")
