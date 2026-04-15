from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


YAML_CONFIG_FILE = "config.yaml"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOG_LEVELS = frozenset({"debug", "info", "warning", "error"})
KNOWN_PLUGINS = frozenset({"database", "dingtalk", "jira", "log_search", "remote_fs"})
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
CONFIG_FILE_LABEL = "config.yaml"


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
class AllowedRoot:
    name: str
    path: Path
    kind: str
    description: str


@dataclass(frozen=True)
class RemoteFsSettings:
    roots: tuple[AllowedRoot, ...]


@dataclass(frozen=True)
class DatabaseSettings:
    db_type: str
    host: str
    port: int
    user: str
    password: str
    driver: str
    trust_server_certificate: bool
    connect_timeout_seconds: int


@dataclass(frozen=True)
class Settings:
    server: ServerSettings
    startup: StartupSettings
    dingtalk_webhook_url: str
    dingtalk_secret: str | None
    jira_base_url: str | None
    jira_api_token: str | None
    jira_project_key: str | None
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
    remote_fs: RemoteFsSettings | None = None


class ConfigError(RuntimeError):
    """User-fixable configuration error."""


def _config_error(message: str) -> ConfigError:
    return ConfigError(message)


def _format_yaml_error(path: Path, exc: yaml.YAMLError) -> str:
    mark = getattr(exc, "problem_mark", None)
    problem = getattr(exc, "problem", None)
    detail = str(problem or exc).strip()
    if mark is None:
        return f"Invalid {CONFIG_FILE_LABEL} at {path}: YAML syntax error: {detail}"
    line = mark.line + 1
    column = mark.column + 1
    return (
        f"Invalid {CONFIG_FILE_LABEL} at {path}: "
        f"YAML syntax error at line {line}, column {column}: {detail}"
    )


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle) or {}
    except OSError as exc:
        raise _config_error(f"Cannot read {CONFIG_FILE_LABEL} at {path}: {exc.strerror or exc}") from None
    except yaml.YAMLError as exc:
        raise _config_error(_format_yaml_error(path, exc)) from None
    if not isinstance(loaded, dict):
        raise _config_error(
            f"Invalid {CONFIG_FILE_LABEL} at {path}: expected a mapping at the document root."
        )
    return loaded


def _read_int(raw_value: Any, field_name: str) -> int:
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        raise _config_error(
            f"Invalid {field_name} in {CONFIG_FILE_LABEL}. Expected an integer."
        ) from None


def load_yaml_config(yaml_path: Path | None = None) -> dict[str, Any]:
    """Load configuration from config.yaml."""
    path = yaml_path or PROJECT_ROOT / YAML_CONFIG_FILE
    if not path.exists():
        return {}
    return _load_yaml_mapping(path)


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


def _read_string_list(section: dict[str, Any], key: str, section_name: str) -> tuple[str, ...]:
    raw_value = section.get(key, [])
    if not isinstance(raw_value, list):
        raise RuntimeError(f"Invalid {section_name}.{key} in config.yaml. Expected a list.")
    return tuple(str(item).strip() for item in raw_value if str(item).strip())


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
    timeout_seconds = _read_int(
        raw_timeout_seconds,
        "startup.healthcheck.timeout_seconds",
    )

    return StartupSettings(
        healthcheck=StartupHealthcheckSettings(
            enabled=raw_enabled,
            timeout_seconds=timeout_seconds,
        )
    )


def _read_logging_settings(yaml_cfg: dict[str, Any]) -> tuple[Path, str]:
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
    return Path(log_dir_raw), log_level


def _read_text(raw_value: Any) -> str:
    if raw_value is None:
        return ""
    return str(raw_value).strip()


def _read_log_search_settings(yaml_cfg: dict[str, Any]) -> LogSearchSettings | None:
    yaml_log_search = yaml_cfg.get("log_search")
    if not yaml_log_search:
        return None
    if not isinstance(yaml_log_search, dict):
        raise RuntimeError(
            "Invalid log_search section in config.yaml. Expected a mapping."
        )
    log_base_dir = _read_text(yaml_log_search.get("log_base_dir"))
    return LogSearchSettings(log_base_dir=log_base_dir)


