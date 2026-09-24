"""FastAPI 应用入口。"""

from __future__ import annotations

import hmac
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from urllib.parse import parse_qs, quote

import uvicorn
from fastapi import FastAPI, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.chat import router as chat_router
from app.auth.oauth import (
    OAuthError,
    build_authorize_url,
    build_callback_url,
    exchange_code_for_user,
    get_provider,
    list_ready_providers,
    provider_ready,
)
from app.config import get_settings
from app.security import (
    OAUTH_STATE_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    create_oauth_state,
    create_session_token,
    verify_credentials,
    verify_oauth_state,
    verify_session_token,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
settings = get_settings()

PUBLIC_PATHS = frozenset(
    {
        "/",
        "/login",
        "/logout",
        "/favicon.ico",
        "/auth/google/login",
        "/auth/google/callback",
        "/auth/github/login",
        "/auth/github/callback",
    }
)
PUBLIC_PREFIXES = ("/static/",)
DEFAULT_REDIRECT = "/chat"
MAX_LOGIN_BODY_BYTES = 8 * 1024

app = FastAPI(title=settings.app_title)
app.include_router(chat_router)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def _is_public(path: str) -> bool:
    return path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES)


def _safe_redirect(target: str | None) -> str:
    """只允许站内相对路径，避免开放重定向。"""
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return DEFAULT_REDIRECT


def _parse_urlencoded(raw: bytes) -> dict[str, str]:
    parsed = parse_qs(raw.decode("utf-8", errors="replace"), keep_blank_values=True)
    return {key: values[0] for key, values in parsed.items() if values}


def _current_user(request: Request) -> str | None:
    token = request.cookies.get(SESSION_COOKIE_NAME, "")
    return verify_session_token(token, settings)


def _set_session_cookie(response: Response, username: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=create_session_token(username, settings),
        max_age=settings.auth_session_max_age_seconds,
        httponly=True,
        samesite="lax",
        secure=settings.auth_cookie_secure,
        path="/",
    )


def _login_page_context(
    *,
    next_url: str,
    username: str = "",
    error: str | None = None,
) -> dict:
    providers = list_ready_providers(settings)
    return {
        "app_title": settings.app_title,
        "next_url": next_url,
        "username": username,
        "error": error,
        "auth_local_enabled": settings.auth_local_enabled,
        "providers": providers,
    }


async def _login_error_response(
    request: Request,
    *,
    next_url: str,
    error: str,
    status_code: int = 401,
    username: str = "",
) -> Response:
    return templates.TemplateResponse(
        request,
        "login.html",
        _login_page_context(
            next_url=next_url,
            username=username,
            error=error,
        ),
        status_code=status_code,
    )


