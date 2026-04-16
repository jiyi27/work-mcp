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
  base_url: https://jira.example.invalid
  api_token: secret-token
  project_key: IOS
  latest_assigned_statuses:
    - 待处理
    - 已接收
  start_target_status: 已接收
  resolve_target_status: 已解决
""".strip(),
        encoding="utf-8",
    )
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
    monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)

    with pytest.raises(RuntimeError, match="missing jira.base_url"):
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


def test_get_settings_reports_yaml_syntax_errors_with_location(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(
        """
plugins:
  enabled:
    - remote_fs
remote_fs:
  roots:
    - name: app
      path: /tmp
      kind: workplace
      description: first line
  second line without colon
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)

    with pytest.raises(RuntimeError, match=r"YAML syntax error at line \d+, column \d+"):
        config_module.get_settings()


def test_get_settings_requires_mapping_at_document_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text("- database\n- jira\n", encoding="utf-8")
    monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)

    with pytest.raises(RuntimeError, match="expected a mapping at the document root"):
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
  base_url: https://jira.example.invalid
  api_token: secret-token
  project_key: IOS
  start_target_status: 已接收
  resolve_target_status: 已解决
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)

    with pytest.raises(RuntimeError, match="missing jira.latest_assigned_statuses"):
        config_module.get_settings()


def test_get_settings_treats_null_jira_credentials_as_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(
        """
plugins:
  enabled:
    - jira
jira:
  base_url: null
  api_token: secret-token
  project_key: IOS
  latest_assigned_statuses:
    - 待处理
  start_target_status: 已接收
  resolve_target_status: 已解决
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)

    with pytest.raises(RuntimeError, match="missing jira.base_url"):
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


def test_get_settings_reads_database_config_when_database_plugin_enabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(
        """
plugins:
  enabled:
    - database
database:
  type: sqlserver
  host: db.example.internal
  port: 1444
  user: readonly_user
  password: secret
  driver: ODBC Driver 18 for SQL Server
  trust_server_certificate: true
  connect_timeout_seconds: 9
""".strip(),
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
    assert settings.database.trust_server_certificate is True
    assert settings.database.connect_timeout_seconds == 9


def test_get_settings_ignores_invalid_jira_section_when_jira_is_disabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(
        """
plugins:
  enabled:
    - database
database:
  type: mysql
  host: mysql.example.internal
  user: readonly_user
  password: secret
jira: disabled
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)

    settings = config_module.get_settings()

    assert settings.enabled_plugins == ("database",)
    assert settings.database is not None
    assert settings.jira_base_url is None


def test_get_settings_ignores_invalid_remote_fs_section_when_remote_fs_is_disabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(
        """
plugins:
  enabled:
    - database
database:
  type: mysql
  host: mysql.example.internal
  user: readonly_user
  password: secret
remote_fs:
  roots:
    - name: app
      path: /path/that/does/not/exist
      kind: code
      description: invalid while disabled
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)

    settings = config_module.get_settings()

    assert settings.enabled_plugins == ("database",)
    assert settings.database is not None
    assert settings.remote_fs is None


def test_get_settings_reads_mysql_config_when_database_plugin_enabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(
        """
plugins:
  enabled:
    - database
database:
  type: mysql
  host: mysql.example.internal
  user: readonly_user
  password: secret
  connect_timeout_seconds: 9
""".strip(),
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
    assert settings.database.driver == ""
    assert settings.database.trust_server_certificate is False
    assert settings.database.connect_timeout_seconds == 9


def test_get_settings_requires_database_config_when_database_plugin_enabled(
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
    monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)

    with pytest.raises(RuntimeError, match="missing database section"):
        config_module.get_settings()
