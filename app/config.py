"""应用配置，通过环境变量 / .env 加载。"""

import logging
import secrets
from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """AI API 与服务端配置。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ai_api_base_url: str = "http://localhost:8080"
    ai_api_key: str = ""
    ai_model: str = "my-model"
    # 逗号分隔的可选模型列表，供 WebUI 切换
    ai_models: str = ""
    # openai: /v1/chat/completions；anthropic: /v1/messages（CC Switch Claude 常用）
    ai_api_protocol: Literal["openai", "anthropic"] = "openai"
    ai_max_tokens: int = 4096
    ai_timeout_seconds: float = 120.0
    app_title: str = "AI Chat Bot"

    # 默认只监听本机，避免把上游 API Key 暴露到公网
    app_host: str = "127.0.0.1"
    app_port: int = 8000

    # 登录鉴权（无数据库，凭据来自配置）
    auth_enabled: bool = True
    auth_username: str = "admin"
    auth_password: str = "admin"
    # 为空时启动自动生成临时密钥，重启后登录态失效
    auth_secret_key: str = ""
    auth_session_max_age_seconds: int = 7 * 24 * 3600
    # 通过 HTTPS 部署时应设为 true
    auth_cookie_secure: bool = False

    @model_validator(mode="after")
    def ensure_auth_secret_key(self) -> "Settings":
        """未显式配置签名密钥时生成临时密钥，避免使用固定弱密钥。"""
        if self.auth_enabled and not self.auth_secret_key.strip():
            self.auth_secret_key = secrets.token_urlsafe(32)
            logger.warning(
                "未配置 AUTH_SECRET_KEY，已生成临时签名密钥，服务重启后需要重新登录。"
            )
        return self

    def model_list(self) -> list[str]:
        """解析可选模型，确保默认模型在列表中。"""
        items: list[str] = []
        seen: set[str] = set()
        for raw in self.ai_models.split(","):
            name = raw.strip()
            if not name or name in seen:
                continue
            seen.add(name)
            items.append(name)
        if self.ai_model and self.ai_model not in seen:
            items.insert(0, self.ai_model)
        if not items and self.ai_model:
            items.append(self.ai_model)
        return items


@lru_cache
def get_settings() -> Settings:
    return Settings()