def _read_remote_fs_settings(yaml_cfg: dict[str, Any]) -> RemoteFsSettings | None:
    yaml_remote_fs = yaml_cfg.get("remote_fs")
    if not yaml_remote_fs:
        return None
    if not isinstance(yaml_remote_fs, dict):
        raise RuntimeError(
            "Invalid remote_fs section in config.yaml. Expected a mapping."
        )
    raw_roots = yaml_remote_fs.get("roots", [])
    if not isinstance(raw_roots, list):
        raise RuntimeError(
            "Invalid remote_fs.roots in config.yaml. Expected a list."
        )
    roots: list[AllowedRoot] = []
    for idx, raw_root in enumerate(raw_roots):
        if not isinstance(raw_root, dict):
            raise RuntimeError(
                f"Invalid remote_fs.roots[{idx}] in config.yaml. Expected a mapping."
            )
        name = _read_text(raw_root.get("name"))
        raw_path = _read_text(raw_root.get("path"))
        kind = _read_text(raw_root.get("kind"))
        description = _read_text(raw_root.get("description"))
        if not name:
            raise RuntimeError(
                f"Missing remote_fs.roots[{idx}].name in config.yaml."
            )
        if not raw_path:
            raise RuntimeError(
                f"Missing remote_fs.roots[{idx}].path in config.yaml."
            )
        if not kind:
            raise RuntimeError(
                f"Missing remote_fs.roots[{idx}].kind in config.yaml."
            )
        if not description:
            raise RuntimeError(
                f"Missing remote_fs.roots[{idx}].description in config.yaml."
            )
        resolved = Path(raw_path).resolve()
        if not resolved.exists():
            raise RuntimeError(
                f"remote_fs.roots[{idx}].path does not exist: {raw_path}"
            )
        if not resolved.is_dir():
            raise RuntimeError(
                f"remote_fs.roots[{idx}].path is not a directory: {raw_path}"
            )
        roots.append(AllowedRoot(
            name=name, path=resolved, kind=kind, description=description,
        ))
    return RemoteFsSettings(roots=tuple(roots))


def _read_dingtalk_settings(yaml_cfg: dict[str, Any]) -> tuple[str, str | None]:
    yaml_dingtalk = yaml_cfg.get("dingtalk", {})
    if not isinstance(yaml_dingtalk, dict):
        raise RuntimeError("Invalid dingtalk section in config.yaml. Expected a mapping.")
    webhook_url = _read_text(yaml_dingtalk.get("webhook_url"))
    secret = _read_text(yaml_dingtalk.get("secret")) or None
    return webhook_url, secret


def _read_jira_settings(yaml_cfg: dict[str, Any]) -> dict[str, Any]:
    yaml_jira = yaml_cfg.get("jira", {})
    if not isinstance(yaml_jira, dict):
        raise RuntimeError("Invalid jira section in config.yaml. Expected a mapping.")

    base_url = _read_text(yaml_jira.get("base_url")) or None
    api_token = _read_text(yaml_jira.get("api_token")) or None
    project_key = _read_text(yaml_jira.get("project_key")) or None
    latest_assigned_statuses = _read_string_list(
        yaml_jira, "latest_assigned_statuses", "jira"
    )
    start_target_status = _read_text(yaml_jira.get("start_target_status"))
    resolve_target_status = _read_text(yaml_jira.get("resolve_target_status"))

    yaml_attachments = yaml_jira.get("attachments", {})
    if not isinstance(yaml_attachments, dict):
        raise RuntimeError("Invalid jira.attachments in config.yaml. Expected a mapping.")
    max_images = _read_int(yaml_attachments.get("max_images", 5), "jira.attachments.max_images")
    max_bytes = _read_int(
        yaml_attachments.get("max_bytes_per_image", 1_048_576),
        "jira.attachments.max_bytes_per_image",
    )

    return {
        "jira_base_url": base_url,
        "jira_api_token": api_token,
        "jira_project_key": project_key,
        "jira_latest_assigned_statuses": latest_assigned_statuses,
        "jira_start_target_status": start_target_status,
        "jira_resolve_target_status": resolve_target_status,
        "jira_attachment_max_images": max_images,
        "jira_attachment_max_bytes": max_bytes,
    }


def _default_db_port(db_type: str) -> int:
    return DEFAULT_DB_PORTS.get(db_type, DEFAULT_DB_PORTS[DB_TYPE_SQLSERVER])


def _default_db_driver(db_type: str) -> str:
    if db_type == DB_TYPE_SQLSERVER:
        return DEFAULT_DB_DRIVER
    return ""


def _read_database_settings(yaml_cfg: dict[str, Any]) -> DatabaseSettings | None:
    yaml_db = yaml_cfg.get("database")
    if not yaml_db:
        return None
    if not isinstance(yaml_db, dict):
        raise RuntimeError("Invalid database section in config.yaml. Expected a mapping.")

    db_type = _read_text(yaml_db.get("type")).lower()

    raw_port = yaml_db.get("port", _default_db_port(db_type))
    port = _read_int(raw_port, "database.port")

    raw_trust_cert = yaml_db.get("trust_server_certificate", False)
    if not isinstance(raw_trust_cert, bool):
        raise RuntimeError(
            "Invalid database.trust_server_certificate in config.yaml. Expected true/false."
        )

    raw_timeout = yaml_db.get("connect_timeout_seconds", DEFAULT_DB_CONNECT_TIMEOUT_SECONDS)
    connect_timeout_seconds = _read_int(
        raw_timeout,
        "database.connect_timeout_seconds",
    )

    return DatabaseSettings(
        db_type=db_type,
        host=_read_text(yaml_db.get("host")),
        port=port,
        user=_read_text(yaml_db.get("user")),
        password=_read_text(yaml_db.get("password")),
        driver=_read_text(yaml_db.get("driver", _default_db_driver(db_type))),
        trust_server_certificate=raw_trust_cert,
        connect_timeout_seconds=connect_timeout_seconds,
    )


