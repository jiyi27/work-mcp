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
KNOWN_PLUGINS = frozenset({"database", "dingtalk", "jira", "log_search"})
DEFAULT_TRANSPORT = "stdio"
DEFAULT_HTTP_HOST = "127.0.0.1"
DEFAULT_HTTP_PORT = 8000
DB_TYPE_SQLSERVER = "sqlserver"
DB_TYPE_MYSQL = "mysql"
SUPPORTED_DB_TYPES = frozenset({DB_TYPE_SQLSERVER, DB_TYPE_MYSQL})
DEFAULT_DB_PORTS = {
    DB_TYPE_SQLSERVER: 1433,
    DB_TYPE_MYSQL: 3306,
}
DEFAULT_DB_DRIVER = "ODBC Driver 18 for SQL Server"
DEFAULT_DB_CONNECT_TIMEOUT_SECONDS = 5
DEFAULT_STARTUP_HEALTHCHECK_TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class ServerSettings:
    transport: str
    host: str | None
    port: int | None


@dataclass(frozen=True)
class StartupHealthcheckSettings:
    enabled: bool
    timeout_seconds: int


@dataclass(frozen=True)
class StartupSettings:
    healthcheck: StartupHealthcheckSettings


@dataclass(frozen=True)
class LogSearchSettings:
    log_base_dir: str


@dataclass(frozen=True)
class DatabaseSettings:
    db_type: str
    host: str
    port: int
    user: str
    password: str
    default_database: str
    driver: str
    trust_server_certificate: bool
    connect_timeout_seconds: int


@dataclass(frozen=True)
class Settings:
    # server transport
    server: ServerSettings
    startup: StartupSettings
    # sensitive — loaded from .env / environment
    dingtalk_webhook_url: str
    dingtalk_secret: str | None
    jira_base_url: str | None
    jira_api_token: str | None
    jira_project_key: str | None
    # non-sensitive — loaded from config.yaml
    log_dir: Path
    log_level: str
    enabled_plugins: tuple[str, ...]
    jira_latest_assigned_statuses: tuple[str, ...]
    jira_start_target_status: str
    jira_resolve_target_status: str
    jira_attachment_max_images: int
    jira_attachment_max_bytes: int
    log_search: LogSearchSettings | None
    database: DatabaseSettings | None = None


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


def default_server_settings() -> ServerSettings:
    return ServerSettings(transport=DEFAULT_TRANSPORT, host=None, port=None)


def default_startup_settings() -> StartupSettings:
    return StartupSettings(
        healthcheck=StartupHealthcheckSettings(
            enabled=False,
            timeout_seconds=DEFAULT_STARTUP_HEALTHCHECK_TIMEOUT_SECONDS,
        )
    )


def _read_enabled_plugins(yaml_cfg: dict[str, Any]) -> tuple[str, ...]:
    if "plugins" not in yaml_cfg:
        raise RuntimeError("Missing plugins section in config.yaml.")
    yaml_plugins = yaml_cfg["plugins"]
    if not isinstance(yaml_plugins, dict):
        raise RuntimeError("Invalid plugins section in config.yaml. Expected a mapping.")
    if "enabled" not in yaml_plugins:
        raise RuntimeError("Missing plugins.enabled in config.yaml.")
    raw_enabled = yaml_plugins["enabled"]
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
    yaml_log_search = yaml_cfg.get("log_search")
    if not yaml_log_search:
        return None
    if not isinstance(yaml_log_search, dict):
        raise RuntimeError(
            "Invalid log_search section in config.yaml. Expected a mapping."
        )

    log_base_dir = str(yaml_log_search.get("log_base_dir", "")).strip()
    return LogSearchSettings(
        log_base_dir=log_base_dir,
    )


def _read_startup_settings(yaml_cfg: dict[str, Any]) -> StartupSettings:
    yaml_startup = yaml_cfg.get("startup", {})
    if not isinstance(yaml_startup, dict):
        raise RuntimeError("Invalid startup section in config.yaml. Expected a mapping.")

    yaml_healthcheck = yaml_startup.get("healthcheck", {})
    if not isinstance(yaml_healthcheck, dict):
        raise RuntimeError(
            "Invalid startup.healthcheck in config.yaml. Expected a mapping."
        )

    raw_enabled = yaml_healthcheck.get("enabled", False)
    if not isinstance(raw_enabled, bool):
        raise RuntimeError(
            "Invalid startup.healthcheck.enabled in config.yaml. Expected true/false."
        )

    raw_timeout_seconds = yaml_healthcheck.get(
        "timeout_seconds",
        DEFAULT_STARTUP_HEALTHCHECK_TIMEOUT_SECONDS,
    )
    try:
        timeout_seconds = int(raw_timeout_seconds)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(
            "Invalid startup.healthcheck.timeout_seconds in config.yaml. Expected an integer."
        ) from exc

    return StartupSettings(
        healthcheck=StartupHealthcheckSettings(
            enabled=raw_enabled,
            timeout_seconds=timeout_seconds,
        )
    )


