from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
from typing import Any

import yaml

from .config import (
    DB_TYPE_MYSQL,
    DB_TYPE_SQLSERVER,
    DEFAULT_DB_CONNECT_TIMEOUT_SECONDS,
    DEFAULT_DB_DRIVER,
    DEFAULT_DB_PORTS,
    PROJECT_ROOT,
    YAML_CONFIG_FILE,
)
from .tools.database.factory import check_database_connectivity

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
    database_name: str
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


@dataclass(frozen=True)
class DiagnosticResult:
    level: str
    message: str


def yaml_config_path(project_root: Path = PROJECT_ROOT) -> Path:
    return project_root / YAML_CONFIG_FILE


def load_existing_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    if not isinstance(loaded, dict):
        raise RuntimeError("Invalid config.yaml. Expected a mapping at the document root.")
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
            "name": answers.database_name,
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
    required = ["host", "port", "user", "password", "name"]
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


def diagnose(project_root: Path = PROJECT_ROOT) -> list[DiagnosticResult]:
    results: list[DiagnosticResult] = [_diagnose_uv()]

    yaml_path = yaml_config_path(project_root)
    results.append(_file_result(yaml_path, "config"))

    try:
        yaml_values = load_existing_yaml(yaml_path)
    except RuntimeError as exc:
        results.append(DiagnosticResult("error", str(exc)))
        return results

    plugin_names = _coerce_enabled_plugins(yaml_values.get("plugins"))
    if plugin_names:
        results.append(DiagnosticResult("ok", f"enabled plugins: {', '.join(plugin_names)}"))
    else:
        results.append(DiagnosticResult("ok", "enabled plugins: none"))

    if OPTIONAL_PLUGIN_DATABASE in plugin_names:
        yaml_db = yaml_values.get("database")
        if not isinstance(yaml_db, dict):
            results.append(DiagnosticResult("error", "database section is missing from config.yaml"))
        else:
            db_type = normalize_text_value(yaml_db.get("type")).lower()
            if not db_type:
                results.append(DiagnosticResult("error", "database.type is missing from config.yaml"))
            elif db_type not in {DB_TYPE_MYSQL, DB_TYPE_SQLSERVER}:
                results.append(
                    DiagnosticResult("error", "database.type must be either 'mysql' or 'sqlserver'")
                )
            else:
                results.append(DiagnosticResult("ok", f"database.type = {db_type}"))

            required_keys = ["host", "user", "password", "name"]
            if db_type == DB_TYPE_SQLSERVER:
                required_keys.append("driver")
            for key in required_keys:
                if normalize_text_value(yaml_db.get(key)):
                    results.append(DiagnosticResult("ok", f"database.{key} is set"))
                else:
                    results.append(
                        DiagnosticResult("error", f"database.{key} is missing from config.yaml")
                    )

            timeout_raw = yaml_db.get("connect_timeout_seconds")
            if timeout_raw is not None:
                try:
                    validate_positive_int(str(timeout_raw), "database.connect_timeout_seconds")
                except RuntimeError as exc:
                    results.append(DiagnosticResult("error", str(exc)))
                else:
                    results.append(DiagnosticResult("ok", "database.connect_timeout_seconds is valid"))
            else:
                results.append(
                    DiagnosticResult("ok", "database.connect_timeout_seconds will use the default")
                )

            if db_type == DB_TYPE_SQLSERVER:
                installed_drivers = get_installed_odbc_drivers()
                if installed_drivers is None:
                    results.append(
                        DiagnosticResult("error", "未安装 Python 依赖 pyodbc，请先执行 `uv sync`。")
                    )
                elif not installed_drivers:
                    results.append(
                        DiagnosticResult(
                            "error",
                            "未检测到可用的 SQL Server ODBC driver，请先在本机安装后再继续。",
                        )
                    )
                else:
                    driver_name = normalize_text_value(yaml_db.get("driver"))
                    if driver_name and driver_name in installed_drivers:
                        results.append(
                            DiagnosticResult("ok", f"ODBC driver found: {driver_name}")
                        )
                    else:
                        joined = ", ".join(installed_drivers) if installed_drivers else "none"
                        results.append(
                            DiagnosticResult(
                                "error",
                                f"Configured ODBC driver was not found. Installed drivers: {joined}.",
                            )
                        )

            if _can_run_database_probe(yaml_db):
                timeout_seconds = int(
                    yaml_db.get("connect_timeout_seconds", DEFAULT_DB_CONNECT_TIMEOUT_SECONDS)
                )
                try:
                    probe = _probe_database_connectivity(
                        _build_database_settings(yaml_db),
                        timeout_seconds=timeout_seconds,
                    )
                except RuntimeError as exc:
                    results.append(
                        DiagnosticResult("error", f"database connectivity failed: {exc}")
                    )
                else:
                    database_name = str(probe.get("database_name", ""))
                    results.append(
                        DiagnosticResult(
                            "ok",
                            f"database connectivity succeeded for {database_name or 'configured database'}",
                        )
                    )

    if OPTIONAL_PLUGIN_LOG_SEARCH in plugin_names:
        log_search_section = yaml_values.get("log_search")
        if not isinstance(log_search_section, dict):
            results.append(
                DiagnosticResult("error", "log_search section is missing from config.yaml")
            )
        else:
            raw_log_base_dir = normalize_text_value(log_search_section.get("log_base_dir"))
            try:
                validated = validate_log_base_dir(raw_log_base_dir)
            except RuntimeError as exc:
                results.append(DiagnosticResult("error", str(exc)))
            else:
                results.append(DiagnosticResult("ok", f"log_base_dir = {validated}"))

    if OPTIONAL_PLUGIN_DINGTALK in plugin_names:
        yaml_dingtalk = yaml_values.get("dingtalk")
        webhook = str(yaml_dingtalk.get("webhook_url", "") if isinstance(yaml_dingtalk, dict) else "").strip()
        if webhook:
            results.append(DiagnosticResult("ok", "dingtalk.webhook_url is set"))
        else:
            results.append(
                DiagnosticResult("error", "dingtalk.webhook_url is missing from config.yaml")
            )

    if OPTIONAL_PLUGIN_JIRA in plugin_names:
        yaml_jira = yaml_values.get("jira")
        if not isinstance(yaml_jira, dict):
            results.append(DiagnosticResult("error", "jira section is missing from config.yaml"))
        else:
            for key in ("base_url", "api_token", "project_key"):
                if normalize_text_value(yaml_jira.get(key)):
                    results.append(DiagnosticResult("ok", f"jira.{key} is set"))
                else:
                    results.append(
                        DiagnosticResult("error", f"jira.{key} is missing from config.yaml")
                    )

            latest_statuses = yaml_jira.get("latest_assigned_statuses", [])
            if isinstance(latest_statuses, list) and any(
                normalize_text_value(item) for item in latest_statuses
            ):
                results.append(DiagnosticResult("ok", "jira.latest_assigned_statuses is set"))
            else:
                results.append(
                    DiagnosticResult(
                        "error", "jira.latest_assigned_statuses is missing from config.yaml"
                    )
                )

            for key in ("start_target_status", "resolve_target_status"):
                if normalize_text_value(yaml_jira.get(key)):
                    results.append(DiagnosticResult("ok", f"jira.{key} is set"))
                else:
                    results.append(
                        DiagnosticResult("error", f"jira.{key} is missing from config.yaml")
                    )

    return results


