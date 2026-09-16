"""从 CC Switch 当前 Claude 配置同步到项目 .env（脱敏日志）。"""

from __future__ import annotations

import json
from pathlib import Path


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


def main() -> None:
    settings = json.loads(
        (Path.home() / ".claude" / "settings.json").read_text(encoding="utf-8")
    )
    env = settings.get("env") or {}
    base = str(env.get("ANTHROPIC_BASE_URL", "")).rstrip("/")
    key = str(env.get("ANTHROPIC_AUTH_TOKEN") or env.get("ANTHROPIC_API_KEY") or "")
    model = str(env.get("ANTHROPIC_MODEL") or "claude-sonnet-5")
    models = collect_models(env)
    if model and model not in models:
        models.insert(0, model)

    if not base or not key:
        raise SystemExit("未在 ~/.claude/settings.json 中找到可用的 Base URL / API Key")

    content = "\n".join(
        [
            f"AI_API_BASE_URL={base}",
            f"AI_API_KEY={key}",
            f"AI_MODEL={model}",
            f"AI_MODELS={','.join(models)}",
            "AI_API_PROTOCOL=anthropic",
            "AI_MAX_TOKENS=4096",
            "APP_TITLE=AI Chat Bot",
            "",
        ]
    )
    env_path = Path(r"D:\Project\AI\chat_bot\.env")
    env_path.write_text(content, encoding="utf-8", newline="\n")
    print(f"synced -> {env_path}")
    print(f"base={base}")
    print(f"model={model}")
    print(f"models={models}")
    print(f"key={mask(key)}")
    print("protocol=anthropic")


if __name__ == "__main__":
    main()
