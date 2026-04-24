"""Plugin registry — maps enabled plugins to their tool registration functions."""

from __future__ import annotations

from collections.abc import Callable
from importlib import import_module
from typing import NamedTuple, cast

from mcp.server.fastmcp import FastMCP

from ..config import Settings


RegisterTools = Callable[[FastMCP, Settings], None]


class PluginSpec(NamedTuple):
    module: str
    function: str

    def load(self) -> RegisterTools:
        module = import_module(self.module)
        register_fn = getattr(module, self.function)
        return cast(RegisterTools, register_fn)


PLUGIN_REGISTRY: dict[str, PluginSpec] = {
    "database": PluginSpec("work_mcp.tools.database", "register_database_tools"),
    "dingtalk": PluginSpec("work_mcp.tools.dingtalk", "register_dingtalk_tools"),
    "jira": PluginSpec("work_mcp.tools.jira", "register_jira_tools"),
    "log_search": PluginSpec("work_mcp.tools.log_search", "register_log_search_tools"),
    "remote_fs": PluginSpec("work_mcp.tools.remote_fs", "register_remote_fs_tools"),
}
