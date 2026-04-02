from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ...config import Settings
from .service import JiraService


def register_jira_tools(mcp: FastMCP, settings: Settings) -> None:
    service = JiraService(settings)

    @mcp.tool()
    def jira_get_latest_assigned_issue() -> dict[str, Any]:
        """Fetch the most recently updated open issue assigned to the current user, including image attachment metadata."""
        return service.get_latest_assigned_issue()

    @mcp.tool()
    def jira_get_attachment_image(issue_key: str, attachment_id: str) -> dict[str, Any]:
        """Fetch one Jira image attachment when you need the actual image content for an issue you are working on."""
        return service.get_attachment_image(issue_key, attachment_id)

    @mcp.tool()
    def jira_accept_issue(issue_key: str) -> dict[str, Any]:
        """Call this when you have understood the issue and are about to start working on it."""
        return service.accept_issue(issue_key)

    @mcp.tool()
    def jira_resolve_issue(issue_key: str) -> dict[str, Any]:
        """Call this when you have finished fixing the issue and the fix is ready for verification."""
        return service.resolve_issue(issue_key)
