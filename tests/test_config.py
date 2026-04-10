from __future__ import annotations

from pathlib import Path

import pytest

from work_mcp import config as config_module


def test_get_settings_reads_top_level_log_search_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(
        """
plugins:
  enabled:
    - log_search
log_search:
  log_base_dir: /tmp/work-logs
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)

    settings = config_module.get_settings()

    assert settings.enabled_plugins == ("log_search",)
    assert settings.log_search is not None
    assert settings.log_search.log_base_dir == "/tmp/work-logs"


def test_get_settings_requires_log_search_section_when_enabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(
        """
plugins:
  enabled:
    - log_search
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)

    with pytest.raises(RuntimeError, match="missing log_search section"):
        config_module.get_settings()


def test_get_settings_allows_jira_without_dingtalk(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(
"""
plugins:
  enabled:
    - jira
jira:
  latest_assigned_statuses:
    - 待处理
    - 已接收
  start_target_status: 已接收
  resolve_target_status: 已解决
""".strip(),
        encoding="utf-8",
    )
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "JIRA_BASE_URL=https://jira.example.invalid",
                "JIRA_API_TOKEN=secret-token",
                "JIRA_PROJECT_KEY=IOS",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.delenv("DINGTALK_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("DINGTALK_SECRET", raising=False)
    monkeypatch.delenv("JIRA_BASE_URL", raising=False)
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
    monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)

    settings = config_module.get_settings()

    assert settings.enabled_plugins == ("jira",)
    assert settings.dingtalk_webhook_url == ""
    assert settings.jira_base_url == "https://jira.example.invalid"
    assert settings.jira_project_key == "IOS"


def test_get_settings_requires_jira_credentials_when_jira_enabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(
"""
plugins:
  enabled:
    - jira
jira:
  latest_assigned_statuses:
    - 待处理
    - 已接收
  start_target_status: 已接收
  resolve_target_status: 已解决
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.delenv("DINGTALK_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("JIRA_BASE_URL", raising=False)
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
    monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)

    with pytest.raises(RuntimeError, match="missing JIRA_BASE_URL"):
        config_module.get_settings()


def test_get_settings_requires_plugins_section_to_be_a_mapping(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(
        """
plugins:
  - jira
jira:
  latest_assigned_statuses:
    - 待处理
    - 已接收
  start_target_status: 已接收
  resolve_target_status: 已解决
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)

    with pytest.raises(RuntimeError, match="Invalid plugins section"):
        config_module.get_settings()


def test_get_settings_requires_plugins_section(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)

    with pytest.raises(RuntimeError, match="Missing plugins section"):
        config_module.get_settings()


def test_get_settings_requires_plugins_enabled_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(
        """
plugins: {}
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)

    with pytest.raises(RuntimeError, match="Missing plugins.enabled"):
        config_module.get_settings()


def test_get_settings_requires_latest_assigned_statuses_when_jira_enabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(
        """
plugins:
  enabled:
    - jira
jira:
  start_target_status: 已接收
  resolve_target_status: 已解决
""".strip(),
        encoding="utf-8",
    )
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "JIRA_BASE_URL=https://jira.example.invalid",
                "JIRA_API_TOKEN=secret-token",
                "JIRA_PROJECT_KEY=IOS",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.delenv("JIRA_BASE_URL", raising=False)
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
    monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)

    with pytest.raises(RuntimeError, match="missing jira.latest_assigned_statuses"):
        config_module.get_settings()


def test_get_settings_reads_logging_values_from_yaml(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(
        """
plugins:
  enabled: []
logging:
  dir: logs-from-yaml
  level: warning
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)

    settings = config_module.get_settings()

    assert settings.log_dir == Path("logs-from-yaml")
    assert settings.log_level == "warning"


def test_get_settings_disables_startup_healthcheck_by_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(
        """
plugins:
  enabled: []
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)

    settings = config_module.get_settings()

    assert settings.startup.healthcheck.enabled is False
    assert (
        settings.startup.healthcheck.timeout_seconds
        == config_module.DEFAULT_STARTUP_HEALTHCHECK_TIMEOUT_SECONDS
    )


def test_get_settings_reads_startup_healthcheck_settings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(
        """
plugins:
  enabled: []
startup:
  healthcheck:
    enabled: true
    timeout_seconds: 7
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)

    settings = config_module.get_settings()

    assert settings.startup.healthcheck.enabled is True
    assert settings.startup.healthcheck.timeout_seconds == 7


def test_get_settings_uses_stdio_by_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(
        """
plugins:
  enabled: []
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)

    settings = config_module.get_settings()

    assert settings.server.transport == "stdio"
    assert settings.server.host is None
    assert settings.server.port is None


def test_get_settings_allows_missing_server_section(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(
        """
plugins:
  enabled: []
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)

    settings = config_module.get_settings()

    assert settings.server.transport == config_module.DEFAULT_TRANSPORT
    assert settings.server.host is None
    assert settings.server.port is None


def test_get_settings_rejects_invalid_logging_section(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(
        """
plugins:
  enabled: []
logging: logs
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)

    with pytest.raises(RuntimeError, match="Invalid logging section"):
        config_module.get_settings()


def test_get_settings_rejects_invalid_startup_healthcheck_timeout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(
        """
plugins:
  enabled: []
startup:
  healthcheck:
    enabled: true
    timeout_seconds: 0
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)

    with pytest.raises(RuntimeError, match="startup.healthcheck.timeout_seconds"):
        config_module.get_settings()


def test_get_settings_reads_database_env_when_database_plugin_enabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(
        """
plugins:
  enabled:
    - database
""".strip(),
        encoding="utf-8",
    )
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "DB_TYPE=sqlserver",
                "DB_HOST=db.example.internal",
                "DB_PORT=1444",
                "DB_USER=readonly_user",
                "DB_PASSWORD=secret",
                "DB_NAME=master",
                "DB_DRIVER=ODBC Driver 18 for SQL Server",
                "DB_TRUST_SERVER_CERTIFICATE=true",
                "DB_CONNECT_TIMEOUT_SECONDS=9",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)

    settings = config_module.get_settings()

    assert settings.enabled_plugins == ("database",)
    assert settings.database is not None
    assert settings.database.host == "db.example.internal"
    assert settings.database.port == 1444
    assert settings.database.user == "readonly_user"
    assert settings.database.password == "secret"
    assert settings.database.default_database == "master"
    assert settings.database.trust_server_certificate is True
    assert settings.database.connect_timeout_seconds == 9


def test_get_settings_reads_mysql_env_when_database_plugin_enabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    for env_name in (
        "DB_TYPE",
        "DB_HOST",
        "DB_PORT",
        "DB_USER",
        "DB_PASSWORD",
        "DB_NAME",
        "DB_DRIVER",
        "DB_TRUST_SERVER_CERTIFICATE",
        "DB_CONNECT_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(env_name, raising=False)
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(
        """
plugins:
  enabled:
    - database
""".strip(),
        encoding="utf-8",
    )
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "DB_TYPE=mysql",
                "DB_HOST=mysql.example.internal",
                "DB_USER=readonly_user",
                "DB_PASSWORD=secret",
                "DB_NAME=app_db",
                "DB_CONNECT_TIMEOUT_SECONDS=9",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)

    settings = config_module.get_settings()

    assert settings.enabled_plugins == ("database",)
    assert settings.database is not None
    assert settings.database.db_type == "mysql"
    assert settings.database.host == "mysql.example.internal"
    assert settings.database.port == 3306
    assert settings.database.user == "readonly_user"
    assert settings.database.password == "secret"
    assert settings.database.default_database == "app_db"
    assert settings.database.driver == ""
    assert settings.database.trust_server_certificate is False
    assert settings.database.connect_timeout_seconds == 9


def test_get_settings_requires_database_env_when_database_plugin_enabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(
        """
plugins:
  enabled:
    - database
    """.strip(),
        encoding="utf-8",
    )
    for env_name in (
        "DB_TYPE",
        "DB_HOST",
        "DB_PORT",
        "DB_USER",
        "DB_PASSWORD",
        "DB_NAME",
        "DB_DRIVER",
        "DB_TRUST_SERVER_CERTIFICATE",
        "DB_CONNECT_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(env_name, raising=False)
    monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)

    with pytest.raises(RuntimeError, match="missing DB_HOST"):
        config_module.get_settings()
