from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .config import (
    DB_TYPE_MYSQL,
    DB_TYPE_SQLSERVER,
    DEFAULT_DB_CONNECT_TIMEOUT_SECONDS,
    DEFAULT_DB_DRIVER,
    DEFAULT_DB_PORTS,
    ENV_FILE_NAME,
    PROJECT_ROOT,
    YAML_CONFIG_FILE,
)
from .tools.database.factory import check_database_connectivity

SUPPORTED_DATABASE_CHOICES = (
    (1, DB_TYPE_MYSQL),
    (2, DB_TYPE_SQLSERVER),
)
DATABASE_CHOICE_BY_NUMBER = dict(SUPPORTED_DATABASE_CHOICES)
NO_YES_CHOICES = {
    "1": False,
    "2": True,
}
ENV_KEYS_MANAGED_BY_INIT = (
    "DB_TYPE",
    "DB_HOST",
    "DB_PORT",
    "DB_USER",
    "DB_PASSWORD",
    "DB_NAME",
    "DB_DRIVER",
    "DB_TRUST_SERVER_CERTIFICATE",
    "DB_CONNECT_TIMEOUT_SECONDS",
    "DINGTALK_WEBHOOK_URL",
    "DINGTALK_SECRET",
)
DEFAULT_PLUGIN_SET = ("database", "log_search")
OPTIONAL_PLUGIN_DINGTALK = "dingtalk"
@dataclass(frozen=True)
class SetupAnswers:
    db_type: str
    host: str
    port: int
    user: str
    password: str
    database_name: str
    driver: str
    trust_server_certificate: bool
    connect_timeout_seconds: int
    log_base_dir: str
    enable_dingtalk: bool
    dingtalk_webhook_url: str
    dingtalk_secret: str


@dataclass(frozen=True)
class DiagnosticResult:
    level: str
    message: str


def env_file_path(project_root: Path = PROJECT_ROOT) -> Path:
    return project_root / ENV_FILE_NAME


def yaml_config_path(project_root: Path = PROJECT_ROOT) -> Path:
    return project_root / YAML_CONFIG_FILE


def parse_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if key:
            values[key] = value
    return values


def load_existing_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    if not isinstance(loaded, dict):
        raise RuntimeError("Invalid config.yaml. Expected a mapping at the document root.")
    return loaded


def build_updated_env(existing_env: dict[str, str], answers: SetupAnswers) -> dict[str, str]:
    updated = dict(existing_env)
    updated["DB_TYPE"] = answers.db_type
    updated["DB_HOST"] = answers.host
    updated["DB_PORT"] = str(answers.port)
    updated["DB_USER"] = answers.user
    updated["DB_PASSWORD"] = answers.password
    updated["DB_NAME"] = answers.database_name
    updated["DB_CONNECT_TIMEOUT_SECONDS"] = str(answers.connect_timeout_seconds)

    if answers.db_type == DB_TYPE_SQLSERVER:
        updated["DB_DRIVER"] = answers.driver
        updated["DB_TRUST_SERVER_CERTIFICATE"] = format_bool(answers.trust_server_certificate)
    else:
        updated.pop("DB_DRIVER", None)
        updated.pop("DB_TRUST_SERVER_CERTIFICATE", None)

    if answers.enable_dingtalk:
        updated["DINGTALK_WEBHOOK_URL"] = answers.dingtalk_webhook_url
        updated["DINGTALK_SECRET"] = answers.dingtalk_secret
    else:
        updated.pop("DINGTALK_WEBHOOK_URL", None)
        updated.pop("DINGTALK_SECRET", None)

    return updated


def build_updated_yaml(existing_yaml: dict[str, Any], answers: SetupAnswers) -> dict[str, Any]:
    updated = dict(existing_yaml)

    enabled_plugins = [
        plugin
        for plugin in _coerce_enabled_plugins(updated.get("plugins"))
        if plugin != OPTIONAL_PLUGIN_DINGTALK and plugin != "jira"
    ]
    for plugin_name in DEFAULT_PLUGIN_SET:
        if plugin_name not in enabled_plugins:
            enabled_plugins.append(plugin_name)
    if answers.enable_dingtalk and OPTIONAL_PLUGIN_DINGTALK not in enabled_plugins:
        enabled_plugins.append(OPTIONAL_PLUGIN_DINGTALK)
    updated["plugins"] = {"enabled": enabled_plugins}

    log_search_section = updated.get("log_search")
    if not isinstance(log_search_section, dict):
        log_search_section = {}
    log_search_section["log_base_dir"] = answers.log_base_dir
    updated["log_search"] = log_search_section

    return updated


