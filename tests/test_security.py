"""会话令牌与凭据校验单元测试。"""

from app.config import Settings
from app.security import (
    create_session_token,
    verify_credentials,
    verify_session_token,
)


def build_settings(**overrides) -> Settings:
    defaults = {
        "auth_secret_key": "test-secret",
        "auth_username": "admin",
        "auth_password": "admin",
    }
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


def test_verify_credentials_accepts_configured_pair() -> None:
    settings = build_settings()
    assert verify_credentials("admin", "admin", settings) is True


def test_verify_credentials_rejects_wrong_password() -> None:
    settings = build_settings()
    assert verify_credentials("admin", "wrong", settings) is False


def test_verify_credentials_trims_username_whitespace() -> None:
    settings = build_settings()
    assert verify_credentials("  admin  ", "admin", settings) is True


def test_session_token_round_trip() -> None:
    settings = build_settings()
    token = create_session_token("admin", settings)
    assert verify_session_token(token, settings) == "admin"


def test_session_token_rejects_tampered_signature() -> None:
    settings = build_settings()
    token = create_session_token("admin", settings)
    payload, _, signature = token.rpartition(".")
    tampered = f"{payload}.{signature[:-1]}x"
    assert verify_session_token(tampered, settings) is None


def test_session_token_rejects_other_secret_key() -> None:
    token = create_session_token("admin", build_settings())
    assert verify_session_token(token, build_settings(auth_secret_key="other")) is None


def test_session_token_rejects_expired_token() -> None:
    settings = build_settings(auth_session_max_age_seconds=-10)
    token = create_session_token("admin", settings)
    assert verify_session_token(token, settings) is None


def test_session_token_rejects_renamed_user() -> None:
    token = create_session_token("admin", build_settings())
    settings = build_settings(auth_username="someone-else")
    assert verify_session_token(token, settings) is None


def test_session_token_rejects_malformed_value() -> None:
    assert verify_session_token("not-a-token", build_settings()) is None
