"""从 CC Switch 当前 Claude 配置同步到项目 .env（脱敏日志）。

只更新 AI_* 相关键，保留 .env 中已有的其他配置与注释。
"""

from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"
CLAUDE_SETTINGS_PATH = Path.home() / ".claude" / "settings.json"


def mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}...{value[-4:]}"


def collect_models(env: dict) -> list[str]:
    """从当前 Claude env 收集可选模型（去重保序）。"""
    keys = [
        "ANTHROPIC_MODEL",
        "ANTHROPIC_DEFAULT_SONNET_MODEL",
        "ANTHROPIC_DEFAULT_OPUS_MODEL",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL",
        "ANTHROPIC_DEFAULT_SONNET_MODEL_NAME",
        "ANTHROPIC_DEFAULT_OPUS_MODEL_NAME",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL_NAME",
    ]
    models: list[str] = []
    seen: set[str] = set()
    for key in keys:
        value = str(env.get(key) or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        models.append(value)
    return models


def load_claude_env() -> dict:
    """读取 CC Switch / Claude Code 的当前配置。"""
    if not CLAUDE_SETTINGS_PATH.exists():
        raise SystemExit(f"未找到 Claude 配置文件：{CLAUDE_SETTINGS_PATH}")
    try:
        settings = json.loads(CLAUDE_SETTINGS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Claude 配置文件不是合法 JSON：{exc}") from exc
    return settings.get("env") or {}


def upsert_env(lines: list[str], updates: dict[str, str]) -> list[str]:
    """原地替换已存在的键，其余键追加到末尾，保留注释与无关配置。"""
    remaining = dict(updates)
    result: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in remaining:
                result.append(f"{key}={remaining.pop(key)}")
                continue
        result.append(line)
    result.extend(f"{key}={value}" for key, value in remaining.items())
    return result


def main() -> None:
    env = load_claude_env()
    base = str(env.get("ANTHROPIC_BASE_URL", "")).rstrip("/")
    key = str(env.get("ANTHROPIC_AUTH_TOKEN") or env.get("ANTHROPIC_API_KEY") or "")
    model = str(env.get("ANTHROPIC_MODEL") or "claude-sonnet-5")
    models = collect_models(env)
    if model and model not in models:
        models.insert(0, model)

    if not base or not key:
        raise SystemExit(f"未在 {CLAUDE_SETTINGS_PATH} 中找到可用的 Base URL / API Key")

    updates = {
        "AI_API_BASE_URL": base,
        "AI_API_KEY": key,
        "AI_MODEL": model,
        "AI_MODELS": ",".join(models),
        "AI_API_PROTOCOL": "anthropic",
    }

    existing = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    merged = upsert_env(existing, updates)
    ENV_PATH.write_text("\n".join(merged) + "\n", encoding="utf-8", newline="\n")

    print(f"synced -> {ENV_PATH}")
    print(f"base={base}")
    print(f"model={model}")
    print(f"models={models}")
    print(f"key={mask(key)}")
    print("protocol=anthropic")
    if not existing:
        print("提示：.env 原本不存在，登录配置将使用默认值（admin / admin）")


if __name__ == "__main__":
    main()
