from __future__ import annotations

import asyncio
import os
from pathlib import Path

from work_mcp.config import LogSearchSettings, ServerSettings, Settings
from work_mcp.server import create_mcp
from work_mcp.tools.log_search.constants import MAX_FILE_SIZE_BYTES, MAX_RESULTS

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
        server_name="work-mcp",
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
    api_dir = root / "api"
    worker_dir = root / "worker"
    api_dir.mkdir(parents=True)
    worker_dir.mkdir(parents=True)
    os.utime(api_dir, (1_700_000_000, 1_700_000_000))
    os.utime(worker_dir, (1_700_000_100, 1_700_000_100))
    mcp = create_mcp(_make_settings(tmp_path))

    _, structured = asyncio.run(mcp.call_tool("list_log_files", {}))

    assert structured["success"] is True
    assert structured["path"] == ""
    assert [entry["name"] for entry in structured["entries"]] == ["worker", "api"]
    assert structured["hint"] == (
        "Results are capped at 10 entries, sorted by most recently modified — "
        "older entries may not appear. To drill into a subdirectory, pass its entry's `path` field "
        "to list_log_files."
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


def test_list_log_files_returns_path_rules_when_path_not_found(tmp_path: Path) -> None:
    mcp = create_mcp(_make_settings(tmp_path))

    _, structured = asyncio.run(
        mcp.call_tool("list_log_files", {"path": "api/missing"})
    )

    assert structured == {
        "success": False,
        "error_type": "path_not_found",
        "hint": (
            "Path 'api/missing' does not exist. Verify the path is correct. Paths passed to "
            "list_log_files must be relative to the log root — do not use absolute paths or "
            "guess paths manually. Call list_log_files with path=\"\" to browse from the log "
            "root, then pass the returned directory `path` value directly."
        ),
    }


def test_list_log_files_returns_entries_with_path_and_limits_total_entries(tmp_path: Path) -> None:
    service_dir = tmp_path / "services" / "api" / "2026-04-08"
    service_dir.mkdir(parents=True)
    older_dir = tmp_path / "services" / "api" / "2026-04-07"
    older_dir.mkdir(parents=True)
    for index in range(12):
        file_path = service_dir / f"app-{index:02d}.log"
        file_path.write_text("log line\n", encoding="utf-8")
        timestamp = 1_700_000_000 + index
        os.utime(file_path, (timestamp, timestamp))
    older_timestamp = 1_600_000_000
    os.utime(older_dir, (older_timestamp, older_timestamp))
    mcp = create_mcp(_make_settings(tmp_path))

    _, structured = asyncio.run(
        mcp.call_tool("list_log_files", {"path": "api"})
    )

    assert structured["success"] is True
    assert structured["path"] == "api"
    assert [entry["name"] for entry in structured["entries"]] == ["2026-04-08", "2026-04-07"]
    assert structured["entries"][0]["type"] == "dir"
    assert structured["entries"][0]["path"] == "api/2026-04-08"
    assert "mtime" in structured["entries"][0]

    _, nested = asyncio.run(
        mcp.call_tool("list_log_files", {"path": "api/2026-04-08"})
    )

    assert nested["success"] is True
    assert nested["path"] == "api/2026-04-08"
    assert len(nested["entries"]) == 10
    assert all(entry["type"] == "file" for entry in nested["entries"])
    assert nested["entries"][0]["name"] == "app-11.log"
    assert nested["entries"][-1]["name"] == "app-02.log"


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
    assert result["pre_context"] == ["line one", "line two"]
    assert result["post_context"] == ["line four", "line five"]


def test_search_log_returns_most_recent_matches_first_then_sorts_output(tmp_path: Path) -> None:
    log_dir = tmp_path / "services" / "api"
    log_dir.mkdir(parents=True)
    lines = [
        "trace-123 first",
        "middle one",
        "trace-123 second",
        "middle two",
        "trace-123 third",
    ]
    (log_dir / "app.log").write_text("\n".join(lines), encoding="utf-8")
    mcp = create_mcp(_make_settings(tmp_path))

    _, structured = asyncio.run(
        mcp.call_tool("search_log", {"file_path": "api/app.log", "query": "TRACE-123"})
    )

    assert structured["success"] is True
    assert [result["line_no"] for result in structured["results"]] == [1, 3, 5]
    assert structured["results"][-1]["pre_context"] == ["middle one", "trace-123 second", "middle two"]
    assert structured["results"][0]["post_context"] == ["middle one", "trace-123 second", "middle two"]


def test_search_log_truncates_to_most_recent_matches(tmp_path: Path) -> None:
    log_dir = tmp_path / "services" / "api"
    log_dir.mkdir(parents=True)
    lines = [f"trace-123 line {index}" for index in range(MAX_RESULTS + 2)]
    (log_dir / "app.log").write_text("\n".join(lines), encoding="utf-8")
    mcp = create_mcp(_make_settings(tmp_path))

    _, structured = asyncio.run(
        mcp.call_tool("search_log", {"file_path": "api/app.log", "query": "trace-123"})
    )

    assert structured["success"] is True
    assert structured["truncated"] is True
    assert len(structured["results"]) == MAX_RESULTS
    assert [result["line_no"] for result in structured["results"]] == list(range(3, MAX_RESULTS + 3))
    assert structured["hint"] == (
        "Showing the 10 most recent matches. Older occurrences may exist but are not shown. "
        "Use a more specific query to narrow results. If completeness is critical, inform the user "
        "that this tool may not have captured all matches."
    )


def test_search_log_rejects_file_that_is_too_large(tmp_path: Path) -> None:
    log_dir = tmp_path / "services" / "api"
    log_dir.mkdir(parents=True)
    oversized = log_dir / "app.log"
    with oversized.open("wb") as file_obj:
        file_obj.truncate(MAX_FILE_SIZE_BYTES + 1)
    mcp = create_mcp(_make_settings(tmp_path))

    _, structured = asyncio.run(
        mcp.call_tool("search_log", {"file_path": "api/app.log", "query": "trace-123"})
    )

    assert structured == {
        "success": False,
        "error_type": "file_too_large",
        "hint": (
            "This file exceeds the tool's size limit (50 MB) and cannot be searched directly. "
            "Notify the user — they may need to search the file outside this tool (e.g. grep on the server)."
        ),
    }