def _read_bool_env(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(
        f"Invalid {name} in environment or .env. Expected true/false."
    )


def _read_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        return int(raw_value.strip())
    except ValueError as exc:
        raise RuntimeError(
            f"Invalid {name} in environment or .env. Expected an integer."
        ) from exc


def _read_database_type() -> str:
    return os.getenv("DB_TYPE", "").strip().lower()


def _default_db_port(db_type: str) -> int:
    return DEFAULT_DB_PORTS.get(db_type, DEFAULT_DB_PORTS[DB_TYPE_SQLSERVER])


def _default_db_driver(db_type: str) -> str:
    if db_type == DB_TYPE_SQLSERVER:
        return DEFAULT_DB_DRIVER
    return ""


def validate_settings(settings: Settings) -> None:
    errors: list[str] = []

    if settings.startup.healthcheck.timeout_seconds <= 0:
        errors.append(
            "startup: startup.healthcheck.timeout_seconds must be greater than 0"
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
                "log_search: missing log_search section in config.yaml"
            )
        else:
            if not settings.log_search.log_base_dir:
                errors.append(
                    "log_search: missing log_search.log_base_dir in config.yaml"
                )

    if "database" in settings.enabled_plugins:
        if settings.database is None:
            errors.append("database: missing database settings in environment or .env")
        else:
            if settings.database.db_type not in SUPPORTED_DB_TYPES:
                supported_values = ", ".join(sorted(SUPPORTED_DB_TYPES))
                errors.append(
                    "database: DB_TYPE must be one of the supported values: "
                    f"{supported_values}"
                )
            if not settings.database.host:
                errors.append("database: missing DB_HOST in environment or .env")
            if not settings.database.user:
                errors.append("database: missing DB_USER in environment or .env")
            if not settings.database.password:
                errors.append("database: missing DB_PASSWORD in environment or .env")
            if not settings.database.default_database:
                errors.append("database: missing DB_NAME in environment or .env")
            if (
                settings.database.db_type == DB_TYPE_SQLSERVER
                and not settings.database.driver
            ):
                errors.append("database: missing DB_DRIVER in environment or .env")
            if settings.database.port <= 0:
                errors.append("database: DB_PORT must be greater than 0")
            if settings.database.connect_timeout_seconds <= 0:
                errors.append(
                    "database: DB_CONNECT_TIMEOUT_SECONDS must be greater than 0"
                )

    if errors:
        lines = "\n".join(f"- {item}" for item in errors)
        raise RuntimeError(f"Invalid configuration for enabled plugins:\n{lines}")


def get_settings() -> Settings:
    load_env_file()
    yaml_cfg = load_yaml_config()

    server = default_server_settings()
    startup = _read_startup_settings(yaml_cfg)
    enabled_plugins = _read_enabled_plugins(yaml_cfg)
    log_search = _read_log_search_settings(yaml_cfg)

    # sensitive values — only from environment
    webhook_url = os.getenv("DINGTALK_WEBHOOK_URL", "").strip()
    dingtalk_secret = os.getenv("DINGTALK_SECRET", "").strip() or None

    jira_base_url = os.getenv("JIRA_BASE_URL", "").strip() or None
    jira_api_token = os.getenv("JIRA_API_TOKEN", "").strip() or None
    jira_project_key = os.getenv("JIRA_PROJECT_KEY", "").strip() or None
    database_type = _read_database_type()
    database = DatabaseSettings(
        db_type=database_type,
        host=os.getenv("DB_HOST", "").strip(),
        port=_read_int_env("DB_PORT", _default_db_port(database_type)),
        user=os.getenv("DB_USER", "").strip(),
        password=os.getenv("DB_PASSWORD", "").strip(),
        default_database=os.getenv("DB_NAME", "").strip(),
        driver=os.getenv("DB_DRIVER", _default_db_driver(database_type)).strip(),
        trust_server_certificate=_read_bool_env(
            "DB_TRUST_SERVER_CERTIFICATE", False
        ),
        connect_timeout_seconds=_read_int_env(
            "DB_CONNECT_TIMEOUT_SECONDS",
            DEFAULT_DB_CONNECT_TIMEOUT_SECONDS,
        ),
    )

    # non-sensitive values — only from config.yaml
    yaml_logging = yaml_cfg.get("logging", {})
    if not isinstance(yaml_logging, dict):
        raise RuntimeError("Invalid logging section in config.yaml. Expected a mapping.")
    log_dir_raw = str(yaml_logging.get("dir", "logs")).strip() or "logs"
    log_level = str(yaml_logging.get("level", "info")).strip().lower() or "info"
    if log_level not in LOG_LEVELS:
        valid_levels = ", ".join(sorted(LOG_LEVELS))
        raise RuntimeError(
            "Invalid logging.level in config.yaml. "
            f"Expected one of: {valid_levels}."
        )

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
        startup=startup,
        dingtalk_webhook_url=webhook_url,
        dingtalk_secret=dingtalk_secret,
        jira_base_url=jira_base_url,
        jira_api_token=jira_api_token,
        jira_project_key=jira_project_key,
        log_dir=Path(log_dir_raw),
        log_level=log_level,
        enabled_plugins=enabled_plugins,
        jira_latest_assigned_statuses=jira_latest_assigned_statuses,
        jira_start_target_status=jira_start_target_status,
        jira_resolve_target_status=jira_resolve_target_status,
        jira_attachment_max_images=jira_attachment_max_images,
        jira_attachment_max_bytes=jira_attachment_max_bytes,
        log_search=log_search,
        database=database,
    )
    validate_settings(settings)
    return settings
