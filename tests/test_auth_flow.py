"""登录流程端到端测试（不触达上游 AI）。"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.security import SESSION_COOKIE_NAME


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, follow_redirects=False)


def login(client: TestClient) -> None:
    response = client.post(
        "/login",
        data={"username": "tester", "password": "test-pass", "next": "/chat"},
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/chat"


def test_landing_page_is_public(client: TestClient) -> None:
    assert client.get("/").status_code == 200


def test_login_page_is_public(client: TestClient) -> None:
    assert client.get("/login").status_code == 200


def test_chat_page_redirects_when_anonymous(client: TestClient) -> None:
    response = client.get("/chat")
    assert response.status_code == 303
    assert response.headers["location"] == "/login?next=/chat"


def test_api_returns_401_when_anonymous(client: TestClient) -> None:
    response = client.get("/api/models")
    assert response.status_code == 401
    assert response.json()["error"]["message"]


def test_login_rejects_wrong_credentials(client: TestClient) -> None:
    response = client.post("/login", data={"username": "tester", "password": "nope"})
    assert response.status_code == 401
    assert SESSION_COOKIE_NAME not in response.cookies


def test_login_grants_access_to_chat_and_api(client: TestClient) -> None:
    login(client)
    assert client.cookies.get(SESSION_COOKIE_NAME)
    assert client.get("/chat").status_code == 200

    models = client.get("/api/models")
    assert models.status_code == 200
    assert models.json()["default"] == "test-model"


def test_logout_revokes_access(client: TestClient) -> None:
    login(client)
    response = client.post("/logout")
    assert response.status_code == 303
    assert client.get("/chat").status_code == 303


def test_login_rejects_offsite_redirect_target(client: TestClient) -> None:
    response = client.post(
        "/login",
        data={
            "username": "tester",
            "password": "test-pass",
            "next": "https://evil.example.com",
        },
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/chat"
