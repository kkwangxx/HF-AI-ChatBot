"""Google / GitHub OAuth 登录。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlencode

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)


class OAuthError(Exception):
    """三方登录失败。"""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass(frozen=True)
class OAuthProvider:
    """一个可配置的 OAuth 提供商。"""

    key: str
    label: str
    css: str
    authorize_url: str
    token_url: str
    scope: str
    client_id_attr: str
    client_secret_attr: str
    fetch_identity: Callable[[str], Any]


async def _fetch_google_identity(access_token: str) -> str:
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if response.status_code >= 400:
            raise OAuthError("无法从 Google 获取用户信息。")
        data = response.json()
    email = str(data.get("email") or "").strip()
    sub = str(data.get("sub") or "").strip()
    if email:
        return f"google/{email}"
    if sub:
        return f"google/{sub}"
    raise OAuthError("Google 未返回可用的用户标识。")


async def _fetch_github_identity(access_token: str) -> str:
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "hf-ai-chatbot",
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get("https://api.github.com/user", headers=headers)
        if response.status_code >= 400:
            raise OAuthError("无法从 GitHub 获取用户信息。")
        data = response.json()
    login = str(data.get("login") or "").strip()
    if login:
        return f"github/{login}"
    user_id = data.get("id")
    if user_id is not None:
        return f"github/{user_id}"
    raise OAuthError("GitHub 未返回可用的用户标识。")


PROVIDERS: dict[str, OAuthProvider] = {
    "google": OAuthProvider(
        key="google",
        label="Google",
        css="google",
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        scope="openid email profile",
        client_id_attr="google_client_id",
        client_secret_attr="google_client_secret",
        fetch_identity=_fetch_google_identity,
    ),
    "github": OAuthProvider(
        key="github",
        label="GitHub",
        css="github",
        authorize_url="https://github.com/login/oauth/authorize",
        token_url="https://github.com/login/oauth/access_token",
        scope="read:user user:email",
        client_id_attr="github_client_id",
        client_secret_attr="github_client_secret",
        fetch_identity=_fetch_github_identity,
    ),
}


def get_provider(key: str) -> OAuthProvider | None:
    return PROVIDERS.get((key or "").strip().lower())


def provider_ready(settings: Settings, provider: OAuthProvider) -> bool:
    client_id = str(getattr(settings, provider.client_id_attr, "") or "").strip()
    client_secret = str(getattr(settings, provider.client_secret_attr, "") or "").strip()
    return bool(client_id and client_secret)


def list_ready_providers(settings: Settings) -> list[dict[str, str]]:
    """登录页按钮数据。只返回已配置 Client ID/Secret 的提供商。"""
    items: list[dict[str, str]] = []
    for provider in PROVIDERS.values():
        if not provider_ready(settings, provider):
            continue
        items.append(
            {
                "key": provider.key,
                "label": provider.label,
                "css": provider.css,
            }
        )
    return items


def resolve_public_base(settings: Settings, request_base_url: str) -> str:
    configured = settings.oauth_public_base_url.strip().rstrip("/")
    if configured:
        return configured
    return request_base_url.rstrip("/")


def build_callback_url(settings: Settings, request_base_url: str, provider_key: str) -> str:
    return f"{resolve_public_base(settings, request_base_url)}/auth/{provider_key}/callback"


def build_authorize_url(
    settings: Settings,
    provider: OAuthProvider,
    *,
    redirect_uri: str,
    state: str,
) -> str:
    client_id = str(getattr(settings, provider.client_id_attr)).strip()
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": provider.scope,
        "state": state,
    }
    # Google 建议带上 access_type / prompt，便于拿到稳定授权
    if provider.key == "google":
        params["access_type"] = "online"
        params["include_granted_scopes"] = "true"
        params["prompt"] = "select_account"
    return f"{provider.authorize_url}?{urlencode(params)}"


async def exchange_code_for_user(
    settings: Settings,
    provider: OAuthProvider,
    *,
    code: str,
    redirect_uri: str,
) -> str:
    """用授权码换 access_token，再换成本地会话用户名。"""
    if not code.strip():
        raise OAuthError("缺少授权码。")
    if not provider_ready(settings, provider):
        raise OAuthError(f"{provider.label} 登录未配置。")

    client_id = str(getattr(settings, provider.client_id_attr)).strip()
    client_secret = str(getattr(settings, provider.client_secret_attr)).strip()
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }
    headers = {"Accept": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(provider.token_url, data=data, headers=headers)
            payload = response.json() if response.content else {}
            status_code = response.status_code
    except Exception as exc:  # noqa: BLE001
        logger.error("%s 换取 token 失败：%s", provider.label, exc, exc_info=True)
        raise OAuthError(f"向 {provider.label} 换取令牌失败。") from exc

    if not isinstance(payload, dict):
        raise OAuthError(f"{provider.label} 返回了无法识别的令牌响应。")
    if status_code >= 400 or payload.get("error"):
        detail = payload.get("error_description") or payload.get("error") or "授权失败"
        raise OAuthError(f"{provider.label} 授权失败：{detail}")

    access_token = str(payload.get("access_token") or "").strip()
    if not access_token:
        raise OAuthError(f"{provider.label} 未返回 access_token。")

    try:
        return await provider.fetch_identity(access_token)
    except OAuthError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("%s 拉取用户信息失败：%s", provider.label, exc, exc_info=True)
        raise OAuthError(f"无法从 {provider.label} 获取用户信息。") from exc
