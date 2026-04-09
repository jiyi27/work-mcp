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
server:
  transport: stdio
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
server:
  transport: stdio
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
server:
  transport: stdio
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
server:
  transport: stdio
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
server:
  transport: stdio
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


def test_get_settings_requires_latest_assigned_statuses_when_jira_enabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(
        """
server:
  transport: stdio
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
server:
  transport: stdio
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


def test_get_settings_rejects_invalid_logging_section(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(
        """
server:
  transport: stdio
plugins:
  enabled: []
logging: logs
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)

    with pytest.raises(RuntimeError, match="Invalid logging section"):
        config_module.get_settings()
