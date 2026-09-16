"""读取 CC Switch / Claude / Codex 配置（脱敏），输出到文件。"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path


def mask(value: object) -> str:
    text = "" if value is None else str(value)
    if not text:
        return ""
    if len(text) <= 8:
        return "****"
    return f"{text[:4]}...{text[-4:]}"


def main() -> None:
    lines: list[str] = []

    settings_path = Path.home() / ".claude" / "settings.json"
    lines.append("=== .claude/settings.json ===")
    if settings_path.exists():
        data = json.loads(settings_path.read_text(encoding="utf-8"))
        env = data.get("env") or {}
        for key, value in env.items():
            if any(x in key.upper() for x in ("KEY", "TOKEN", "SECRET", "PASSWORD")):
                lines.append(f"{key}={mask(value)}")
            else:
                lines.append(f"{key}={value}")
        for key, value in data.items():
            if key == "env":
                continue
            dumped = json.dumps(value, ensure_ascii=False)
            lines.append(f"top.{key}={dumped[:300]}")
    else:
        lines.append("missing")

    codex_path = Path.home() / ".codex" / "config.toml"
    lines.append("=== .codex/config.toml ===")
    if codex_path.exists():
        for line in codex_path.read_text(encoding="utf-8").splitlines():
            if re.search(r"(key|token|secret|password)", line, re.I) and "=" in line:
                left, right = line.split("=", 1)
                lines.append(f"{left.strip()}={mask(right.strip().strip('\"'))}")
            else:
                lines.append(line)
    else:
        lines.append("missing")

    db_path = Path.home() / ".cc-switch" / "cc-switch.db"
    lines.append("=== cc-switch.db ===")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    tables = [
        row[0]
        for row in cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
    ]
    lines.append("tables=" + ", ".join(tables))

    for table in tables:
        cols = [row[1] for row in cur.execute(f"PRAGMA table_info({table})")]
        lines.append(f"-- {table} cols={cols}")
        try:
            rows = list(cur.execute(f"SELECT * FROM {table} LIMIT 50"))
        except sqlite3.Error as exc:
            lines.append(f"query_error={exc}")
            continue
        for row in rows:
            item = dict(zip(cols, row, strict=False))
            sanitized: dict[str, object] = {}
            for key, value in item.items():
                key_l = key.lower()
                if any(x in key_l for x in ("key", "token", "secret", "password", "auth")):
                    # settings JSON 可能内含密钥
                    if isinstance(value, str) and value.strip().startswith("{"):
                        try:
                            nested = json.loads(value)
                            sanitized[key] = _sanitize_obj(nested)
                            continue
                        except json.JSONDecodeError:
                            pass
                    sanitized[key] = mask(value)
                elif isinstance(value, str) and value.strip().startswith("{"):
                    try:
                        nested = json.loads(value)
                        sanitized[key] = _sanitize_obj(nested)
                    except json.JSONDecodeError:
                        sanitized[key] = value[:200]
                else:
                    if isinstance(value, str) and len(value) > 240:
                        sanitized[key] = value[:240] + "..."
                    else:
                        sanitized[key] = value
            lines.append(json.dumps(sanitized, ensure_ascii=False))

    conn.close()
    out = Path(r"D:\Project\AI\chat_bot\_cc_switch_probe.txt")
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {out}")


def _sanitize_obj(obj: object) -> object:
    if isinstance(obj, dict):
        result = {}
        for key, value in obj.items():
            key_l = str(key).lower()
            if any(x in key_l for x in ("key", "token", "secret", "password", "authorization")):
                result[key] = mask(value)
            else:
                result[key] = _sanitize_obj(value)
        return result
    if isinstance(obj, list):
        return [_sanitize_obj(x) for x in obj]
    if isinstance(obj, str) and len(obj) > 240:
        return obj[:240] + "..."
    return obj


if __name__ == "__main__":
    main()
