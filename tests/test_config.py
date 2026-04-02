from __future__ import annotations

from pathlib import Path

import pytest

from work_assistant_mcp import config as config_module


def test_get_settings_allows_jira_without_dingtalk(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(
"""
integrations:
  enabled:
    - jira
jira:
  accept_transitions:
    - Accept
  resolve_transitions:
    - Resolved
""".strip(),
        encoding="utf-8",
    )
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "JIRA_BASE_URL=https://jira.example.invalid",
                "JIRA_EMAIL=user@example.invalid",
                "JIRA_API_TOKEN=secret-token",
                "JIRA_PROJECT_KEY=IOS",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.delenv("DINGTALK_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("DINGTALK_SECRET", raising=False)
    monkeypatch.delenv("JIRA_BASE_URL", raising=False)
    monkeypatch.delenv("JIRA_EMAIL", raising=False)
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
    monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)

    settings = config_module.get_settings()

    assert settings.enabled_integrations == ("jira",)
    assert settings.dingtalk_webhook_url == ""
    assert settings.jira_base_url == "https://jira.example.invalid"
    assert settings.jira_project_key == "IOS"


def test_get_settings_requires_jira_credentials_when_jira_enabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(
"""
integrations:
  enabled:
    - jira
jira:
  accept_transitions:
    - Accept
  resolve_transitions:
    - Resolved
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.delenv("DINGTALK_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("JIRA_BASE_URL", raising=False)
    monkeypatch.delenv("JIRA_EMAIL", raising=False)
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
    monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)

    with pytest.raises(RuntimeError, match="missing JIRA_BASE_URL"):
        config_module.get_settings()


def test_get_settings_supports_legacy_tools_enabled_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(
        """
tools:
  enabled:
    - jira
jira:
  accept_transitions:
    - Accept
  resolve_transitions:
    - Resolved
""".strip(),
        encoding="utf-8",
    )
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "JIRA_BASE_URL=https://jira.example.invalid",
                "JIRA_EMAIL=user@example.invalid",
                "JIRA_API_TOKEN=secret-token",
                "JIRA_PROJECT_KEY=IOS",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.delenv("JIRA_BASE_URL", raising=False)
    monkeypatch.delenv("JIRA_EMAIL", raising=False)
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
    monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)

    settings = config_module.get_settings()

    assert settings.enabled_integrations == ("jira",)
