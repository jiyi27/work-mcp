from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
from pathlib import Path
from unittest.mock import patch

from urllib.parse import parse_qs, urlsplit

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
        enabled_integrations=("dingtalk",),
        jira_accept_transitions=("已接收", "Accept"),
        jira_resolve_transitions=("已解决", "Resolved"),
        jira_attachment_max_images=5,
        jira_attachment_max_bytes=1_048_576,
    )
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


class FakeResponse:
    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False

    def read(self) -> bytes:
        return b'{"errcode":0,"errmsg":"ok"}'


def test_list_tools_includes_dingtalk_send_markdown() -> None:
    mcp = create_mcp(_make_settings())
    tools = asyncio.run(mcp.list_tools())

    assert [tool.name for tool in tools] == ["dingtalk_send_markdown"]


def test_dingtalk_send_markdown_returns_structured_result() -> None:
    mcp = create_mcp(_make_settings())
    with patch("work_assistant_mcp.tools.dingtalk.urlopen", return_value=FakeResponse()):
        _, structured = asyncio.run(
            mcp.call_tool(
                "dingtalk_send_markdown",
                {"title": "Smoke Test", "markdown": "hello"},
            )
        )

    assert structured == {"success": True}


def test_dingtalk_send_markdown_writes_success_log(tmp_path: Path) -> None:
    mcp = create_mcp(_make_settings(log_dir=tmp_path))
    with patch("work_assistant_mcp.tools.dingtalk.urlopen", return_value=FakeResponse()):
        with patch.dict(
            "os.environ",
            {
                "DINGTALK_WEBHOOK_URL": "https://example.invalid/webhook",
                "WORK_ASSISTANT_LOG_DIR": str(tmp_path),
                "WORK_ASSISTANT_LOG_LEVEL": "info",
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
    assert record["topic"] == "dingtalk.sent"


def test_dingtalk_send_markdown_signs_webhook_when_secret_is_configured() -> None:
    captured_request = None

    def fake_urlopen(request: object, timeout: int) -> FakeResponse:
        nonlocal captured_request
        captured_request = request
        return FakeResponse()

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

    with patch("work_assistant_mcp.tools.dingtalk.urlopen", side_effect=fake_urlopen):
        with patch("work_assistant_mcp.tools.dingtalk.time.time", return_value=fixed_timestamp_ms / 1000):
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
    assert captured_request is not None
    query = parse_qs(urlsplit(captured_request.full_url).query)
    assert query["access_token"] == ["test-token"]
    assert query["timestamp"] == [str(fixed_timestamp_ms)]
    assert query["sign"] == [expected_sign]


def test_enabled_integrations_controls_which_tools_are_registered() -> None:
    mcp_empty = create_mcp(_make_settings(enabled_integrations=()))
    tools = asyncio.run(mcp_empty.list_tools())
    assert tools == []

    mcp_with_dingtalk = create_mcp(
        _make_settings(enabled_integrations=("dingtalk",))
    )
    tools = asyncio.run(mcp_with_dingtalk.list_tools())
    assert [t.name for t in tools] == ["dingtalk_send_markdown"]


def test_enabled_integrations_can_register_jira_only() -> None:
    mcp = create_mcp(_make_settings(enabled_integrations=("jira",)))
    tools = asyncio.run(mcp.list_tools())
    assert [tool.name for tool in tools] == [
        "jira_get_current_fault",
        "jira_accept_issue",
        "jira_resolve_issue",
    ]
