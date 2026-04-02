"""Integration registry — maps enabled integrations to their tool registration functions."""

from __future__ import annotations

from collections.abc import Callable

from mcp.server.fastmcp import FastMCP

from ..config import Settings
from .dingtalk import register_dingtalk_tools
from .jira import register_jira_tools

INTEGRATION_REGISTRY: dict[str, Callable[[FastMCP, Settings], None]] = {
    "dingtalk": register_dingtalk_tools,
    "jira": register_jira_tools,
}
