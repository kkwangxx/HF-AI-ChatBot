"""配置解析单元测试。"""

from app.config import Settings


def build_settings(**overrides) -> Settings:
    """构造不读取 .env 的配置实例，避免本地 .env 干扰断言。"""
    return Settings(_env_file=None, **overrides)


def test_model_list_dedups_and_keeps_order() -> None:
    settings = build_settings(ai_model="a", ai_models="a, b , a ,c")
    assert settings.model_list() == ["a", "b", "c"]


def test_model_list_prepends_default_when_absent() -> None:
    settings = build_settings(ai_model="a", ai_models="b,c")
    assert settings.model_list() == ["a", "b", "c"]


def test_model_list_falls_back_to_default_only() -> None:
    settings = build_settings(ai_model="a", ai_models="")
    assert settings.model_list() == ["a"]
