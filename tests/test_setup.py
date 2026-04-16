from __future__ import annotations
from pathlib import Path

import pytest

from work_mcp.setup import (
    SetupAnswers,
    build_updated_yaml,
    is_jira_config_complete,
    is_log_search_config_complete,
    load_existing_yaml,
)


def _answers(**overrides: object) -> SetupAnswers:
    defaults = dict(
        enable_database=True,
        db_type="mysql",
        host="db.example.internal",
        port=3306,
        user="readonly_user",
        password="secret",
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


def test_build_updated_yaml_updates_active_plugin_and_preserves_inactive_ones() -> None:
    existing_yaml = {
        "database": {"type": "sqlserver", "host": "old-host"},
        "dingtalk": {"webhook_url": "https://old.invalid/webhook"},
        "jira": {"base_url": "https://old-jira.invalid"},
    }

    updated = build_updated_yaml(existing_yaml, _answers())

    # Active plugin (database) is updated with new values
    assert updated["database"]["type"] == "mysql"
    assert updated["database"]["host"] == "db.example.internal"
    assert "name" not in updated["database"]
    assert "driver" not in updated["database"]
    assert "trust_server_certificate" not in updated["database"]
    # Inactive plugins are preserved, not removed
    assert updated["dingtalk"]["webhook_url"] == "https://old.invalid/webhook"
    assert updated["jira"]["base_url"] == "https://old-jira.invalid"


def test_load_existing_yaml_reports_yaml_syntax_errors_with_location(tmp_path: Path) -> None:
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(
        """
plugins:
  enabled:
    - jira
jira:
  base_url: https://jira.example.invalid
broken line
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match=r"YAML syntax error at line \d+, column \d+"):
        load_existing_yaml(yaml_path)


def test_load_existing_yaml_requires_mapping_at_document_root(tmp_path: Path) -> None:
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text("- jira\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="expected a mapping at the document root"):
        load_existing_yaml(yaml_path)


def test_build_updated_yaml_updates_jira_and_preserves_database_and_dingtalk() -> None:
    existing_yaml = {
        "database": {"type": "mysql", "host": "db.example.internal"},
        "dingtalk": {"webhook_url": "https://old.invalid/webhook"},
    }

    updated = build_updated_yaml(
        existing_yaml,
        _answers(
            enable_database=False,
            enable_log_search=False,
            enable_jira=True,
            jira_base_url="https://jira.example.invalid",
            jira_api_token="jira-token",
            jira_project_key="IOS",
        ),
    )

    # Inactive plugins are preserved, not removed
    assert updated["database"]["host"] == "db.example.internal"
    assert updated["dingtalk"]["webhook_url"] == "https://old.invalid/webhook"
    # Active plugin (jira) is written
    assert updated["jira"]["base_url"] == "https://jira.example.invalid"
    assert updated["jira"]["api_token"] == "jira-token"
    assert updated["jira"]["project_key"] == "IOS"

def test_build_updated_yaml_replaces_enabled_plugins_and_preserves_inactive_sections() -> None:
    existing_yaml = {
        "plugins": {"enabled": ["jira", "database"]},
        "log_search": {"log_base_dir": "/tmp/existing-logs"},
        "jira": {"start_target_status": "In Progress"},
    }

    updated = build_updated_yaml(existing_yaml, _answers(enable_dingtalk=True))

    assert updated["plugins"]["enabled"] == ["database", "log_search", "dingtalk"]
    assert updated["log_search"]["log_base_dir"] == "/tmp/work-logs"
    # jira is inactive but its existing config is preserved
    assert updated["jira"]["start_target_status"] == "In Progress"


def test_build_updated_yaml_adds_default_jira_config_when_enabled() -> None:
    updated = build_updated_yaml(
        {},
        _answers(
            enable_database=False,
            enable_log_search=False,
            enable_jira=True,
            jira_base_url="https://jira.example.invalid",
            jira_api_token="jira-token",
            jira_project_key="IOS",
        ),
    )

    assert updated["plugins"]["enabled"] == ["jira"]
    jira = updated["jira"]
    assert jira["base_url"] == "https://jira.example.invalid"
    assert jira["api_token"] == "jira-token"
    assert jira["project_key"] == "IOS"
    assert jira["latest_assigned_statuses"] == ["重新打开", "ToDo"]
    assert jira["start_target_status"] == "已接受"
    assert jira["resolve_target_status"] == "已解决"
    assert jira["attachments"] == {"max_images": 5, "max_bytes_per_image": 1048576}


def test_build_updated_yaml_updates_plugins_enabled_and_preserves_inactive_sections() -> None:
    existing_yaml = {
        "plugins": {"enabled": ["database", "log_search"]},
        "log_search": {"log_base_dir": "/tmp/existing-logs"},
    }

    updated = build_updated_yaml(
        existing_yaml,
        _answers(enable_database=False, enable_log_search=False),
    )

    assert updated["plugins"]["enabled"] == []
    # Inactive sections are preserved, not removed
    assert updated["log_search"]["log_base_dir"] == "/tmp/existing-logs"

def test_is_jira_config_complete_treats_none_as_missing() -> None:
    assert is_jira_config_complete(
        {
            "base_url": None,
            "api_token": "secret-token",
            "project_key": "IOS",
        }
    ) is False


def test_is_log_search_config_complete_treats_none_as_missing() -> None:
    assert is_log_search_config_complete({"log_base_dir": None}) is False
