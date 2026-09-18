"""工具注册表。Agent 只认识注册进来的插件，不依赖具体业务项目。"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from app.agent.types import ToolSpec

logger = logging.getLogger(__name__)


class Plugin(Protocol):
    """别的项目要接入时实现这四个方法，再注册进来。"""

    name: str

    def tool_specs(self) -> list[ToolSpec]:
        """本插件提供的工具。"""

    def system_prompt(self) -> str:
        """追加到系统提示词的项目说明。不要包含密钥。"""

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """执行工具，返回可 JSON 序列化的结构化结果。"""


class ToolRegistry:
    """按工具名分发到插件。同名工具以后注册的拒绝覆盖，避免静默冲突。"""

    def __init__(self) -> None:
        self._plugins: list[Plugin] = []
        self._owners: dict[str, Plugin] = {}

    def register(self, plugin: Plugin) -> None:
        for spec in plugin.tool_specs():
            if spec.name in self._owners:
                raise ValueError(f"工具名冲突：{spec.name}")
            self._owners[spec.name] = plugin
        self._plugins.append(plugin)

    def tool_specs(self) -> list[ToolSpec]:
        specs: list[ToolSpec] = []
        for plugin in self._plugins:
            specs.extend(plugin.tool_specs())
        return specs

    def system_prompt(self) -> str:
        parts = [plugin.system_prompt().strip() for plugin in self._plugins]
        return "\n\n".join(part for part in parts if part)

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        plugin = self._owners.get(name)
        if plugin is None:
            return {"success": False, "error": f"未知工具：{name}"}
        if not isinstance(arguments, dict):
            return {"success": False, "error": "工具参数必须是 JSON 对象"}
        try:
            result = plugin.call(name, arguments)
        except Exception as exc:  # noqa: BLE001
            logger.error("工具执行失败，name=%s，原因：%s", name, exc, exc_info=True)
            return {"success": False, "error": "工具执行失败，请缩小范围后重试。"}
        if not isinstance(result, dict):
            return {"success": False, "error": "工具返回了无法识别的结果"}
        return result
