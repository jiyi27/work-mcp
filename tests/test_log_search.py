from __future__ import annotations

import asyncio
import json
from pathlib import Path

from work_assistant_mcp.config import LogSearchSettings, ServerSettings, Settings
from work_assistant_mcp.server import create_mcp

_DEFAULT_SERVER = ServerSettings(transport="stdio", host=None, port=None)


def _make_settings(tmp_path: Path, **overrides: object) -> Settings:
    defaults = dict(
        server=_DEFAULT_SERVER,
        dingtalk_webhook_url="https://example.invalid/webhook",
        dingtalk_secret=None,
        jira_base_url="https://jira.example.invalid",
        jira_api_token="jira-token",
        jira_project_key="IOS",
        log_dir=tmp_path / "logs",
        log_level="info",
        server_name="work-assistant-mcp",
        server_instructions="",
        enabled_plugins=("log_search",),
        jira_latest_assigned_statuses=("待处理", "已接收", "处理中"),
        jira_start_target_status="已接收",
        jira_resolve_target_status="已解决",
        jira_attachment_max_images=5,
        jira_attachment_max_bytes=1024,
        log_search=LogSearchSettings(
            log_base_dir=str(tmp_path / "services"),
            file_pattern="current.log",
            levels=(),
            services=("api",),
        ),
    )
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


def test_log_search_rejects_empty_service(tmp_path: Path) -> None:
    mcp = create_mcp(_make_settings(tmp_path))

    _, structured = asyncio.run(
        mcp.call_tool("search_logs", {"service": " ", "query": "trace-123"})
    )

    assert structured == {
        "success": False,
        "error_type": "invalid_input",
        "hint": "`service` must not be empty. Fix the parameter and retry.",
    }


def test_log_search_rejects_non_positive_limit(tmp_path: Path) -> None:
    mcp = create_mcp(_make_settings(tmp_path))

    _, structured = asyncio.run(
        mcp.call_tool("search_logs", {"service": "api", "query": "trace-123", "limit": 0})
    )

    assert structured == {
        "success": False,
        "error_type": "invalid_input",
        "hint": "`limit` must be greater than 0. Fix the parameter and retry.",
    }


def test_log_search_rejects_unknown_service_with_recoverable_hint(tmp_path: Path) -> None:
    mcp = create_mcp(_make_settings(tmp_path))

    _, structured = asyncio.run(
        mcp.call_tool("search_logs", {"service": "worker", "query": "trace-123"})
    )

    assert structured == {
        "success": False,
        "error_type": "invalid_service",
        "hint": (
            "The service name is not recognized. "
            "Call list_log_services to get valid names, then retry with the correct service."
        ),
    }


def test_log_search_returns_stop_hint_when_no_services_are_configured(tmp_path: Path) -> None:
    mcp = create_mcp(
        _make_settings(
            tmp_path,
            log_search=LogSearchSettings(
                log_base_dir=str(tmp_path / "services"),
                file_pattern="current.log",
                levels=(),
                services=(),
            ),
        )
    )

    _, structured = asyncio.run(mcp.call_tool("list_log_services", {}))

    assert structured == {
        "success": False,
        "error_type": "no_services_configured",
        "hint": (
            "No log services are configured. "
            "Stop, tell the user in your reply, and ask the user how you should proceed."
        ),
    }


def test_log_search_returns_empty_results_with_recovery_hint(tmp_path: Path) -> None:
    log_dir = tmp_path / "services" / "api"
    log_dir.mkdir(parents=True)
    (log_dir / "current.log").write_text(
        json.dumps({"time": "2026-04-07T10:00:00Z", "message": "different trace"}) + "\n",
        encoding="utf-8",
    )
    mcp = create_mcp(_make_settings(tmp_path))

    _, structured = asyncio.run(
        mcp.call_tool("search_logs", {"service": "api", "query": "trace-123"})
    )

    assert structured == {
        "success": True,
        "results": [],
        "hint": (
            "No matching log entries found. "
            "Try a different query string, or call list_log_services to verify the service name."
        ),
    }
