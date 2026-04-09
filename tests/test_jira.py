from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import patch

from work_mcp import logger
from work_mcp.config import ServerSettings, Settings, default_startup_settings
from work_mcp.server import create_mcp
from work_mcp.tools.jira.client import JiraApiError

_DEFAULT_SERVER = ServerSettings(transport="stdio", host=None, port=None)


def _make_settings(**overrides: object) -> Settings:
    defaults = dict(
        server=_DEFAULT_SERVER,
        startup=default_startup_settings(),
        dingtalk_webhook_url="https://example.invalid/webhook",
        dingtalk_secret=None,
        jira_base_url="https://jira.example.invalid",
        jira_api_token="jira-token",
        jira_project_key="IOS",
        log_dir=Path("logs"),
        log_level="info",
        enabled_plugins=("jira",),
        jira_latest_assigned_statuses=("待处理", "已接收", "处理中"),
        jira_start_target_status="已接收",
        jira_resolve_target_status="已解决",
        jira_attachment_max_images=5,
        jira_attachment_max_bytes=1024,
        log_search=None,
    )
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


def test_jira_client_uses_bearer_auth_by_default() -> None:
    from work_mcp.tools.jira.client import JiraClient

    client = JiraClient(_make_settings())

    assert client._auth_header() == "Bearer jira-token"


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
        "work_mcp.tools.jira.client.JiraClient.search_issues",
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
        "hint": (
            "If you cannot determine the root cause or the issue appears to already be resolved, "
            "stop processing, summarize your findings, tell the user in your reply, "
            "and ask the user how you should proceed."
        ),
    }


def test_jira_get_latest_assigned_issue_uses_configured_status_list_in_jql() -> None:
    service_settings = _make_settings(jira_project_key="IOS", jira_latest_assigned_statuses=("待处理", "已接收"))
    mcp = create_mcp(service_settings)
    with patch(
        "work_mcp.tools.jira.client.JiraClient.search_issues",
        return_value=[],
    ) as search_mock:
        _, structured = asyncio.run(mcp.call_tool("jira_get_latest_assigned_issue", {}))

    assert structured == {"found": False}
    search_mock.assert_called_once_with(
        jql='project = "IOS" AND assignee = currentUser() AND status in ("待处理", "已接收") ORDER BY updated DESC',
        fields=(
            "summary",
            "description",
            "status",
            "priority",
            "issuetype",
            "assignee",
            "attachment",
            "updated",
        ),
        max_results=1,
    )


