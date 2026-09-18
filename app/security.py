"""登录凭据校验与签名会话 Cookie。

无数据库场景下，凭据来自配置，登录态用 HMAC 签名的无状态 Cookie 承载。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time

from app.config import Settings

SESSION_COOKIE_NAME = "chat_session"
_SEPARATOR = "."


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _sign(payload: str, secret: str) -> str:
    digest = hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return _b64encode(digest)


def verify_credentials(username: str, password: str, settings: Settings) -> bool:
    """比对登录凭据，使用定长比较避免时序泄漏。"""
    username_ok = hmac.compare_digest(
        username.strip().encode("utf-8"),
        settings.auth_username.encode("utf-8"),
    )
    password_ok = hmac.compare_digest(
        password.encode("utf-8"),
        settings.auth_password.encode("utf-8"),
    )
    return username_ok and password_ok


def create_session_token(username: str, settings: Settings) -> str:
    """生成 `payload.signature` 形式的会话令牌。"""
    expires_at = int(time.time()) + settings.auth_session_max_age_seconds
    payload = _b64encode(f"{username}|{expires_at}".encode("utf-8"))
    return f"{payload}{_SEPARATOR}{_sign(payload, settings.auth_secret_key)}"


def verify_session_token(token: str, settings: Settings) -> str | None:
    """校验令牌签名与有效期，通过则返回用户名，否则返回 None。"""
    if not token or _SEPARATOR not in token:
        return None

    payload, _, signature = token.rpartition(_SEPARATOR)
    expected = _sign(payload, settings.auth_secret_key)
    if not hmac.compare_digest(signature, expected):
        return None

    try:
        username, _, expires_at = _b64decode(payload).decode("utf-8").rpartition("|")
        if int(expires_at) < int(time.time()):
            return None
    except (ValueError, UnicodeDecodeError):
        return None

    # 配置中的用户名变更后，历史令牌立即失效
    if username != settings.auth_username:
        return None
    return username
