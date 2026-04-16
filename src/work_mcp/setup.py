from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .config import (
    CONFIG_FILE_LABEL,
    DB_TYPE_MYSQL,
    DB_TYPE_SQLSERVER,
    ConfigError,
    DEFAULT_DB_DRIVER,
    DEFAULT_DB_PORTS,
    PROJECT_ROOT,
    YAML_CONFIG_FILE,
    _format_yaml_error,
)

OPTIONAL_PLUGIN_DATABASE = "database"
OPTIONAL_PLUGIN_LOG_SEARCH = "log_search"
OPTIONAL_PLUGIN_DINGTALK = "dingtalk"
OPTIONAL_PLUGIN_JIRA = "jira"
DEFAULT_JIRA_LATEST_ASSIGNED_STATUSES = ("重新打开", "ToDo")
DEFAULT_JIRA_START_TARGET_STATUS = "已接受"
DEFAULT_JIRA_RESOLVE_TARGET_STATUS = "已解决"
DEFAULT_JIRA_ATTACHMENT_MAX_IMAGES = 5
DEFAULT_JIRA_ATTACHMENT_MAX_BYTES = 1_048_576


@dataclass(frozen=True)
class SetupAnswers:
    enable_database: bool
    db_type: str
    host: str
    port: int
    user: str
    password: str
    driver: str
    trust_server_certificate: bool
    connect_timeout_seconds: int
    enable_log_search: bool
    log_base_dir: str
    enable_dingtalk: bool
    dingtalk_webhook_url: str
    dingtalk_secret: str
    enable_jira: bool
    jira_base_url: str
    jira_api_token: str
    jira_project_key: str


def yaml_config_path(project_root: Path = PROJECT_ROOT) -> Path:
    return project_root / YAML_CONFIG_FILE


def load_existing_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open(encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle) or {}
    except OSError as exc:
        raise ConfigError(
            f"Cannot read {CONFIG_FILE_LABEL} at {path}: {exc.strerror or exc}"
        ) from None
    except yaml.YAMLError as exc:
        raise ConfigError(_format_yaml_error(path, exc)) from None
    if not isinstance(loaded, dict):
        raise ConfigError(
            f"Invalid {CONFIG_FILE_LABEL} at {path}: expected a mapping at the document root."
        )
    return loaded


def build_updated_yaml(existing_yaml: dict[str, Any], answers: SetupAnswers) -> dict[str, Any]:
    updated = dict(existing_yaml)

    enabled_plugins = [
        plugin
        for plugin in _coerce_enabled_plugins(updated.get("plugins"))
        if plugin
        not in {
            OPTIONAL_PLUGIN_DATABASE,
            OPTIONAL_PLUGIN_LOG_SEARCH,
            OPTIONAL_PLUGIN_DINGTALK,
            OPTIONAL_PLUGIN_JIRA,
        }
    ]
    if answers.enable_database:
        enabled_plugins.append(OPTIONAL_PLUGIN_DATABASE)
    if answers.enable_log_search:
        enabled_plugins.append(OPTIONAL_PLUGIN_LOG_SEARCH)
    if answers.enable_dingtalk and OPTIONAL_PLUGIN_DINGTALK not in enabled_plugins:
        enabled_plugins.append(OPTIONAL_PLUGIN_DINGTALK)
    if answers.enable_jira and OPTIONAL_PLUGIN_JIRA not in enabled_plugins:
        enabled_plugins.append(OPTIONAL_PLUGIN_JIRA)
    updated["plugins"] = {"enabled": enabled_plugins}

    if answers.enable_log_search:
        log_search_section = updated.get("log_search")
        if not isinstance(log_search_section, dict):
            log_search_section = {}
        log_search_section["log_base_dir"] = answers.log_base_dir
        updated["log_search"] = log_search_section

    if answers.enable_dingtalk:
        dingtalk_section: dict[str, Any] = {"webhook_url": answers.dingtalk_webhook_url}
        if answers.dingtalk_secret:
            dingtalk_section["secret"] = answers.dingtalk_secret
        updated["dingtalk"] = dingtalk_section

    if answers.enable_jira:
        existing_jira = updated.get("jira")
        jira_section: dict[str, Any] = existing_jira if isinstance(existing_jira, dict) else {}
        jira_section["base_url"] = answers.jira_base_url
        jira_section["api_token"] = answers.jira_api_token
        jira_section["project_key"] = answers.jira_project_key
        jira_section.setdefault(
            "latest_assigned_statuses", list(DEFAULT_JIRA_LATEST_ASSIGNED_STATUSES)
        )
        jira_section.setdefault("start_target_status", DEFAULT_JIRA_START_TARGET_STATUS)
        jira_section.setdefault("resolve_target_status", DEFAULT_JIRA_RESOLVE_TARGET_STATUS)
        jira_section.setdefault(
            "attachments",
            {
                "max_images": DEFAULT_JIRA_ATTACHMENT_MAX_IMAGES,
                "max_bytes_per_image": DEFAULT_JIRA_ATTACHMENT_MAX_BYTES,
            },
        )
        updated["jira"] = jira_section

    if answers.enable_database:
        database_section: dict[str, Any] = {
            "type": answers.db_type,
            "host": answers.host,
            "port": answers.port,
            "user": answers.user,
            "password": answers.password,
            "connect_timeout_seconds": answers.connect_timeout_seconds,
        }
        if answers.db_type == DB_TYPE_SQLSERVER:
            database_section["driver"] = answers.driver
            database_section["trust_server_certificate"] = answers.trust_server_certificate
        updated["database"] = database_section

    return updated


