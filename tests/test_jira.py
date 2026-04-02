from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

from work_assistant_mcp.config import Settings
from work_assistant_mcp.server import create_mcp


def _make_settings(**overrides: object) -> Settings:
    defaults = dict(
        dingtalk_webhook_url="https://example.invalid/webhook",
        dingtalk_secret=None,
        jira_base_url="https://jira.example.invalid",
        jira_email="user@example.invalid",
        jira_api_token="jira-token",
        jira_project_key="IOS",
        log_dir=Path("logs"),
        log_level="info",
        server_name="work-assistant-mcp",
        server_instructions="",
        enabled_integrations=("jira",),
        jira_accept_transitions=("已接收", "Accept"),
        jira_resolve_transitions=("已解决", "Resolved"),
        jira_attachment_max_images=5,
        jira_attachment_max_bytes=1024,
    )
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


def test_jira_get_latest_assigned_issue_returns_issue_with_attachment_metadata() -> None:
    search_results = [
        {
            "key": "IOS-123",
            "fields": {
                "summary": "Crash on launch",
                "description": "Steps to reproduce",
                "status": {"name": "Todo"},
                "priority": {"name": "High"},
                "issuetype": {"name": "故障"},
                "updated": "2026-04-02T10:00:00.000+0800",
                "attachment": [
                    {
                        "id": "10",
                        "filename": "crash.png",
                        "mimeType": "image/png",
                        "size": 123,
                        "content": "https://jira.example.invalid/attachment/1",
                    }
                ],
            },
        }
    ]
    mcp = create_mcp(_make_settings())
    with patch(
        "work_assistant_mcp.tools.jira.client.JiraClient.search_issues",
        return_value=search_results,
    ):
        _, structured = asyncio.run(mcp.call_tool("jira_get_latest_assigned_issue", {}))

    assert structured == {
        "found": True,
        "issue": {
            "key": "IOS-123",
            "summary": "Crash on launch",
            "description": "Steps to reproduce",
            "status": "Todo",
            "priority": "High",
            "issue_type": "故障",
        },
        "attachments": [
            {
                "attachment_id": "10",
                "filename": "crash.png",
                "mime_type": "image/png",
                "size_bytes": 123,
            }
        ],
    }


def test_jira_get_attachment_image_returns_single_attachment_content() -> None:
    search_results = [
        {
            "key": "IOS-123",
            "fields": {
                "summary": "Crash on launch",
                "description": "Steps to reproduce",
                "status": {"name": "Todo"},
                "priority": {"name": "High"},
                "issuetype": {"name": "故障"},
                "assignee": {"emailAddress": "user@example.invalid"},
                "updated": "2026-04-02T10:00:00.000+0800",
                "attachment": [
                    {
                        "id": "10",
                        "filename": "crash.png",
                        "mimeType": "image/png",
                        "size": 123,
                        "content": "https://jira.example.invalid/attachment/1",
                    }
                ],
            },
        }
    ]
    mcp = create_mcp(_make_settings())
    with patch(
        "work_assistant_mcp.tools.jira.client.JiraClient.search_issues",
        return_value=search_results,
    ), patch(
        "work_assistant_mcp.tools.jira.client.JiraClient.get_current_user_identifiers",
        return_value=frozenset({"user@example.invalid"}),
    ), patch(
        "work_assistant_mcp.tools.jira.client.JiraClient.download_attachment",
        return_value=b"png-bytes",
    ):
        _, structured = asyncio.run(
            mcp.call_tool(
                "jira_get_attachment_image",
                {"issue_key": "IOS-123", "attachment_id": "10"},
            )
        )

    assert structured == {
        "success": True,
        "issue_key": "IOS-123",
        "attachment": {
            "attachment_id": "10",
            "filename": "crash.png",
            "mime_type": "image/png",
            "base64": "cG5nLWJ5dGVz",
        },
    }


def test_jira_get_attachment_image_rejects_unknown_attachment() -> None:
    search_results = [
        {
            "key": "IOS-123",
            "fields": {
                "summary": "Crash on launch",
                "description": "Steps to reproduce",
                "status": {"name": "Todo"},
                "priority": {"name": "High"},
                "issuetype": {"name": "故障"},
                "assignee": {"emailAddress": "user@example.invalid"},
                "updated": "2026-04-02T10:00:00.000+0800",
                "attachment": [],
            },
        }
    ]
    mcp = create_mcp(_make_settings())
    with patch(
        "work_assistant_mcp.tools.jira.client.JiraClient.search_issues",
        return_value=search_results,
    ), patch(
        "work_assistant_mcp.tools.jira.client.JiraClient.get_current_user_identifiers",
        return_value=frozenset({"user@example.invalid"}),
    ):
        _, structured = asyncio.run(
            mcp.call_tool(
                "jira_get_attachment_image",
                {"issue_key": "IOS-123", "attachment_id": "10"},
            )
        )

    assert structured == {
        "success": False,
        "error_type": "attachment_not_found",
        "hint": (
            "Attachment 10 was not found on IOS-123, or it is not a supported image attachment. "
            "Do not guess another attachment id. Stop and notify the user."
        ),
    }


