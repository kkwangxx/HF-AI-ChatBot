"""探测 CC Switch 当前 Claude 配置对应的可用 API 协议（不打印完整密钥）。"""

from __future__ import annotations

import json
from pathlib import Path

import httpx


def mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}...{value[-4:]}"


def main() -> None:
    settings = json.loads(
        (Path.home() / ".claude" / "settings.json").read_text(encoding="utf-8")
    )
    env = settings.get("env") or {}
    base = str(env.get("ANTHROPIC_BASE_URL", "")).rstrip("/")
    key = str(env.get("ANTHROPIC_AUTH_TOKEN") or env.get("ANTHROPIC_API_KEY") or "")
    model = str(env.get("ANTHROPIC_MODEL") or "claude-sonnet-5")

    out: list[str] = [
        f"base={base}",
        f"model={model}",
        f"key={mask(key)}",
    ]

    headers_openai = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    headers_anthropic = {
        "x-api-key": key,
        "Authorization": f"Bearer {key}",
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }

    cases = [
        (
            "openai_chat",
            "POST",
            f"{base}/v1/chat/completions",
            headers_openai,
            {
                "model": model,
                "messages": [{"role": "user", "content": "只回复一个字：好"}],
                "stream": False,
                "max_tokens": 16,
            },
        ),
        (
            "anthropic_messages",
            "POST",
            f"{base}/v1/messages",
            headers_anthropic,
            {
                "model": model,
                "max_tokens": 16,
                "messages": [{"role": "user", "content": "只回复一个字：好"}],
                "stream": False,
            },
        ),
        (
            "anthropic_messages_no_v1",
            "POST",
            f"{base}/messages",
            headers_anthropic,
            {
                "model": model,
                "max_tokens": 16,
                "messages": [{"role": "user", "content": "只回复一个字：好"}],
                "stream": False,
            },
        ),
    ]

    with httpx.Client(timeout=45.0) as client:
        for name, method, url, headers, body in cases:
            try:
                resp = client.request(method, url, headers=headers, json=body)
                text = resp.text.replace("\n", " ")[:180]
                out.append(f"{name} status={resp.status_code} body={text}")
            except Exception as exc:  # noqa: BLE001
                out.append(f"{name} error={exc}")

    path = Path(r"D:\Project\AI\chat_bot\_api_probe.txt")
    path.write_text("\n".join(out), encoding="utf-8")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
