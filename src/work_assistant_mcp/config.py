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
KNOWN_PLUGINS = frozenset({"dingtalk", "jira", "log_search"})
ALLOWED_TRANSPORTS = frozenset({"stdio", "streamable-http"})


@dataclass(frozen=True)
class ServerSettings:
    transport: str
    host: str | None
    port: int | None


@dataclass(frozen=True)
class LogSearchSettings:
    log_base_dir: str
    file_pattern: str
    levels: tuple[str, ...]
    services: tuple[str, ...]


@dataclass(frozen=True)
class Settings:
    # server transport
    server: ServerSettings
    # sensitive — loaded from .env / environment
    dingtalk_webhook_url: str
    dingtalk_secret: str | None
    jira_base_url: str | None
    jira_api_token: str | None
    jira_project_key: str | None
    # non-sensitive — loaded from config.yaml (env can override)
    log_dir: Path
    log_level: str
    server_name: str
    server_instructions: str
    enabled_plugins: tuple[str, ...]
    jira_latest_assigned_statuses: tuple[str, ...]
    jira_start_target_status: str
    jira_resolve_target_status: str
    jira_attachment_max_images: int
    jira_attachment_max_bytes: int
    log_search: LogSearchSettings | None


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


def _read_server_settings(yaml_cfg: dict[str, Any]) -> ServerSettings:
    yaml_server = yaml_cfg.get("server", {})
    if not isinstance(yaml_server, dict):
        raise RuntimeError("Invalid server section in config.yaml. Expected a mapping.")

    transport = str(yaml_server.get("transport", "")).strip()
    if not transport:
        allowed = ", ".join(sorted(ALLOWED_TRANSPORTS))
        raise RuntimeError(
            f"server.transport is required in config.yaml. Allowed values: {allowed}"
        )
    if transport not in ALLOWED_TRANSPORTS:
        allowed = ", ".join(sorted(ALLOWED_TRANSPORTS))
        raise RuntimeError(
            f"Invalid server.transport '{transport}' in config.yaml. Allowed values: {allowed}"
        )

    host_raw = yaml_server.get("host")
    port_raw = yaml_server.get("port")
    host = str(host_raw).strip() if host_raw is not None else None
    port = int(port_raw) if port_raw is not None else None

    return ServerSettings(transport=transport, host=host, port=port)


def _read_enabled_plugins(yaml_cfg: dict[str, Any]) -> tuple[str, ...]:
    yaml_plugins = yaml_cfg.get("plugins", {})
    if not isinstance(yaml_plugins, dict):
        raise RuntimeError("Invalid plugins section in config.yaml. Expected a mapping.")
    raw_enabled = yaml_plugins.get("enabled", [])
    if not isinstance(raw_enabled, list):
        raise RuntimeError("Invalid plugins.enabled in config.yaml. Expected a list.")
    enabled = tuple(str(item).strip() for item in raw_enabled if str(item).strip())
    unknown = sorted(set(enabled) - KNOWN_PLUGINS)
    if unknown:
        known = ", ".join(sorted(KNOWN_PLUGINS))
        joined = ", ".join(unknown)
        raise RuntimeError(
            f"Unknown plugin(s) in config.yaml: {joined}. Available plugins: {known}"
        )
    return enabled


def _read_string_list(section: dict[str, Any], key: str) -> tuple[str, ...]:
    raw_value = section.get(key, [])
    if not isinstance(raw_value, list):
        raise RuntimeError(f"Invalid jira.{key} in config.yaml. Expected a list.")
    return tuple(str(item).strip() for item in raw_value if str(item).strip())


def _read_log_search_settings(yaml_cfg: dict[str, Any]) -> LogSearchSettings | None:
    yaml_plugins = yaml_cfg.get("plugins", {})
    if not isinstance(yaml_plugins, dict):
        return None
    yaml_log_search = yaml_plugins.get("log_search")
    if not yaml_log_search:
        return None
    if not isinstance(yaml_log_search, dict):
        raise RuntimeError(
            "Invalid plugins.log_search in config.yaml. Expected a mapping."
        )

    log_base_dir = str(yaml_log_search.get("log_base_dir", "")).strip()
    file_pattern = str(yaml_log_search.get("file_pattern", "")).strip()
    levels = tuple(
        str(l).strip() for l in yaml_log_search.get("levels", []) if str(l).strip()
    )
    services = tuple(
        str(s).strip() for s in yaml_log_search.get("services", []) if str(s).strip()
    )
    return LogSearchSettings(
        log_base_dir=log_base_dir,
        file_pattern=file_pattern,
        levels=levels,
        services=services,
    )


