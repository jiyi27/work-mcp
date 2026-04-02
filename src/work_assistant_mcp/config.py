from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


ENV_FILE_NAME = ".env"
YAML_CONFIG_FILE = "config.yaml"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOG_LEVELS = frozenset({"debug", "info", "warning", "error"})
KNOWN_INTEGRATIONS = frozenset({"dingtalk", "jira"})


@dataclass(frozen=True)
class Settings:
    # sensitive — loaded from .env / environment
    dingtalk_webhook_url: str
    dingtalk_secret: str | None
    jira_base_url: str | None
    jira_email: str | None
    jira_api_token: str | None
    jira_project_key: str | None
    # non-sensitive — loaded from config.yaml (env can override)
    log_dir: Path
    log_level: str
    server_name: str
    server_instructions: str
    enabled_integrations: tuple[str, ...]
    jira_accept_transitions: tuple[str, ...]
    jira_resolve_transitions: tuple[str, ...]
    jira_attachment_max_images: int
    jira_attachment_max_bytes: int


def load_env_file(env_path: Path | None = None) -> None:
    """Load key/value pairs from a local .env file without extra dependencies."""
    path = env_path or PROJECT_ROOT / ENV_FILE_NAME
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if not key or key in os.environ:
            continue

        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]

        os.environ[key] = value


def load_yaml_config(yaml_path: Path | None = None) -> dict[str, Any]:
    """Load non-sensitive configuration from config.yaml."""
    path = yaml_path or PROJECT_ROOT / YAML_CONFIG_FILE
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _read_enabled_integrations(yaml_cfg: dict[str, Any]) -> tuple[str, ...]:
    yaml_integrations = yaml_cfg.get("integrations")
    if yaml_integrations is None:
        yaml_integrations = yaml_cfg.get("tools", {})
    if not isinstance(yaml_integrations, dict):
        raise RuntimeError(
            "Invalid integrations section in config.yaml. Expected a mapping."
        )
    raw_enabled = yaml_integrations.get("enabled", [])
    if not isinstance(raw_enabled, list):
        raise RuntimeError(
            "Invalid integrations.enabled in config.yaml. Expected a list."
        )
    enabled = tuple(str(item).strip() for item in raw_enabled if str(item).strip())
    unknown = sorted(set(enabled) - KNOWN_INTEGRATIONS)
    if unknown:
        known = ", ".join(sorted(KNOWN_INTEGRATIONS))
        joined = ", ".join(unknown)
        raise RuntimeError(
            f"Unknown integration(s) in config.yaml: {joined}. Available integrations: {known}"
        )
    return enabled


def validate_settings(settings: Settings) -> None:
    errors: list[str] = []

    if "dingtalk" in settings.enabled_integrations and not settings.dingtalk_webhook_url:
        errors.append(
            "dingtalk: missing DINGTALK_WEBHOOK_URL in environment or .env"
        )

    if "jira" in settings.enabled_integrations:
        if not settings.jira_base_url:
            errors.append("jira: missing JIRA_BASE_URL in environment or .env")
        if not settings.jira_email:
            errors.append("jira: missing JIRA_EMAIL in environment or .env")
        if not settings.jira_api_token:
            errors.append("jira: missing JIRA_API_TOKEN in environment or .env")
        if not settings.jira_project_key:
            errors.append("jira: missing JIRA_PROJECT_KEY in environment or .env")
        if not settings.jira_accept_transitions:
            errors.append(
                "jira: missing jira.accept_transitions in config.yaml"
            )
        if not settings.jira_resolve_transitions:
            errors.append(
                "jira: missing jira.resolve_transitions in config.yaml"
            )
        if settings.jira_attachment_max_images <= 0:
            errors.append("jira: jira.attachments.max_images must be greater than 0")
        if settings.jira_attachment_max_bytes <= 0:
            errors.append(
                "jira: jira.attachments.max_bytes_per_image must be greater than 0"
            )

    if errors:
        lines = "\n".join(f"- {item}" for item in errors)
        raise RuntimeError(f"Invalid configuration for enabled integrations:\n{lines}")


def get_settings() -> Settings:
    load_env_file()
    yaml_cfg = load_yaml_config()
    enabled_integrations = _read_enabled_integrations(yaml_cfg)

    # sensitive values — only from environment
    webhook_url = os.getenv("DINGTALK_WEBHOOK_URL", "").strip()
    dingtalk_secret = os.getenv("DINGTALK_SECRET", "").strip() or None

    jira_base_url = os.getenv("JIRA_BASE_URL", "").strip() or None
    jira_email = os.getenv("JIRA_EMAIL", "").strip() or None
    jira_api_token = os.getenv("JIRA_API_TOKEN", "").strip() or None
    jira_project_key = os.getenv("JIRA_PROJECT_KEY", "").strip() or None

    # non-sensitive values — env overrides yaml, yaml overrides defaults
    yaml_logging = yaml_cfg.get("logging", {})
    log_dir_raw = (
        os.getenv("WORK_ASSISTANT_LOG_DIR", "").strip()
        or yaml_logging.get("dir", "logs")
    )
    log_level = (
        os.getenv("WORK_ASSISTANT_LOG_LEVEL", "").strip().lower()
        or str(yaml_logging.get("level", "info")).lower()
    )
    if log_level not in LOG_LEVELS:
        valid_levels = ", ".join(sorted(LOG_LEVELS))
        raise RuntimeError(
            "Invalid WORK_ASSISTANT_LOG_LEVEL. "
            f"Expected one of: {valid_levels}."
        )

    yaml_server = yaml_cfg.get("server", {})
    server_name = yaml_server.get("name", "work-assistant-mcp")
    server_instructions = yaml_server.get("instructions", "")

    yaml_jira = yaml_cfg.get("jira", {})

    def _read_string_list(key: str, default: list[str]) -> tuple[str, ...]:
        value = yaml_jira.get(key, default)
        if not isinstance(value, list):
            raise RuntimeError(f"Invalid jira.{key} in config.yaml. Expected a list.")
        items = tuple(str(item).strip() for item in value if str(item).strip())
        return items

    jira_accept_transitions = _read_string_list("accept_transitions", [])
    jira_resolve_transitions = _read_string_list("resolve_transitions", [])

    yaml_jira_attachments = yaml_jira.get("attachments", {})
    if not isinstance(yaml_jira_attachments, dict):
        raise RuntimeError(
            "Invalid jira.attachments in config.yaml. Expected a mapping."
        )
    jira_attachment_max_images = int(yaml_jira_attachments.get("max_images", 5))
    jira_attachment_max_bytes = int(
        yaml_jira_attachments.get("max_bytes_per_image", 1_048_576)
    )

    settings = Settings(
        dingtalk_webhook_url=webhook_url,
        dingtalk_secret=dingtalk_secret,
        jira_base_url=jira_base_url,
        jira_email=jira_email,
        jira_api_token=jira_api_token,
        jira_project_key=jira_project_key,
        log_dir=Path(log_dir_raw),
        log_level=log_level,
        server_name=server_name,
        server_instructions=server_instructions,
        enabled_integrations=enabled_integrations,
        jira_accept_transitions=jira_accept_transitions,
        jira_resolve_transitions=jira_resolve_transitions,
        jira_attachment_max_images=jira_attachment_max_images,
        jira_attachment_max_bytes=jira_attachment_max_bytes,
    )
    validate_settings(settings)
    return settings
