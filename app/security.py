"""登录凭据校验与签名会话 Cookie。

无数据库场景下，本地凭据来自配置；三方 OAuth 用户校验通过后同样写入签名 Cookie。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from urllib.parse import quote, unquote

from app.config import Settings

SESSION_COOKIE_NAME = "chat_session"
OAUTH_STATE_COOKIE_NAME = "oauth_state"
_SEPARATOR = "."
# OAuth state 有效期 10 分钟，足够完成跳转登录
_OAUTH_STATE_TTL_SECONDS = 600


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
    """比对本地登录凭据，使用定长比较避免时序泄漏。"""
    if not settings.auth_local_enabled:
        return False
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
    """校验令牌签名与有效期，通过则返回用户名，否则返回 None。

    不要求用户名等于 AUTH_USERNAME，以便接纳 Google/GitHub 等三方用户。
    """
    if not token or _SEPARATOR not in token:
        return None

    payload, _, signature = token.rpartition(_SEPARATOR)
    expected = _sign(payload, settings.auth_secret_key)
    if not hmac.compare_digest(signature, expected):
        return None

    try:
        username, _, expires_at = _b64decode(payload).decode("utf-8").rpartition("|")
        if not username or int(expires_at) < int(time.time()):
            return None
    except (ValueError, UnicodeDecodeError):
        return None

    return username


def create_oauth_state(next_url: str, settings: Settings) -> str:
    """签发 OAuth state，内嵌 next 与过期时间，防 CSRF。"""
    nonce = secrets.token_urlsafe(16)
    expires_at = int(time.time()) + _OAUTH_STATE_TTL_SECONDS
    body = f"{nonce}|{quote(next_url, safe='/')}|{expires_at}"
    payload = _b64encode(body.encode("utf-8"))
    return f"{payload}{_SEPARATOR}{_sign(payload, settings.auth_secret_key)}"


def verify_oauth_state(state: str, settings: Settings) -> str | None:
    """校验 state，通过则返回其中的 next_url。"""
    if not state or _SEPARATOR not in state:
        return None

    payload, _, signature = state.rpartition(_SEPARATOR)
    expected = _sign(payload, settings.auth_secret_key)
    if not hmac.compare_digest(signature, expected):
        return None

    try:
        decoded = _b64decode(payload).decode("utf-8")
        _nonce, next_part, expires_at = decoded.split("|", 2)
        if int(expires_at) < int(time.time()):
            return None
        return unquote(next_part)
    except (ValueError, UnicodeDecodeError):
        return None
