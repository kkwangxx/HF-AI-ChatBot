"""应用配置，通过环境变量 / .env 加载。"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


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