def write_env_file(path: Path, values: dict[str, str]) -> None:
    lines = [f"{key}={_quote_env_value(values[key])}" for key in sorted(values)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


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
    if field_name in {"DB_PASSWORD", "DINGTALK_SECRET"}:
        return mask_secret(value)
    return value


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
    value = validate_required_text(raw_value, "DB_DRIVER")
    available = get_installed_odbc_drivers()
    if available is None:
        raise RuntimeError(
            "pyodbc is not installed. Run `uv sync` before configuring SQL Server."
        )
    if value not in available:
        joined = ", ".join(available) if available else "none"
        raise RuntimeError(
            f"ODBC driver '{value}' was not found. Installed drivers: {joined}."
        )
    return value


def get_installed_odbc_drivers() -> list[str] | None:
    try:
        import pyodbc
    except ImportError:
        return None
    return sorted(str(item) for item in pyodbc.drivers())


def diagnose(project_root: Path = PROJECT_ROOT) -> list[DiagnosticResult]:
    results: list[DiagnosticResult] = []
    results.append(_diagnose_uv())

    env_path = env_file_path(project_root)
    yaml_path = yaml_config_path(project_root)

    env_values = parse_env_file(env_path)
    results.append(_file_result(env_path, "env"))
    results.append(_file_result(yaml_path, "config"))

    try:
        yaml_values = load_existing_yaml(yaml_path)
    except RuntimeError as exc:
        results.append(DiagnosticResult("error", str(exc)))
        return results

    db_type = env_values.get("DB_TYPE", "").strip().lower()
    if not db_type:
        results.append(DiagnosticResult("error", "DB_TYPE is missing from .env"))
    elif db_type not in {DB_TYPE_MYSQL, DB_TYPE_SQLSERVER}:
        results.append(
            DiagnosticResult(
                "error",
                "DB_TYPE must be either 'mysql' or 'sqlserver'",
            )
        )
    else:
        results.append(DiagnosticResult("ok", f"DB_TYPE = {db_type}"))

    required_env = ["DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME"]
    if db_type == DB_TYPE_SQLSERVER:
        required_env.extend(["DB_DRIVER", "DB_TRUST_SERVER_CERTIFICATE"])
    for key in required_env:
        if env_values.get(key, "").strip():
            results.append(DiagnosticResult("ok", f"{key} is set"))
        else:
            results.append(DiagnosticResult("error", f"{key} is missing from .env"))

    timeout_value = env_values.get("DB_CONNECT_TIMEOUT_SECONDS", "").strip()
    if timeout_value:
        try:
            validate_positive_int(timeout_value, "DB_CONNECT_TIMEOUT_SECONDS")
        except RuntimeError as exc:
            results.append(DiagnosticResult("error", str(exc)))
        else:
            results.append(DiagnosticResult("ok", "DB_CONNECT_TIMEOUT_SECONDS is valid"))
    else:
        results.append(DiagnosticResult("ok", "DB_CONNECT_TIMEOUT_SECONDS will use the default"))

    plugin_names = _coerce_enabled_plugins(yaml_values.get("plugins"))
    if plugin_names:
        results.append(DiagnosticResult("ok", f"enabled plugins: {', '.join(plugin_names)}"))
    else:
        results.append(DiagnosticResult("error", "plugins.enabled is missing or empty in config.yaml"))

    log_search_section = yaml_values.get("log_search")
    if not isinstance(log_search_section, dict):
        results.append(DiagnosticResult("error", "log_search section is missing from config.yaml"))
    else:
        raw_log_base_dir = str(log_search_section.get("log_base_dir", "")).strip()
        try:
            validated = validate_log_base_dir(raw_log_base_dir)
        except RuntimeError as exc:
            results.append(DiagnosticResult("error", str(exc)))
        else:
            results.append(DiagnosticResult("ok", f"log_base_dir = {validated}"))

    if db_type == DB_TYPE_SQLSERVER:
        installed_drivers = get_installed_odbc_drivers()
        if installed_drivers is None:
            results.append(
                DiagnosticResult(
                    "error",
                    "pyodbc is not installed. Run `uv sync` before using SQL Server.",
                )
            )
        else:
            driver_name = env_values.get("DB_DRIVER", "").strip()
            if driver_name and driver_name in installed_drivers:
                results.append(DiagnosticResult("ok", f"ODBC driver found: {driver_name}"))
            else:
                joined = ", ".join(installed_drivers) if installed_drivers else "none"
                results.append(
                    DiagnosticResult(
                        "error",
                        f"Configured ODBC driver was not found. Installed drivers: {joined}.",
                    )
                )

    if _can_run_database_probe(env_values):
        try:
            probe = check_database_connectivity(
                _build_database_settings(env_values),
                timeout_seconds=int(
                    env_values.get(
                        "DB_CONNECT_TIMEOUT_SECONDS",
                        str(DEFAULT_DB_CONNECT_TIMEOUT_SECONDS),
                    )
                ),
            )
        except RuntimeError as exc:
            results.append(DiagnosticResult("error", f"database connectivity failed: {exc}"))
        else:
            database_name = str(probe.get("database_name", ""))
            results.append(
                DiagnosticResult(
                    "ok",
                    f"database connectivity succeeded for {database_name or 'configured database'}",
                )
            )

    if OPTIONAL_PLUGIN_DINGTALK in plugin_names:
        webhook = env_values.get("DINGTALK_WEBHOOK_URL", "").strip()
        if webhook:
            results.append(DiagnosticResult("ok", "DINGTALK_WEBHOOK_URL is set"))
        else:
            results.append(DiagnosticResult("error", "DINGTALK_WEBHOOK_URL is missing from .env"))

    return results


def has_errors(results: list[DiagnosticResult]) -> bool:
    return any(result.level == "error" for result in results)


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


def _can_run_database_probe(env_values: dict[str, str]) -> bool:
    db_type = env_values.get("DB_TYPE", "").strip().lower()
    required = {"DB_TYPE", "DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME"}
    if db_type == DB_TYPE_SQLSERVER:
        required.update({"DB_DRIVER", "DB_TRUST_SERVER_CERTIFICATE"})
    if db_type not in {DB_TYPE_MYSQL, DB_TYPE_SQLSERVER}:
        return False
    return all(env_values.get(key, "").strip() for key in required)


def _build_database_settings(env_values: dict[str, str]):
    from .config import DatabaseSettings

    db_type = env_values["DB_TYPE"].strip().lower()
    trust_server_certificate = (
        parse_bool_text(env_values.get("DB_TRUST_SERVER_CERTIFICATE", "false"))
        if db_type == DB_TYPE_SQLSERVER
        else False
    )
    return DatabaseSettings(
        db_type=db_type,
        host=env_values["DB_HOST"].strip(),
        port=int(env_values["DB_PORT"].strip()),
        user=env_values["DB_USER"].strip(),
        password=env_values["DB_PASSWORD"].strip(),
        default_database=env_values["DB_NAME"].strip(),
        driver=env_values.get("DB_DRIVER", "").strip(),
        trust_server_certificate=trust_server_certificate,
        connect_timeout_seconds=int(
            env_values.get(
                "DB_CONNECT_TIMEOUT_SECONDS",
                str(DEFAULT_DB_CONNECT_TIMEOUT_SECONDS),
            )
        ),
    )


def _quote_env_value(value: str) -> str:
    if not value:
        return '""'
    if any(character.isspace() for character in value) or "#" in value:
        escaped = value.replace('"', '\\"')
        return f'"{escaped}"'
    return value


def default_port_for_db(db_type: str) -> int:
    return DEFAULT_DB_PORTS[db_type]


def default_driver_for_db(db_type: str) -> str:
    if db_type == DB_TYPE_SQLSERVER:
        return DEFAULT_DB_DRIVER
    return ""


def env_value(project_root: Path, key: str) -> str:
    return parse_env_file(env_file_path(project_root)).get(key, "")


def yaml_value(project_root: Path) -> dict[str, Any]:
    return load_existing_yaml(yaml_config_path(project_root))
