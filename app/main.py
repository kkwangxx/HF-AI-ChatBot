"""FastAPI 应用入口。"""

from __future__ import annotations

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
from app.config import get_settings
from app.security import (
    SESSION_COOKIE_NAME,
    create_session_token,
    verify_credentials,
    verify_session_token,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
settings = get_settings()

# 无需登录即可访问：落地页、登录/登出、静态资源
PUBLIC_PATHS = frozenset({"/", "/login", "/logout", "/favicon.ico"})
PUBLIC_PREFIXES = ("/static/",)
DEFAULT_REDIRECT = "/chat"
# 登录表单体积很小，限制上限避免未鉴权接口被塞入大请求体
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
    """解析表单请求体，避免为登录页引入 python-multipart 依赖。"""
    parsed = parse_qs(raw.decode("utf-8", errors="replace"), keep_blank_values=True)
    return {key: values[0] for key, values in parsed.items() if values}


def _current_user(request: Request) -> str | None:
    token = request.cookies.get(SESSION_COOKIE_NAME, "")
    return verify_session_token(token, settings)


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
        {
            "app_title": settings.app_title,
            "next_url": _safe_redirect(next_url),
            "username": "",
            "error": None,
        },
    )


@app.post("/login")
async def login(request: Request) -> Response:
    """校验凭据并下发签名会话 Cookie。"""
    raw = await request.body()
    if len(raw) > MAX_LOGIN_BODY_BYTES:
        return JSONResponse({"error": {"message": "请求体过大。"}}, status_code=413)

    form = _parse_urlencoded(raw)
    username = form.get("username", "")
    password = form.get("password", "")
    next_url = _safe_redirect(form.get("next", ""))

    if not verify_credentials(username, password, settings):
        logger.warning("登录失败，username=%s", username)
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "app_title": settings.app_title,
                "next_url": next_url,
                "username": username,
                "error": "用户名或密码错误。",
            },
            status_code=401,
        )

    logger.info("登录成功，username=%s", username)
    response = RedirectResponse(next_url, status_code=303)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=create_session_token(settings.auth_username, settings),
        max_age=settings.auth_session_max_age_seconds,
        httponly=True,
        samesite="lax",
        secure=settings.auth_cookie_secure,
        path="/",
    )
    return response


@app.post("/logout")
async def logout() -> Response:
    """清除会话 Cookie。"""
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
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