def write_yaml_file(path: Path, values: dict[str, Any]) -> None:
    dumped = yaml.safe_dump(values, sort_keys=False, allow_unicode=True)
    path.write_text(dumped, encoding="utf-8")


def format_bool(value: bool) -> str:
    return "true" if value else "false"


def parse_bool_text(raw_value: str) -> bool:
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise RuntimeError("Expected a boolean value.")


def mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 4:
        return "*" * len(value)
    return f"{value[:2]}{'*' * (len(value) - 4)}{value[-2:]}"


def current_value_label(field_name: str, value: str) -> str:
    if field_name in {"password", "secret", "api_token"}:
        return mask_secret(value)
    return value


def normalize_text_value(raw_value: Any) -> str:
    if raw_value is None:
        return ""
    return str(raw_value).strip()


def validate_log_base_dir(raw_value: str) -> str:
    value = raw_value.strip()
    if not value:
        raise RuntimeError("log_base_dir is required.")
    path = Path(value)
    if not path.is_absolute():
        raise RuntimeError("log_base_dir must be an absolute path.")
    if not path.exists():
        raise RuntimeError("log_base_dir does not exist.")
    if not path.is_dir():
        raise RuntimeError("log_base_dir must point to a directory.")
    return value


def validate_required_text(raw_value: str, field_name: str) -> str:
    value = raw_value.strip()
    if not value:
        raise RuntimeError(f"{field_name} is required.")
    return value


def validate_port(raw_value: str, field_name: str) -> int:
    value = validate_positive_int(raw_value, field_name)
    if value > 65535:
        raise RuntimeError(f"{field_name} must be less than or equal to 65535.")
    return value


def validate_positive_int(raw_value: str, field_name: str) -> int:
    try:
        value = int(raw_value.strip())
    except ValueError as exc:
        raise RuntimeError(f"{field_name} must be an integer.") from exc
    if value <= 0:
        raise RuntimeError(f"{field_name} must be greater than 0.")
    return value


def validate_sqlserver_driver(raw_value: str) -> str:
    value = validate_required_text(raw_value, "database.driver")
    available = get_installed_odbc_drivers()
    if available is None:
        raise RuntimeError(
            "未安装 Python 依赖 pyodbc，请先执行 `uv sync`。"
        )
    if not available:
        raise RuntimeError(
            "未检测到可用的 SQL Server ODBC driver，请先在本机安装后再继续。"
        )
    if value not in available:
        joined = ", ".join(available)
        raise RuntimeError(
            f"未找到 ODBC driver '{value}'。当前已安装: {joined}。"
        )
    return value


def is_database_config_complete(yaml_db: dict) -> bool:
    """Return True when all required database fields are present and non-empty."""
    if not isinstance(yaml_db, dict):
        return False
    db_type = normalize_text_value(yaml_db.get("type")).lower()
    if db_type not in {DB_TYPE_MYSQL, DB_TYPE_SQLSERVER}:
        return False
    required = ["host", "port", "user", "password"]
    if db_type == DB_TYPE_SQLSERVER:
        required.append("driver")
    return all(normalize_text_value(yaml_db.get(key)) for key in required)


def is_jira_config_complete(yaml_jira: dict) -> bool:
    """Return True when all required Jira fields are present and non-empty."""
    if not isinstance(yaml_jira, dict):
        return False
    return all(normalize_text_value(yaml_jira.get(key)) for key in ("base_url", "api_token", "project_key"))


def is_log_search_config_complete(yaml_log_search: dict) -> bool:
    """Return True when log_base_dir is present and non-empty."""
    if not isinstance(yaml_log_search, dict):
        return False
    return bool(normalize_text_value(yaml_log_search.get("log_base_dir")))


def get_installed_odbc_drivers() -> list[str] | None:
    try:
        import pyodbc
    except ImportError:
        return None
    return sorted(str(item) for item in pyodbc.drivers())


def yaml_value(project_root: Path) -> dict[str, Any]:
    return load_existing_yaml(yaml_config_path(project_root))


def default_port_for_db(db_type: str) -> int:
    return DEFAULT_DB_PORTS[db_type]


def default_driver_for_db(db_type: str) -> str:
    if db_type == DB_TYPE_SQLSERVER:
        return DEFAULT_DB_DRIVER
    return ""


def _coerce_enabled_plugins(raw_plugins: Any) -> list[str]:
    if not isinstance(raw_plugins, dict):
        return []
    raw_enabled = raw_plugins.get("enabled", [])
    if not isinstance(raw_enabled, list):
        return []
    return [str(item).strip() for item in raw_enabled if str(item).strip()]
