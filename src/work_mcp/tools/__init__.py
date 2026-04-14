"""Plugin registry — maps enabled plugins to their tool registration functions."""

from __future__ import annotations

from collections.abc import Callable

from mcp.server.fastmcp import FastMCP

from ..config import Settings
from .database import register_database_tools
from .dingtalk import register_dingtalk_tools
from .jira import register_jira_tools
from .log_search import register_log_search_tools
from .remote_fs import register_remote_fs_tools

PLUGIN_REGISTRY: dict[str, Callable[[FastMCP, Settings], None]] = {
    "database": register_database_tools,
    "dingtalk": register_dingtalk_tools,
    "jira": register_jira_tools,
    "log_search": register_log_search_tools,
    "remote_fs": register_remote_fs_tools,
}