def validate_settings(settings: Settings) -> None:
    errors: list[str] = []

    # server transport validation
    if settings.server.transport == "streamable-http":
        if not settings.server.host:
            errors.append(
                "server: host is required when transport is streamable-http"
            )
        if settings.server.port is None:
            errors.append(
                "server: port is required when transport is streamable-http"
            )

    if "dingtalk" in settings.enabled_plugins and not settings.dingtalk_webhook_url:
        errors.append(
            "dingtalk: missing DINGTALK_WEBHOOK_URL in environment or .env"
        )

    if "jira" in settings.enabled_plugins:
        if not settings.jira_base_url:
            errors.append("jira: missing JIRA_BASE_URL in environment or .env")
        if not settings.jira_api_token:
            errors.append("jira: missing JIRA_API_TOKEN in environment or .env")
        if not settings.jira_project_key:
            errors.append("jira: missing JIRA_PROJECT_KEY in environment or .env")
        if not settings.jira_latest_assigned_statuses:
            errors.append(
                "jira: missing jira.latest_assigned_statuses in config.yaml"
            )
        if not settings.jira_start_target_status:
            errors.append(
                "jira: missing jira.start_target_status in config.yaml"
            )
        if not settings.jira_resolve_target_status:
            errors.append(
                "jira: missing jira.resolve_target_status in config.yaml"
            )
        if settings.jira_attachment_max_images <= 0:
            errors.append("jira: jira.attachments.max_images must be greater than 0")
        if settings.jira_attachment_max_bytes <= 0:
            errors.append(
                "jira: jira.attachments.max_bytes_per_image must be greater than 0"
            )

    if "log_search" in settings.enabled_plugins:
        if settings.log_search is None:
            errors.append(
                "log_search: missing plugins.log_search section in config.yaml"
            )
        else:
            if not settings.log_search.log_base_dir:
                errors.append(
                    "log_search: missing plugins.log_search.log_base_dir in config.yaml"
                )
            if not settings.log_search.file_pattern:
                errors.append(
                    "log_search: missing plugins.log_search.file_pattern in config.yaml"
                )
            if not settings.log_search.services:
                errors.append(
                    "log_search: missing or empty plugins.log_search.services in config.yaml"
                )
            if (
                settings.log_search.file_pattern
                and "{level}" in settings.log_search.file_pattern
                and not settings.log_search.levels
            ):
                errors.append(
                    "log_search: file_pattern contains {level} but plugins.log_search.levels is empty in config.yaml"
                )

    if errors:
        lines = "\n".join(f"- {item}" for item in errors)
        raise RuntimeError(f"Invalid configuration for enabled plugins:\n{lines}")


def get_settings() -> Settings:
    load_env_file()
    yaml_cfg = load_yaml_config()

    server = _read_server_settings(yaml_cfg)
    enabled_plugins = _read_enabled_plugins(yaml_cfg)
    log_search = _read_log_search_settings(yaml_cfg)

    # sensitive values — only from environment
    webhook_url = os.getenv("DINGTALK_WEBHOOK_URL", "").strip()
    dingtalk_secret = os.getenv("DINGTALK_SECRET", "").strip() or None

    jira_base_url = os.getenv("JIRA_BASE_URL", "").strip() or None
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
    if not isinstance(yaml_jira, dict):
        raise RuntimeError("Invalid jira section in config.yaml. Expected a mapping.")

    jira_latest_assigned_statuses = _read_string_list(
        yaml_jira, "latest_assigned_statuses"
    )
    jira_start_target_status = str(yaml_jira.get("start_target_status", "")).strip()
    jira_resolve_target_status = str(yaml_jira.get("resolve_target_status", "")).strip()

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
        server=server,
        dingtalk_webhook_url=webhook_url,
        dingtalk_secret=dingtalk_secret,
        jira_base_url=jira_base_url,
        jira_api_token=jira_api_token,
        jira_project_key=jira_project_key,
        log_dir=Path(log_dir_raw),
        log_level=log_level,
        server_name=server_name,
        server_instructions=server_instructions,
        enabled_plugins=enabled_plugins,
        jira_latest_assigned_statuses=jira_latest_assigned_statuses,
        jira_start_target_status=jira_start_target_status,
        jira_resolve_target_status=jira_resolve_target_status,
        jira_attachment_max_images=jira_attachment_max_images,
        jira_attachment_max_bytes=jira_attachment_max_bytes,
        log_search=log_search,
    )
    validate_settings(settings)
    return settings
