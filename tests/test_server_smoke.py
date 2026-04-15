from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
from pathlib import Path
from unittest.mock import patch

from urllib.parse import parse_qs, urlsplit

from work_mcp.config import (
    AllowedRoot,
    RemoteFsSettings,
    ServerSettings,
    Settings,
    default_startup_settings,
)
from work_mcp.server import _apply_cli_overrides, create_mcp, main
from work_mcp.tools.jira.strings import (
    JIRA_GET_ISSUE_DETAILS_TOOL_NAME,
    JIRA_LIST_OPEN_ASSIGNED_ISSUES_TOOL_NAME,
    JIRA_RESOLVE_ISSUE_TOOL_NAME,
    JIRA_START_ISSUE_TOOL_NAME,
)

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
        enabled_plugins=("dingtalk",),
        jira_latest_assigned_statuses=("待处理", "已接收", "处理中"),
        jira_start_target_status="已接收",
        jira_resolve_target_status="已解决",
        jira_attachment_max_images=5,
        jira_attachment_max_bytes=1_048_576,
        log_search=None,
        database=None,
    )
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


class FakeResponse:
    pass


def test_list_tools_includes_dingtalk_send_markdown() -> None:
    mcp = create_mcp(_make_settings())
    tools = asyncio.run(mcp.list_tools())

    assert [tool.name for tool in tools] == ["dingtalk_send_markdown"]


def test_dingtalk_send_markdown_returns_structured_result() -> None:
    mcp = create_mcp(_make_settings())
    with patch(
        "work_mcp.tools.dingtalk.request_json",
        return_value={"errcode": 0, "errmsg": "ok"},
    ):
        _, structured = asyncio.run(
            mcp.call_tool(
                "dingtalk_send_markdown",
                {"title": "Smoke Test", "markdown": "hello"},
            )
        )

    assert structured == {"success": True}


def test_dingtalk_send_markdown_writes_success_log(tmp_path: Path) -> None:
    mcp = create_mcp(_make_settings(log_dir=tmp_path))
    with patch(
        "work_mcp.tools.dingtalk.request_json",
        return_value={"errcode": 0, "errmsg": "ok"},
    ):
        with patch.dict(
            "os.environ",
            {
                "DINGTALK_WEBHOOK_URL": "https://example.invalid/webhook",
            },
            clear=False,
        ):
            _, structured = asyncio.run(
                mcp.call_tool(
                    "dingtalk_send_markdown",
                    {"title": "Smoke Test", "markdown": "hello"},
                )
            )

    assert structured == {"success": True}
    files = list(tmp_path.glob("*.info.log"))
    assert len(files) == 1
    record = json.loads(files[0].read_text(encoding="utf-8").splitlines()[0])
    assert record["topic"] == "tool.response"
    assert record["data"]["tool"] == "dingtalk_send_markdown"


def test_dingtalk_send_markdown_signs_webhook_when_secret_is_configured() -> None:
    captured_kwargs: dict[str, object] | None = None

    def fake_request_json(**kwargs: object) -> dict[str, object]:
        nonlocal captured_kwargs
        captured_kwargs = kwargs
        return {"errcode": 0, "errmsg": "ok"}

    fixed_timestamp_ms = 1_712_345_678_900
    secret = "SECtest-secret"
    string_to_sign = f"{fixed_timestamp_ms}\n{secret}".encode("utf-8")
    expected_sign = base64.b64encode(
        hmac.new(secret.encode("utf-8"), string_to_sign, hashlib.sha256).digest()
    ).decode("utf-8")

    mcp = create_mcp(
        _make_settings(
            dingtalk_webhook_url="https://example.invalid/webhook?access_token=test-token",
            dingtalk_secret=secret,
        )
    )

    with patch("work_mcp.tools.dingtalk.request_json", side_effect=fake_request_json):
        with patch("work_mcp.tools.dingtalk.time.time", return_value=fixed_timestamp_ms / 1000):
            with patch.dict(
                "os.environ",
                {
                    "DINGTALK_WEBHOOK_URL": "https://example.invalid/webhook?access_token=test-token",
                    "DINGTALK_SECRET": secret,
                },
                clear=False,
            ):
                _, structured = asyncio.run(
                    mcp.call_tool(
                        "dingtalk_send_markdown",
                        {"title": "Smoke Test", "markdown": "hello"},
                    )
                )

    assert structured == {"success": True}
    assert captured_kwargs is not None
    query = parse_qs(urlsplit(str(captured_kwargs["url"])).query)
    assert query["access_token"] == ["test-token"]
    assert query["timestamp"] == [str(fixed_timestamp_ms)]
    assert query["sign"] == [expected_sign]


