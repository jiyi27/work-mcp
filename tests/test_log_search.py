from __future__ import annotations

import asyncio
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
        ),
    )
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


# --- list_log_files ---

def test_list_log_files_lists_root_when_path_omitted(tmp_path: Path) -> None:
    root = tmp_path / "services"
    (root / "api").mkdir(parents=True)
    (root / "worker").mkdir(parents=True)
    mcp = create_mcp(_make_settings(tmp_path))

    _, structured = asyncio.run(mcp.call_tool("list_log_files", {}))

    assert structured["success"] is True
    assert structured["path"] == ""
    assert [entry["name"] for entry in structured["entries"]] == ["api", "worker"]
    assert structured["hint"] == (
        "The result shows one level of the log directory tree for the returned path. "
        "Continue calling list_log_files with a directory path to drill down. "
        "Use search_log only after you identify a file to search."
    )


def test_list_log_files_rejects_path_traversal(tmp_path: Path) -> None:
    mcp = create_mcp(_make_settings(tmp_path))

    _, structured = asyncio.run(
        mcp.call_tool("list_log_files", {"path": "../../etc"})
    )

    assert structured == {
        "success": False,
        "error_type": "path_outside_base",
        "hint": "The path resolves outside the configured log directory. Stop and tell the user in your reply.",
    }


def test_list_log_files_returns_entries_with_path_and_limits_files(tmp_path: Path) -> None:
    service_dir = tmp_path / "services" / "api" / "2026-04-08"
    service_dir.mkdir(parents=True)
    for index in range(12):
        file_path = service_dir / f"app-{index:02d}.log"
        file_path.write_text("log line\n", encoding="utf-8")
        file_path.touch()
    mcp = create_mcp(_make_settings(tmp_path))

    _, structured = asyncio.run(
        mcp.call_tool("list_log_files", {"path": "api"})
    )

    assert structured["success"] is True
    assert structured["path"] == "api"
    names = [e["name"] for e in structured["entries"]]
    assert "2026-04-08" in names
    dir_entry = next(e for e in structured["entries"] if e["name"] == "2026-04-08")
    assert dir_entry["type"] == "dir"
    assert dir_entry["path"] == "api/2026-04-08"

    _, nested = asyncio.run(
        mcp.call_tool("list_log_files", {"path": "api/2026-04-08"})
    )

    assert nested["success"] is True
    assert nested["path"] == "api/2026-04-08"
    assert len(nested["entries"]) == 10
    assert all(entry["type"] == "file" for entry in nested["entries"])
    assert nested["entries"][0]["name"] == "app-11.log"


# --- search_log ---

def test_search_log_rejects_empty_file_path(tmp_path: Path) -> None:
    mcp = create_mcp(_make_settings(tmp_path))

    _, structured = asyncio.run(
        mcp.call_tool("search_log", {"file_path": " ", "query": "error"})
    )

    assert structured == {
        "success": False,
        "error_type": "invalid_input",
        "hint": "`file_path` must not be empty. Fix the parameter and retry.",
    }

def test_search_log_rejects_path_traversal_outside_base(tmp_path: Path) -> None:
    mcp = create_mcp(_make_settings(tmp_path))

    _, structured = asyncio.run(
        mcp.call_tool("search_log", {"file_path": "../../etc/passwd", "query": "root"})
    )

    assert structured["success"] is False
    assert structured["error_type"] == "path_outside_base"


def test_search_log_rejects_path_outside_base_within_valid_service(tmp_path: Path) -> None:
    mcp = create_mcp(_make_settings(tmp_path))

    _, structured = asyncio.run(
        mcp.call_tool("search_log", {"file_path": "api/../../../etc/passwd", "query": "root"})
    )

    assert structured["success"] is False
    assert structured["error_type"] == "path_outside_base"


def test_search_log_returns_no_results_with_hint(tmp_path: Path) -> None:
    log_dir = tmp_path / "services" / "api"
    log_dir.mkdir(parents=True)
    (log_dir / "app.log").write_text("no match here\n", encoding="utf-8")
    mcp = create_mcp(_make_settings(tmp_path))

    _, structured = asyncio.run(
        mcp.call_tool("search_log", {"file_path": "api/app.log", "query": "trace-123"})
    )

    assert structured["success"] is True
    assert structured["results"] == []
    assert "hint" in structured


def test_search_log_returns_matching_lines_with_context(tmp_path: Path) -> None:
    log_dir = tmp_path / "services" / "api"
    log_dir.mkdir(parents=True)
    lines = ["line one", "line two", "ERROR trace-123 failed", "line four", "line five"]
    (log_dir / "app.log").write_text("\n".join(lines), encoding="utf-8")
    mcp = create_mcp(_make_settings(tmp_path))

    _, structured = asyncio.run(
        mcp.call_tool("search_log", {"file_path": "api/app.log", "query": "trace-123"})
    )

    assert structured["success"] is True
    assert len(structured["results"]) == 1
    result = structured["results"][0]
    assert result["line_no"] == 3
    assert "trace-123" in result["match"]
    assert "line two" in result["pre_context"]
    assert "line four" in result["post_context"]