def test_jira_get_attachment_image_returns_single_attachment_content() -> None:
    issue_payload = {
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
    mcp = create_mcp(_make_settings())
    with patch(
        "work_mcp.tools.jira.client.JiraClient.get_issue",
        return_value=issue_payload,
    ), patch(
        "work_mcp.tools.jira.client.JiraClient.get_current_user_identifiers",
        return_value=frozenset({"user@example.invalid"}),
    ), patch(
        "work_mcp.tools.jira.client.JiraClient.download_attachment",
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


def test_jira_get_attachment_image_log_truncates_large_base64(tmp_path: Path) -> None:
    issue_payload = {
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
    logger.configure(log_dir=tmp_path, level="info")
    mcp = create_mcp(_make_settings(log_dir=tmp_path))
    with patch(
        "work_mcp.tools.jira.client.JiraClient.get_issue",
        return_value=issue_payload,
    ), patch(
        "work_mcp.tools.jira.client.JiraClient.get_current_user_identifiers",
        return_value=frozenset({"user@example.invalid"}),
    ), patch(
        "work_mcp.tools.jira.client.JiraClient.download_attachment",
        return_value=b"a" * 800,
    ):
        _, structured = asyncio.run(
            mcp.call_tool(
                "jira_get_attachment_image",
                {"issue_key": "IOS-123", "attachment_id": "10"},
            )
        )

    assert structured["success"] is True
    files = list(tmp_path.glob("*.info.log"))
    assert len(files) == 1
    records = [
        json.loads(line)
        for line in files[0].read_text(encoding="utf-8").splitlines()
    ]
    completed = next(record for record in records if record["topic"] == "tool.completed")
    base64_field = completed["data"]["result"]["attachment"]["base64"]
    assert isinstance(base64_field, str)
    assert len(base64_field) == 1000
    assert "...<truncated>..." in base64_field


def test_jira_get_attachment_image_rejects_unknown_attachment() -> None:
    issue_payload = {
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
    mcp = create_mcp(_make_settings())
    with patch(
        "work_mcp.tools.jira.client.JiraClient.get_issue",
        return_value=issue_payload,
    ), patch(
        "work_mcp.tools.jira.client.JiraClient.get_current_user_identifiers",
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
            "Do not guess another attachment id. "
            "Stop, tell the user in your reply, and ask the user how you should proceed."
        ),
    }


def test_jira_get_latest_assigned_issue_returns_clean_message_for_auth_failure() -> None:
    mcp = create_mcp(_make_settings())
    with patch(
        "work_mcp.tools.jira.client.JiraClient.search_issues",
        side_effect=JiraApiError(
            "Jira request failed with HTTP 401: authentication failed",
            status_code=401,
        ),
    ):
        _, structured = asyncio.run(mcp.call_tool("jira_get_latest_assigned_issue", {}))

    assert structured == {
        "success": False,
        "error_type": "internal_error",
        "message": (
            "Jira authentication failed while fetching the latest assigned issue (HTTP 401). "
            "Check JIRA_BASE_URL and JIRA_API_TOKEN."
        ),
        "hint": (
            "An internal error occurred. Retry up to 2 times; "
            "if still failing, stop and notify the user with the message above."
        ),
    }


def test_jira_get_latest_assigned_issue_returns_generic_message_for_non_auth_http_error() -> None:
    mcp = create_mcp(_make_settings())
    with patch(
        "work_mcp.tools.jira.client.JiraClient.search_issues",
        side_effect=JiraApiError(
            "Jira request failed with HTTP 500: internal server error",
            status_code=500,
        ),
    ):
        _, structured = asyncio.run(mcp.call_tool("jira_get_latest_assigned_issue", {}))

    assert structured == {
        "success": False,
        "error_type": "internal_error",
        "message": "Error while fetching the latest assigned issue: Jira request failed with HTTP 500: internal server error",
        "hint": (
            "An internal error occurred. Retry up to 2 times; "
            "if still failing, stop and notify the user with the message above."
        ),
    }


def test_jira_start_issue_returns_transition_not_available_with_current_context() -> None:
    issue_payload = {
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
    mcp = create_mcp(_make_settings())
    with patch(
        "work_mcp.tools.jira.client.JiraClient.get_issue",
        return_value=issue_payload,
    ), patch(
        "work_mcp.tools.jira.client.JiraClient.get_current_user_identifiers",
        return_value=frozenset({"user@example.invalid"}),
    ), patch(
        "work_mcp.tools.jira.client.JiraClient.get_transitions",
        return_value=[
            {"id": "41", "name": "Resolve", "to": {"name": "已解决"}},
            {"id": "42", "name": "Close", "to": {"name": "Closed"}},
        ],
    ):
        _, structured = asyncio.run(
            mcp.call_tool("jira_start_issue", {"issue_key": "IOS-123"})
        )

    assert structured == {
        "success": False,
        "error_type": "transition_not_available",
        "message": "Could not start IOS-123 because no available Jira transition reaches 已接收.",
        "current_status": "In Progress",
        "target_status": "已接收",
        "available_statuses": ["已解决", "Closed"],
        "hint": (
            "The Jira workflow change could not be completed. Stop execution, summarize what you completed, "
            "tell the user in your reply with the current status, target status, and available target statuses, "
            "and ask the user how you should proceed."
        ),
    }


def test_jira_start_issue_transitions_by_target_status() -> None:
    issue_payload = {
        "key": "IOS-123",
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
    mcp = create_mcp(_make_settings())
    with patch(
        "work_mcp.tools.jira.client.JiraClient.get_issue",
        return_value=issue_payload,
    ), patch(
        "work_mcp.tools.jira.client.JiraClient.get_current_user_identifiers",
        return_value=frozenset({"user@example.invalid"}),
    ), patch(
        "work_mcp.tools.jira.client.JiraClient.get_transitions",
        return_value=[
            {"id": "21", "name": "Start Progress", "to": {"name": "进行中"}},
            {"id": "22", "name": "Accept", "to": {"name": "已接收"}},
        ],
    ), patch(
        "work_mcp.tools.jira.client.JiraClient.transition_issue",
        return_value=None,
    ) as transition_mock:
        _, structured = asyncio.run(
            mcp.call_tool("jira_start_issue", {"issue_key": "IOS-123"})
        )

    transition_mock.assert_called_once_with("IOS-123", "22")
    assert structured == {"success": True, "issue_key": "IOS-123", "target_status": "已接收"}


def test_jira_resolve_issue_transitions_successfully() -> None:
    issue_payload = {
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
    mcp = create_mcp(_make_settings())
    with patch(
        "work_mcp.tools.jira.client.JiraClient.get_issue",
        return_value=issue_payload,
    ), patch(
        "work_mcp.tools.jira.client.JiraClient.get_current_user_identifiers",
        return_value=frozenset({"user@example.invalid"}),
    ), patch(
        "work_mcp.tools.jira.client.JiraClient.get_transitions",
        return_value=[{"id": "31", "name": "Resolve", "to": {"name": "已解决"}}],
    ), patch(
        "work_mcp.tools.jira.client.JiraClient.transition_issue",
        return_value=None,
    ) as transition_mock:
        _, structured = asyncio.run(
            mcp.call_tool("jira_resolve_issue", {"issue_key": "IOS-123"})
        )

    transition_mock.assert_called_once_with("IOS-123", "31")
    assert structured == {"success": True, "issue_key": "IOS-123", "target_status": "已解决"}


def test_jira_resolve_issue_rejects_ambiguous_target_status() -> None:
    issue_payload = {
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
    mcp = create_mcp(_make_settings())
    with patch(
        "work_mcp.tools.jira.client.JiraClient.get_issue",
        return_value=issue_payload,
    ), patch(
        "work_mcp.tools.jira.client.JiraClient.get_current_user_identifiers",
        return_value=frozenset({"user@example.invalid"}),
    ), patch(
        "work_mcp.tools.jira.client.JiraClient.get_transitions",
        return_value=[
            {"id": "31", "name": "Resolve", "to": {"name": "已解决"}},
            {"id": "32", "name": "Fast Resolve", "to": {"name": "已解决"}},
        ],
    ):
        _, structured = asyncio.run(
            mcp.call_tool("jira_resolve_issue", {"issue_key": "IOS-123"})
        )

    assert structured == {
        "success": False,
        "error_type": "transition_ambiguous",
        "message": "Could not resolve IOS-123 because multiple available Jira transitions reach 已解决.",
        "current_status": "已接收",
        "target_status": "已解决",
        "available_statuses": ["已解决"],
        "matching_transition_names": ["Resolve", "Fast Resolve"],
        "hint": (
            "The Jira workflow change could not be completed. Stop execution, summarize what you completed, "
            "tell the user in your reply with the current status, target status, and available target statuses, "
            "and ask the user how you should proceed."
        ),
    }


def test_jira_start_issue_rejects_write_outside_configured_project() -> None:
    issue_payload = {
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
    mcp = create_mcp(_make_settings(jira_project_key="IOS"))
    with patch(
        "work_mcp.tools.jira.client.JiraClient.get_issue",
        return_value=issue_payload,
    ):
        _, structured = asyncio.run(
            mcp.call_tool("jira_start_issue", {"issue_key": "ANDROID-123"})
        )

    assert structured == {
        "success": False,
        "error_type": "project_not_allowed",
        "hint": (
            "ANDROID-123 is outside the configured Jira project scope. "
            "Do not retry this write operation. "
            "Stop, tell the user in your reply, and ask the user how you should proceed."
        ),
    }



def test_jira_start_issue_rejects_issue_not_assigned_to_current_user() -> None:
    issue_payload = {
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
    mcp = create_mcp(_make_settings())
    with patch(
        "work_mcp.tools.jira.client.JiraClient.get_issue",
        return_value=issue_payload,
    ), patch(
        "work_mcp.tools.jira.client.JiraClient.get_current_user_identifiers",
        return_value=frozenset({"user@example.invalid"}),
    ):
        _, structured = asyncio.run(
            mcp.call_tool("jira_start_issue", {"issue_key": "IOS-123"})
        )

    assert structured == {
        "success": False,
        "error_type": "assignee_not_allowed",
        "hint": (
            "IOS-123 is not currently assigned to you. "
            "Do not retry this write operation unless the issue is reassigned to you. "
            "Stop, tell the user in your reply, and ask the user how you should proceed."
        ),
    }
