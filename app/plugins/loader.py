"""插件加载。新增可集成项目时在这里注册，不要改 Agent 循环。"""

from __future__ import annotations

from app.agent.registry import ToolRegistry
from app.config import Settings
from app.plugins.mom.plugin import MomPlugin


def load_plugins(settings: Settings) -> ToolRegistry:
    """按配置加载插件。没有任何可用数据源时返回空注册表，聊天保持原路径。"""
    registry = ToolRegistry()
    if not settings.agent_enabled:
        return registry

    mom = MomPlugin(settings)
    if mom.available():
        registry.register(mom)
    return registry
