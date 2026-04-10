from __future__ import annotations

from pathlib import Path

from work_mcp.setup import (
    SetupAnswers,
    build_updated_env,
    build_updated_yaml,
    diagnose,
    has_errors,
)


def _answers(**overrides: object) -> SetupAnswers:
    defaults = dict(
        db_type="mysql",
        host="db.example.internal",
        port=3306,
        user="readonly_user",
        password="secret",
        database_name="app_db",
        driver="",
        trust_server_certificate=False,
        connect_timeout_seconds=5,
        log_base_dir="/tmp/work-logs",
        enable_dingtalk=False,
        dingtalk_webhook_url="",
        dingtalk_secret="",
    )
    defaults.update(overrides)
    return SetupAnswers(**defaults)  # type: ignore[arg-type]


def test_build_updated_env_for_mysql_removes_sqlserver_and_dingtalk_keys() -> None:
    existing = {
        "DB_TYPE": "sqlserver",
        "DB_DRIVER": "ODBC Driver 18 for SQL Server",
        "DB_TRUST_SERVER_CERTIFICATE": "true",
        "DINGTALK_WEBHOOK_URL": "https://example.invalid/webhook",
        "DINGTALK_SECRET": "secret",
        "JIRA_API_TOKEN": "keep-me",
    }

    updated = build_updated_env(existing, _answers())

    assert updated["DB_TYPE"] == "mysql"
    assert updated["DB_PORT"] == "3306"
    assert "DB_DRIVER" not in updated
    assert "DB_TRUST_SERVER_CERTIFICATE" not in updated
    assert "DINGTALK_WEBHOOK_URL" not in updated
    assert updated["JIRA_API_TOKEN"] == "keep-me"


def test_build_updated_yaml_sets_supported_plugins_and_preserves_existing_sections() -> None:
    existing_yaml = {
        "plugins": {"enabled": ["jira", "database"]},
        "jira": {"start_target_status": "In Progress"},
    }

    updated = build_updated_yaml(existing_yaml, _answers(enable_dingtalk=True))

    assert updated["plugins"]["enabled"] == ["database", "log_search", "dingtalk"]
    assert updated["log_search"]["log_base_dir"] == "/tmp/work-logs"
    assert updated["jira"] == {"start_target_status": "In Progress"}


def test_diagnose_reports_success_for_valid_mysql_configuration(
    monkeypatch,
    tmp_path: Path,
) -> None:
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "DB_TYPE=mysql",
                "DB_HOST=db.example.internal",
                "DB_PORT=3306",
                "DB_USER=readonly_user",
                "DB_PASSWORD=secret",
                "DB_NAME=app_db",
                "DB_CONNECT_TIMEOUT_SECONDS=5",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "config.yaml").write_text(
        f"""
plugins:
  enabled:
    - database
    - log_search
log_search:
  log_base_dir: {log_dir}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr("work_mcp.setup.shutil.which", lambda name: "/usr/bin/uv")
    monkeypatch.setattr(
        "work_mcp.setup.check_database_connectivity",
        lambda config, timeout_seconds: {"database_name": config.default_database},
    )

    results = diagnose(tmp_path)

    assert has_errors(results) is False
    assert any(result.message == "uv is available" for result in results)
    assert any(
        result.message == "database connectivity succeeded for app_db"
        for result in results
    )


def test_diagnose_reports_missing_sqlserver_driver(
    monkeypatch,
    tmp_path: Path,
) -> None:
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "DB_TYPE=sqlserver",
                "DB_HOST=db.example.internal",
                "DB_PORT=1433",
                "DB_USER=readonly_user",
                "DB_PASSWORD=secret",
                "DB_NAME=master",
                "DB_DRIVER=ODBC Driver 18 for SQL Server",
                "DB_TRUST_SERVER_CERTIFICATE=false",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "config.yaml").write_text(
        f"""
plugins:
  enabled:
    - database
    - log_search
log_search:
  log_base_dir: {log_dir}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr("work_mcp.setup.shutil.which", lambda name: "/usr/bin/uv")
    monkeypatch.setattr("work_mcp.setup.get_installed_odbc_drivers", lambda: [])
    monkeypatch.setattr(
        "work_mcp.setup.check_database_connectivity",
        lambda config, timeout_seconds: {"database_name": config.default_database},
    )

    results = diagnose(tmp_path)

    assert has_errors(results) is True
    assert any(
        "Configured ODBC driver was not found." in result.message for result in results
    )