@app.middleware("http")
async def require_login(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """拦截未登录访问：接口返回 401，页面重定向到登录页。"""
    if not settings.auth_enabled or _is_public(request.url.path):
        return await call_next(request)

    if _current_user(request):
        return await call_next(request)

    if request.url.path.startswith("/api/"):
        return JSONResponse(
            {"error": {"message": "登录已失效，请重新登录。"}},
            status_code=401,
        )
    return RedirectResponse(
        f"/login?next={quote(request.url.path, safe='/')}",
        status_code=303,
    )


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    """产品介绍落地页。"""
    return templates.TemplateResponse(
        request,
        "home.html",
        {"app_title": settings.app_title},
    )


@app.get("/login")
async def login_page(
    request: Request,
    next_url: str = Query(default=DEFAULT_REDIRECT, alias="next"),
) -> Response:
    """登录表单。已登录则直接跳转目标页。"""
    if not settings.auth_enabled or _current_user(request):
        return RedirectResponse(_safe_redirect(next_url), status_code=303)
    return templates.TemplateResponse(
        request,
        "login.html",
        _login_page_context(next_url=_safe_redirect(next_url)),
    )


@app.post("/login")
async def login(request: Request) -> Response:
    """校验本地凭据并下发签名会话 Cookie。"""
    if not settings.auth_local_enabled:
        return await _login_error_response(
            request,
            next_url=DEFAULT_REDIRECT,
            error="已关闭本地账号登录，请使用第三方登录。",
            status_code=403,
        )

    raw = await request.body()
    if len(raw) > MAX_LOGIN_BODY_BYTES:
        return JSONResponse({"error": {"message": "请求体过大。"}}, status_code=413)

    form = _parse_urlencoded(raw)
    username = form.get("username", "")
    password = form.get("password", "")
    next_url = _safe_redirect(form.get("next", ""))

    if not verify_credentials(username, password, settings):
        logger.warning("本地登录失败，username=%s", username)
        return await _login_error_response(
            request,
            next_url=next_url,
            username=username,
            error="用户名或密码错误。",
        )

    logger.info("本地登录成功，username=%s", username)
    response = RedirectResponse(next_url, status_code=303)
    _set_session_cookie(response, settings.auth_username)
    return response


@app.get("/auth/{provider_key}/login")
async def oauth_login(
    request: Request,
    provider_key: str,
    next_url: str = Query(default=DEFAULT_REDIRECT, alias="next"),
) -> Response:
    """跳转 Google / GitHub 授权页。"""
    provider = get_provider(provider_key)
    if provider is None or not provider_ready(settings, provider):
        return RedirectResponse(
            f"/login?next={quote(_safe_redirect(next_url), safe='/')}",
            status_code=303,
        )

    safe_next = _safe_redirect(next_url)
    state = create_oauth_state(safe_next, settings)
    redirect_uri = build_callback_url(settings, str(request.base_url), provider.key)
    authorize_url = build_authorize_url(
        settings,
        provider,
        redirect_uri=redirect_uri,
        state=state,
    )
    response = RedirectResponse(authorize_url, status_code=303)
    response.set_cookie(
        key=OAUTH_STATE_COOKIE_NAME,
        value=state,
        max_age=600,
        httponly=True,
        samesite="lax",
        secure=settings.auth_cookie_secure,
        path="/",
    )
    return response


@app.get("/auth/{provider_key}/callback")
async def oauth_callback(
    request: Request,
    provider_key: str,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
) -> Response:
    """三方回调：校验 state、换 token、写入会话。"""
    provider = get_provider(provider_key)
    if provider is None or not provider_ready(settings, provider):
        return RedirectResponse("/login", status_code=303)

    if error:
        message = error_description or error
        logger.warning("%s 授权被拒绝：%s", provider.label, message)
        return await _login_error_response(
            request,
            next_url=DEFAULT_REDIRECT,
            error=f"{provider.label} 登录失败：{message}",
        )

    cookie_state = request.cookies.get(OAUTH_STATE_COOKIE_NAME, "")
    if not state or not cookie_state or not hmac.compare_digest(
        state.encode("utf-8"),
        cookie_state.encode("utf-8"),
    ):
        return await _login_error_response(
            request,
            next_url=DEFAULT_REDIRECT,
            error="登录状态校验失败，请重试。",
        )

    next_from_state = verify_oauth_state(state, settings)
    if next_from_state is None:
        return await _login_error_response(
            request,
            next_url=DEFAULT_REDIRECT,
            error="登录状态已过期，请重试。",
        )
    next_url = _safe_redirect(next_from_state)
    redirect_uri = build_callback_url(settings, str(request.base_url), provider.key)

    try:
        username = await exchange_code_for_user(
            settings,
            provider,
            code=code or "",
            redirect_uri=redirect_uri,
        )
    except OAuthError as exc:
        logger.warning("%s 回调处理失败：%s", provider.label, exc.message)
        return await _login_error_response(
            request,
            next_url=next_url,
            error=exc.message,
        )

    logger.info("%s 登录成功，username=%s", provider.label, username)
    response = RedirectResponse(next_url, status_code=303)
    _set_session_cookie(response, username)
    response.delete_cookie(OAUTH_STATE_COOKIE_NAME, path="/")
    return response


@app.post("/logout")
async def logout() -> Response:
    """清除会话 Cookie。"""
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(OAUTH_STATE_COOKIE_NAME, path="/")
    return response


@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request) -> HTMLResponse:
    """聊天工作台。"""
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "app_title": settings.app_title,
            "ai_model": settings.ai_model,
            "auth_enabled": settings.auth_enabled,
        },
    )


def main() -> None:
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=True,
    )


if __name__ == "__main__":
    main()
