from __future__ import annotations

from pathlib import Path

import work_mcp.startup_checks as startup_checks_module
from work_mcp.config import (
    DatabaseSettings,
    ServerSettings,
    Settings,
    StartupHealthcheckSettings,
    StartupSettings,
    default_startup_settings,
)
from work_mcp.startup_checks import run_startup_checks


_DEFAULT_SERVER = ServerSettings(transport="stdio", host=None, port=None)
_DEFAULT_DATABASE = DatabaseSettings(
    db_type="sqlserver",
    host="db.example.internal",
    port=1433,
    user="readonly_user",
    password="secret",
    default_database="master",
    driver="ODBC Driver 18 for SQL Server",
    trust_server_certificate=False,
    connect_timeout_seconds=5,
)


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
        enabled_plugins=("jira", "database"),
        jira_latest_assigned_statuses=("待处理", "已接收", "处理中"),
        jira_start_target_status="已接收",
        jira_resolve_target_status="已解决",
        jira_attachment_max_images=5,
        jira_attachment_max_bytes=1_048_576,
        log_search=None,
        database=_DEFAULT_DATABASE,
    )
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


def test_run_startup_checks_skips_when_disabled(monkeypatch) -> None:
    calls: list[tuple[str, int]] = []

    def fake_jira_check(settings: Settings, timeout_seconds: int) -> None:
        calls.append(("jira", timeout_seconds))

    monkeypatch.setitem(
        startup_checks_module.STARTUP_CHECK_REGISTRY,
        "jira",
        fake_jira_check,
    )

    run_startup_checks(_make_settings())

    assert calls == []


def test_run_startup_checks_raises_aggregated_errors(monkeypatch) -> None:
    settings = _make_settings(
        startup=StartupSettings(
            healthcheck=StartupHealthcheckSettings(enabled=True, timeout_seconds=7)
        )
    )

    def fake_jira_check(_: Settings, timeout_seconds: int) -> None:
        assert timeout_seconds == 7
        raise RuntimeError("connectivity check failed: Jira request failed with HTTP 401")

    def fake_database_check(_: Settings, timeout_seconds: int) -> None:
        assert timeout_seconds == 7
        raise RuntimeError("connectivity check failed: Login timeout expired")

    monkeypatch.setitem(
        startup_checks_module.STARTUP_CHECK_REGISTRY,
        "jira",
        fake_jira_check,
    )
    monkeypatch.setitem(
        startup_checks_module.STARTUP_CHECK_REGISTRY,
        "database",
        fake_database_check,
    )

    try:
        run_startup_checks(settings)
    except RuntimeError as exc:
        assert str(exc) == (
            "Startup dependency checks failed:\n"
            "- jira: connectivity check failed: Jira request failed with HTTP 401\n"
            "- database: connectivity check failed: Login timeout expired"
        )
    else:
        raise AssertionError("Expected RuntimeError")
