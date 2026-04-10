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
        enable_database=True,
        db_type="mysql",
        host="db.example.internal",
        port=3306,
        user="readonly_user",
        password="secret",
        database_name="app_db",
        driver="",
        trust_server_certificate=False,
        connect_timeout_seconds=5,
        enable_log_search=True,
        log_base_dir="/tmp/work-logs",
        enable_dingtalk=False,
        dingtalk_webhook_url="",
        dingtalk_secret="",
        enable_jira=False,
        jira_base_url="",
        jira_api_token="",
        jira_project_key="",
    )
    defaults.update(overrides)
    return SetupAnswers(**defaults)  # type: ignore[arg-type]


def test_build_updated_env_keeps_only_enabled_plugin_credentials() -> None:
    existing = {
        "DB_TYPE": "sqlserver",
        "DB_HOST": "db.example.internal",
        "DB_PORT": "1433",
        "DB_USER": "readonly_user",
        "DB_PASSWORD": "secret",
        "DB_NAME": "master",
        "DB_DRIVER": "ODBC Driver 18 for SQL Server",
        "DB_TRUST_SERVER_CERTIFICATE": "true",
        "DINGTALK_WEBHOOK_URL": "https://example.invalid/webhook",
        "DINGTALK_SECRET": "secret",
        "JIRA_BASE_URL": "https://jira.example.invalid",
        "JIRA_API_TOKEN": "keep-me",
        "JIRA_PROJECT_KEY": "IOS",
    }

    updated = build_updated_env(existing, _answers())

    assert updated["DB_TYPE"] == "mysql"
    assert updated["DB_PORT"] == "3306"
    assert updated["DB_HOST"] == "db.example.internal"
    assert "DB_DRIVER" not in updated
    assert "DB_TRUST_SERVER_CERTIFICATE" not in updated
    assert "DINGTALK_WEBHOOK_URL" not in updated
    assert "JIRA_API_TOKEN" not in updated


def test_build_updated_env_removes_database_and_dingtalk_when_only_jira_is_enabled() -> None:
    existing = {
        "DB_TYPE": "mysql",
        "DB_HOST": "db.example.internal",
        "DB_PORT": "3306",
        "DB_USER": "readonly_user",
        "DB_PASSWORD": "secret",
        "DB_NAME": "app_db",
        "DINGTALK_WEBHOOK_URL": "https://example.invalid/webhook",
        "DINGTALK_SECRET": "secret",
    }

    updated = build_updated_env(
        existing,
        _answers(
            enable_database=False,
            enable_log_search=False,
            enable_jira=True,
            jira_base_url="https://jira.example.invalid",
            jira_api_token="jira-token",
            jira_project_key="IOS",
        ),
    )

    assert "DB_TYPE" not in updated
    assert "DINGTALK_WEBHOOK_URL" not in updated
    assert updated["JIRA_BASE_URL"] == "https://jira.example.invalid"
    assert updated["JIRA_API_TOKEN"] == "jira-token"
    assert updated["JIRA_PROJECT_KEY"] == "IOS"

def test_build_updated_yaml_replaces_enabled_plugins_and_removes_disabled_sections() -> None:
    existing_yaml = {
        "plugins": {"enabled": ["jira", "database"]},
        "log_search": {"log_base_dir": "/tmp/existing-logs"},
        "jira": {"start_target_status": "In Progress"},
    }

    updated = build_updated_yaml(existing_yaml, _answers(enable_dingtalk=True))

    assert updated["plugins"]["enabled"] == ["database", "log_search", "dingtalk"]
    assert updated["log_search"]["log_base_dir"] == "/tmp/work-logs"
    assert "jira" not in updated


def test_build_updated_yaml_adds_default_jira_config_when_enabled() -> None:
    updated = build_updated_yaml({}, _answers(enable_database=False, enable_log_search=False, enable_jira=True))

    assert updated["plugins"]["enabled"] == ["jira"]
    assert updated["jira"] == {
        "latest_assigned_statuses": ["重新打开", "ToDo"],
        "start_target_status": "已接受",
        "resolve_target_status": "已解决",
        "attachments": {
            "max_images": 5,
            "max_bytes_per_image": 1048576,
        },
    }


def test_build_updated_yaml_allows_disabling_database_and_log_search() -> None:
    existing_yaml = {
        "plugins": {"enabled": ["database", "log_search"]},
        "log_search": {"log_base_dir": "/tmp/existing-logs"},
    }

    updated = build_updated_yaml(
        existing_yaml,
        _answers(enable_database=False, enable_log_search=False),
    )

    assert updated["plugins"]["enabled"] == []
    assert "log_search" not in updated


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
        "未检测到可用的 SQL Server ODBC driver" in result.message
        for result in results
    )


def test_diagnose_accepts_empty_enabled_plugins(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "config.yaml").write_text(
        """
plugins:
  enabled: []
""".strip()
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr("work_mcp.setup.shutil.which", lambda name: "/usr/bin/uv")

    results = diagnose(tmp_path)

    assert has_errors(results) is False
    assert any(result.message == "enabled plugins: none" for result in results)