def has_errors(results: list[DiagnosticResult]) -> bool:
    return any(result.level == "error" for result in results)


def connectivity_hint(project_root: Path = PROJECT_ROOT) -> str:
    yaml_path = yaml_config_path(project_root)
    try:
        yaml_values = load_existing_yaml(yaml_path)
    except RuntimeError:
        return ""
    plugin_names = _coerce_enabled_plugins(yaml_values.get("plugins"))
    items = []
    if OPTIONAL_PLUGIN_DATABASE in plugin_names:
        items.append("数据库是否从当前机器可以连通")
    if OPTIONAL_PLUGIN_JIRA in plugin_names:
        items.append("Jira 是否从当前机器可以连通")
    if not items:
        return ""
    return "请检查：" + "、".join(items) + "。"


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


def _diagnose_uv() -> DiagnosticResult:
    if shutil.which("uv"):
        return DiagnosticResult("ok", "uv is available")
    return DiagnosticResult("error", "uv is not installed or not on PATH")


def _file_result(path: Path, label: str) -> DiagnosticResult:
    if path.exists():
        return DiagnosticResult("ok", f"{label} file found: {path.name}")
    return DiagnosticResult("warn", f"{label} file not found: {path.name}")


def _can_run_database_probe(yaml_db: dict[str, Any]) -> bool:
    db_type = normalize_text_value(yaml_db.get("type")).lower()
    if db_type not in {DB_TYPE_MYSQL, DB_TYPE_SQLSERVER}:
        return False
    required_keys = ["host", "user", "password", "name"]
    if db_type == DB_TYPE_SQLSERVER:
        required_keys.append("driver")
    return all(normalize_text_value(yaml_db.get(key)) for key in required_keys)


def _probe_database_connectivity(
    settings: Any,
    *,
    timeout_seconds: int,
) -> dict[str, str]:
    result_queue: Queue[tuple[bool, object]] = Queue(maxsize=1)

    def worker() -> None:
        try:
            result = check_database_connectivity(
                settings,
                timeout_seconds=timeout_seconds,
            )
        except Exception as _exc:
            result_queue.put((False, _exc))
            return
        result_queue.put((True, result))

    thread = Thread(target=worker, daemon=True)
    thread.start()
    thread.join(timeout_seconds)

    if thread.is_alive():
        raise RuntimeError(f"timed out after {timeout_seconds} seconds")

    try:
        ok, payload = result_queue.get_nowait()
    except Empty as exc:
        raise RuntimeError("probe finished without returning a result") from exc

    if ok:
        return payload  # type: ignore[return-value]
    raise RuntimeError(str(payload))


def _build_database_settings(yaml_db: dict[str, Any]) -> Any:
    from .config import DatabaseSettings

    db_type = normalize_text_value(yaml_db.get("type")).lower()
    raw_trust_cert = yaml_db.get("trust_server_certificate", False)
    trust_server_certificate = bool(raw_trust_cert) if db_type == DB_TYPE_SQLSERVER else False
    return DatabaseSettings(
        db_type=db_type,
        host=normalize_text_value(yaml_db.get("host")),
        port=int(yaml_db.get("port", DEFAULT_DB_PORTS.get(db_type, 1433))),
        user=normalize_text_value(yaml_db.get("user")),
        password=normalize_text_value(yaml_db.get("password")),
        default_database=normalize_text_value(yaml_db.get("name")),
        driver=normalize_text_value(yaml_db.get("driver")),
        trust_server_certificate=trust_server_certificate,
        connect_timeout_seconds=int(
            yaml_db.get("connect_timeout_seconds", DEFAULT_DB_CONNECT_TIMEOUT_SECONDS)
        ),
    )
