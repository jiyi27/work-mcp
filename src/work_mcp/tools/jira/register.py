from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ...config import Settings
from .service import JiraService
from .strings import (
    JIRA_GET_ISSUE_DETAILS_TOOL_NAME,
    JIRA_LIST_OPEN_ASSIGNED_ISSUES_TOOL_NAME,
    JIRA_RESOLVE_ISSUE_TOOL_NAME,
    JIRA_START_ISSUE_TOOL_NAME,
)


def register_jira_tools(mcp: FastMCP, settings: Settings) -> None:
    service = JiraService(settings)

    @mcp.tool(name=JIRA_LIST_OPEN_ASSIGNED_ISSUES_TOOL_NAME)
    def jira_list_open_assigned_issues() -> dict[str, Any]:
        """List the current user's open Jira issues so the user can choose one by key."""
        return service.list_open_assigned_issues()

    @mcp.tool(name=JIRA_GET_ISSUE_DETAILS_TOOL_NAME)
    def jira_get_issue_details(issue_key: str) -> dict[str, Any]:
        """Fetch detailed Jira context after the user provides or selects one issue key."""
        return service.get_issue_details(issue_key)

    # @mcp.tool()
    # def jira_get_attachment_image(issue_key: str, attachment_id: str) -> dict[str, Any]:
    #     """Fetch one Jira image attachment when you need the actual image content for an issue you are working on."""
    #     return service.get_attachment_image(issue_key, attachment_id)

    @mcp.tool(name=JIRA_START_ISSUE_TOOL_NAME)
    def jira_start_issue(issue_key: str) -> dict[str, Any]:
        """Call this when you have understood the issue and are about to start working on it."""
        return service.start_issue(issue_key)

    @mcp.tool(name=JIRA_RESOLVE_ISSUE_TOOL_NAME)
    def jira_resolve_issue(issue_key: str) -> dict[str, Any]:
        """Call this when you have finished fixing the issue and the fix is ready for verification."""
        return service.resolve_issue(issue_key)