def test_jira_accept_issue_rejects_non_todo_status() -> None:
    search_results = [
        {
            "key": "IOS-123",
            "fields": {
                "summary": "Crash on launch",
                "description": "Steps to reproduce",
                "status": {"name": "In Progress"},
                "priority": {"name": "High"},
                "issuetype": {"name": "故障"},
                "assignee": {"emailAddress": "user@example.invalid"},
                "updated": "2026-04-02T10:00:00.000+0800",
            },
        }
    ]
    mcp = create_mcp(_make_settings())
    with patch(
        "work_assistant_mcp.tools.jira.client.JiraClient.search_issues",
        return_value=search_results,
    ), patch(
        "work_assistant_mcp.tools.jira.client.JiraClient.get_current_user_identifiers",
        return_value=frozenset({"user@example.invalid"}),
    ):
        _, structured = asyncio.run(
            mcp.call_tool("jira_accept_issue", {"issue_key": "IOS-123"})
        )

    assert structured == {
        "success": False,
        "error_type": "invalid_status",
        "hint": (
            "IOS-123 is not in a Todo state and cannot be accepted. "
            "If it is already in an Accepted state, use the resolve tool instead. "
            "If still failing, stop and notify the user."
        ),
    }


def test_jira_resolve_issue_transitions_successfully() -> None:
    search_results = [
        {
            "key": "IOS-123",
            "fields": {
                "summary": "Crash on launch",
                "description": "Steps to reproduce",
                "status": {"name": "已接收"},
                "priority": {"name": "High"},
                "issuetype": {"name": "故障"},
                "assignee": {"emailAddress": "user@example.invalid"},
                "updated": "2026-04-02T10:00:00.000+0800",
            },
        }
    ]
    mcp = create_mcp(_make_settings())
    with patch(
        "work_assistant_mcp.tools.jira.client.JiraClient.search_issues",
        return_value=search_results,
    ), patch(
        "work_assistant_mcp.tools.jira.client.JiraClient.get_current_user_identifiers",
        return_value=frozenset({"user@example.invalid"}),
    ), patch(
        "work_assistant_mcp.tools.jira.client.JiraClient.get_transitions",
        return_value=[{"id": "31", "name": "已解决"}],
    ), patch(
        "work_assistant_mcp.tools.jira.client.JiraClient.transition_issue",
        return_value=None,
    ) as transition_mock:
        _, structured = asyncio.run(
            mcp.call_tool("jira_resolve_issue", {"issue_key": "IOS-123"})
        )

    transition_mock.assert_called_once_with("IOS-123", "31")
    assert structured == {"success": True, "issue_key": "IOS-123"}


def test_jira_accept_issue_rejects_write_outside_configured_project() -> None:
    search_results = [
        {
            "key": "ANDROID-123",
            "fields": {
                "summary": "Crash on launch",
                "description": "Steps to reproduce",
                "status": {"name": "Todo"},
                "priority": {"name": "High"},
                "issuetype": {"name": "故障"},
                "assignee": {"emailAddress": "user@example.invalid"},
                "updated": "2026-04-02T10:00:00.000+0800",
            },
        }
    ]
    mcp = create_mcp(_make_settings(jira_project_key="IOS"))
    with patch(
        "work_assistant_mcp.tools.jira.client.JiraClient.search_issues",
        return_value=search_results,
    ):
        _, structured = asyncio.run(
            mcp.call_tool("jira_accept_issue", {"issue_key": "ANDROID-123"})
        )

    assert structured == {
        "success": False,
        "error_type": "project_not_allowed",
        "hint": (
            "ANDROID-123 is outside the configured Jira project scope. "
            "Do not retry this write operation. Stop and notify the user."
        ),
    }


def test_jira_accept_issue_rejects_issue_not_assigned_to_current_user() -> None:
    lookup_results = [
        {
            "key": "IOS-123",
            "fields": {
                "summary": "Crash on launch",
                "description": "Steps to reproduce",
                "status": {"name": "Todo"},
                "priority": {"name": "High"},
                "issuetype": {"name": "故障"},
                "assignee": {"emailAddress": "someone-else@example.invalid"},
                "updated": "2026-04-02T10:00:00.000+0800",
            },
        }
    ]
    mcp = create_mcp(_make_settings())
    with patch(
        "work_assistant_mcp.tools.jira.client.JiraClient.search_issues",
        return_value=lookup_results,
    ), patch(
        "work_assistant_mcp.tools.jira.client.JiraClient.get_current_user_identifiers",
        return_value=frozenset({"user@example.invalid"}),
    ):
        _, structured = asyncio.run(
            mcp.call_tool("jira_accept_issue", {"issue_key": "IOS-123"})
        )

    assert structured == {
        "success": False,
        "error_type": "assignee_not_allowed",
        "hint": (
            "IOS-123 is not currently assigned to you. "
            "Do not retry this write operation unless the issue is reassigned to you. "
            "Stop and notify the user."
        ),
    }