def test_dingtalk_send_markdown_returns_clean_message_for_http_failure() -> None:
    from work_mcp.http import HttpRequestError

    mcp = create_mcp(_make_settings())
    with patch(
        "work_mcp.tools.dingtalk.request_json",
        side_effect=HttpRequestError(
            "DingTalk request failed with HTTP 500: unknown upstream error",
            status_code=500,
        ),
    ):
        _, structured = asyncio.run(
            mcp.call_tool(
                "dingtalk_send_markdown",
                {"title": "Smoke Test", "markdown": "hello"},
            )
        )

    assert structured == {
        "success": False,
        "error_type": "internal_error",
        "message": "Error while sending the webhook message: DingTalk request failed with HTTP 500: unknown upstream error",
        "hint": "An internal error occurred. Stop and tell the user in your reply: the notification could not be sent.",
    }


def test_enabled_plugins_controls_which_tools_are_registered() -> None:
    mcp_empty = create_mcp(_make_settings(enabled_plugins=()))
    tools = asyncio.run(mcp_empty.list_tools())
    assert tools == []

    mcp_with_dingtalk = create_mcp(
        _make_settings(enabled_plugins=("dingtalk",))
    )
    tools = asyncio.run(mcp_with_dingtalk.list_tools())
    assert [t.name for t in tools] == ["dingtalk_send_markdown"]


def test_enabled_plugins_can_register_jira_only() -> None:
    mcp = create_mcp(_make_settings(enabled_plugins=("jira",)))
    tools = asyncio.run(mcp.list_tools())
    assert [tool.name for tool in tools] == [
        JIRA_LIST_OPEN_ASSIGNED_ISSUES_TOOL_NAME,
        JIRA_GET_ISSUE_DETAILS_TOOL_NAME,
        JIRA_START_ISSUE_TOOL_NAME,
        JIRA_RESOLVE_ISSUE_TOOL_NAME,
    ]


def test_enabled_plugins_can_register_remote_fs_with_remote_prefixed_names(
    tmp_path: Path,
) -> None:
    remote_root = tmp_path / "remote-root"
    remote_root.mkdir()
    mcp = create_mcp(
        _make_settings(
            enabled_plugins=("remote_fs",),
            remote_fs=RemoteFsSettings(
                roots=(
                    AllowedRoot(
                        name="app",
                        path=remote_root,
                        kind="remote",
                        description="Remote application root",
                    ),
                )
            ),
        )
    )

    tools = asyncio.run(mcp.list_tools())

    assert [tool.name for tool in tools] == [
        "remote_describe_environment",
        "remote_list_tree",
        "remote_search_files",
        "remote_read_file",
        "remote_search_file_reverse",
    ]


def test_apply_cli_overrides_can_switch_to_http_mode() -> None:
    settings = _apply_cli_overrides(
        _make_settings(),
        transport="streamable-http",
        host="127.0.0.1",
        port=9000,
    )

    assert settings.server == ServerSettings(
        transport="streamable-http",
        host="127.0.0.1",
        port=9000,
    )


def test_apply_cli_overrides_clears_network_binding_for_stdio() -> None:
    settings = _apply_cli_overrides(
        _make_settings(
            server=ServerSettings(
                transport="streamable-http",
                host="127.0.0.1",
                port=9000,
            )
        ),
        transport="stdio",
        host="0.0.0.0",
        port=8182,
    )

    assert settings.server == ServerSettings(
        transport="stdio",
        host=None,
        port=None,
    )


def test_main_exits_cleanly_for_invalid_configuration(monkeypatch) -> None:
    monkeypatch.setattr(
        "work_mcp.server.get_settings",
        lambda: (_ for _ in ()).throw(RuntimeError("Invalid configuration for enabled plugins")),
    )

    try:
        main([])
    except SystemExit as exc:
        assert exc.code == "Error: Invalid configuration for enabled plugins"
    else:
        raise AssertionError("Expected SystemExit")


def test_main_exits_cleanly_for_failed_startup_checks(monkeypatch) -> None:
    monkeypatch.setattr("work_mcp.server.get_settings", lambda: _make_settings())
    monkeypatch.setattr(
        "work_mcp.server.run_startup_checks",
        lambda _settings: (_ for _ in ()).throw(
            RuntimeError("Startup dependency checks failed:\n- jira: connectivity check failed")
        ),
    )

    try:
        main([])
    except SystemExit as exc:
        assert exc.code == "Error: Startup dependency checks failed:\n- jira: connectivity check failed"
    else:
        raise AssertionError("Expected SystemExit")


def test_main_exits_cleanly_for_yaml_syntax_errors(monkeypatch) -> None:
    monkeypatch.setattr(
        "work_mcp.server.get_settings",
        lambda: (_ for _ in ()).throw(
            RuntimeError(
                "Invalid config.yaml at /tmp/config.yaml: YAML syntax error at line 12, column 3: could not find expected ':'"
            )
        ),
    )

    try:
        main([])
    except SystemExit as exc:
        assert (
            exc.code
            == "Error: Invalid config.yaml at /tmp/config.yaml: YAML syntax error at line 12, column 3: could not find expected ':'"
        )
    else:
        raise AssertionError("Expected SystemExit")
