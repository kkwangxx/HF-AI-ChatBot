"""Google / GitHub OAuth 单元测试。不访问真实三方平台。"""

import asyncio
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.auth.oauth import (
    OAuthError,
    build_authorize_url,
    build_callback_url,
    exchange_code_for_user,
    get_provider,
    list_ready_providers,
)
from app.config import Settings
from app.main import app
from app.security import OAUTH_STATE_COOKIE_NAME, SESSION_COOKIE_NAME, create_oauth_state


def build_settings(**overrides) -> Settings:
    defaults = {
        "auth_secret_key": "unit-test-secret",
        "auth_username": "tester",
        "auth_password": "test-pass",
        "google_client_id": "google-id",
        "google_client_secret": "google-secret",
        "github_client_id": "github-id",
        "github_client_secret": "github-secret",
        "oauth_public_base_url": "http://127.0.0.1:8000",
    }
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, follow_redirects=False)


def test_list_ready_providers_requires_both_credentials() -> None:
    both = list_ready_providers(build_settings())
    assert [item["key"] for item in both] == ["google", "github"]

    only_google = list_ready_providers(
        build_settings(github_client_id="", github_client_secret="")
    )
    assert [item["key"] for item in only_google] == ["google"]

    none_ready = list_ready_providers(
        build_settings(
            google_client_id="",
            google_client_secret="",
            github_client_id="",
            github_client_secret="",
        )
    )
    assert none_ready == []


def test_build_authorize_url_for_google() -> None:
    settings = build_settings()
    provider = get_provider("google")
    assert provider is not None
    url = build_authorize_url(
        settings,
        provider,
        redirect_uri="http://127.0.0.1:8000/auth/google/callback",
        state="abc",
    )
    assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert "client_id=google-id" in url
    assert "state=abc" in url


def test_build_callback_url_uses_public_base() -> None:
    settings = build_settings()
    assert (
        build_callback_url(settings, "http://ignored/", "github")
        == "http://127.0.0.1:8000/auth/github/callback"
    )


def test_oauth_login_redirects_to_github(client: TestClient, monkeypatch) -> None:
    from app import main as main_mod

    monkeypatch.setattr(main_mod, "settings", build_settings())
    response = client.get("/auth/github/login?next=/chat")
    assert response.status_code == 303
    assert response.headers["location"].startswith(
        "https://github.com/login/oauth/authorize?"
    )
    assert OAUTH_STATE_COOKIE_NAME in response.cookies


def test_oauth_login_falls_back_when_not_configured(
    client: TestClient, monkeypatch
) -> None:
    from app import main as main_mod

    monkeypatch.setattr(
        main_mod,
        "settings",
        build_settings(google_client_id="", google_client_secret=""),
    )
    response = client.get("/auth/google/login?next=/chat")
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login?")


def test_oauth_callback_sets_session(client: TestClient, monkeypatch) -> None:
    from app import main as main_mod

    settings = build_settings()
    monkeypatch.setattr(main_mod, "settings", settings)
    state = create_oauth_state("/chat", settings)
    client.cookies.set(OAUTH_STATE_COOKIE_NAME, state)

    async def fake_exchange(_settings, provider, *, code, redirect_uri):
        assert provider.key == "google"
        assert code == "auth-code"
        assert redirect_uri.endswith("/auth/google/callback")
        return "google/alice@example.com"

    monkeypatch.setattr(main_mod, "exchange_code_for_user", fake_exchange)
    response = client.get(f"/auth/google/callback?code=auth-code&state={state}")
    assert response.status_code == 303
    assert response.headers["location"] == "/chat"
    assert SESSION_COOKIE_NAME in response.cookies


def test_oauth_callback_rejects_bad_state(client: TestClient, monkeypatch) -> None:
    from app import main as main_mod

    settings = build_settings()
    monkeypatch.setattr(main_mod, "settings", settings)
    client.cookies.set(OAUTH_STATE_COOKIE_NAME, create_oauth_state("/chat", settings))
    response = client.get("/auth/github/callback?code=auth-code&state=tampered")
    assert response.status_code == 401
    assert SESSION_COOKIE_NAME not in response.cookies


def test_login_page_shows_ready_providers(client: TestClient, monkeypatch) -> None:
    from app import main as main_mod

    monkeypatch.setattr(main_mod, "settings", build_settings())
    response = client.get("/login")
    assert response.status_code == 200
    assert "Google" in response.text
    assert "GitHub" in response.text
    assert "/auth/google/login" in response.text
    assert "/auth/github/login" in response.text


def test_exchange_code_for_user_google() -> None:
    settings = build_settings()
    provider = get_provider("google")
    assert provider is not None

    class FakeResponse:
        def __init__(self, status_code: int, payload: dict) -> None:
            self.status_code = status_code
            self.content = b"{}"
            self._payload = payload

        def json(self) -> dict:
            return self._payload

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return None

        async def post(self, *_args, **_kwargs):
            return FakeResponse(200, {"access_token": "tok"})

        async def get(self, *_args, **_kwargs):
            return FakeResponse(200, {"email": "alice@example.com", "sub": "1"})

    with patch("app.auth.oauth.httpx.AsyncClient", FakeClient):
        username = asyncio.run(
            exchange_code_for_user(
                settings,
                provider,
                code="code",
                redirect_uri="http://127.0.0.1:8000/auth/google/callback",
            )
        )
    assert username == "google/alice@example.com"


def test_exchange_rejects_empty_code() -> None:
    settings = build_settings()
    provider = get_provider("github")
    assert provider is not None

    with pytest.raises(OAuthError):
        asyncio.run(
            exchange_code_for_user(
                settings,
                provider,
                code="",
                redirect_uri="http://127.0.0.1:8000/auth/github/callback",
            )
        )