def validate_settings(settings: Settings) -> None:
    errors: list[str] = []

    if settings.startup.healthcheck.timeout_seconds <= 0:
        errors.append(
            "startup: startup.healthcheck.timeout_seconds must be greater than 0"
        )

    if "dingtalk" in settings.enabled_plugins and not settings.dingtalk_webhook_url:
        errors.append("dingtalk: missing dingtalk.webhook_url in config.yaml")

    if "jira" in settings.enabled_plugins:
        if not settings.jira_base_url:
            errors.append("jira: missing jira.base_url in config.yaml")
        if not settings.jira_api_token:
            errors.append("jira: missing jira.api_token in config.yaml")
        if not settings.jira_project_key:
            errors.append("jira: missing jira.project_key in config.yaml")
        if not settings.jira_latest_assigned_statuses:
            errors.append("jira: missing jira.latest_assigned_statuses in config.yaml")
        if not settings.jira_start_target_status:
            errors.append("jira: missing jira.start_target_status in config.yaml")
        if not settings.jira_resolve_target_status:
            errors.append("jira: missing jira.resolve_target_status in config.yaml")
        if settings.jira_attachment_max_images <= 0:
            errors.append("jira: jira.attachments.max_images must be greater than 0")
        if settings.jira_attachment_max_bytes <= 0:
            errors.append(
                "jira: jira.attachments.max_bytes_per_image must be greater than 0"
            )

    if "log_search" in settings.enabled_plugins:
        if settings.log_search is None:
            errors.append("log_search: missing log_search section in config.yaml")
        else:
            if not settings.log_search.log_base_dir:
                errors.append(
                    "log_search: missing log_search.log_base_dir in config.yaml"
                )

    if "remote_fs" in settings.enabled_plugins:
        if settings.remote_fs is None:
            errors.append("remote_fs: missing remote_fs section in config.yaml")
        elif not settings.remote_fs.roots:
            errors.append("remote_fs: remote_fs.roots must not be empty")

    if "database" in settings.enabled_plugins:
        if settings.database is None:
            errors.append("database: missing database section in config.yaml")
        else:
            if settings.database.db_type not in SUPPORTED_DB_TYPES:
                supported_values = ", ".join(sorted(SUPPORTED_DB_TYPES))
                errors.append(
                    "database: database.type must be one of the supported values: "
                    f"{supported_values}"
                )
            if not settings.database.host:
                errors.append("database: missing database.host in config.yaml")
            if not settings.database.user:
                errors.append("database: missing database.user in config.yaml")
            if not settings.database.password:
                errors.append("database: missing database.password in config.yaml")
            if (
                settings.database.db_type == DB_TYPE_SQLSERVER
                and not settings.database.driver
            ):
                errors.append("database: missing database.driver in config.yaml")
            if settings.database.port <= 0:
                errors.append("database: database.port must be greater than 0")
            if settings.database.connect_timeout_seconds <= 0:
                errors.append(
                    "database: database.connect_timeout_seconds must be greater than 0"
                )

    if errors:
        lines = "\n".join(f"- {item}" for item in errors)
        raise RuntimeError(f"Invalid configuration for enabled plugins:\n{lines}")


def get_settings() -> Settings:
    yaml_cfg = load_yaml_config()
    log_dir, log_level = _read_logging_settings(yaml_cfg)
    webhook_url, dingtalk_secret = _read_dingtalk_settings(yaml_cfg)
    jira_fields = _read_jira_settings(yaml_cfg)
    settings = Settings(
        server=default_server_settings(),
        startup=_read_startup_settings(yaml_cfg),
        log_dir=log_dir,
        log_level=log_level,
        enabled_plugins=_read_enabled_plugins(yaml_cfg),
        log_search=_read_log_search_settings(yaml_cfg),
        database=_read_database_settings(yaml_cfg),
        remote_fs=_read_remote_fs_settings(yaml_cfg),
        dingtalk_webhook_url=webhook_url,
        dingtalk_secret=dingtalk_secret,
        **jira_fields,
    )
    validate_settings(settings)
    return settings
