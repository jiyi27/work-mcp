from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import (
    PROJECT_ROOT,
    DB_TYPE_SQLSERVER,
    Settings,
    get_settings,
)
from .tools.database.factory import check_database_connectivity
from .tools.jira.client import check_jira_connectivity

GENERIC_CONNECTIVITY_INFO = "please check the current module config or network access"


@dataclass(frozen=True)
class CheckLine:
    level: str
    message: str


@dataclass(frozen=True)
class ModuleCheckResult:
    module: str
    lines: tuple[CheckLine, ...]

    def has_errors(self) -> bool:
        return any(line.level == "error" for line in self.lines)


def run_checks(project_root: Path = PROJECT_ROOT) -> list[ModuleCheckResult]:
    try:
        settings = get_settings(project_root / "config.yaml")
    except RuntimeError as exc:
        return _group_config_error(str(exc))

    results: list[ModuleCheckResult] = []
    for plugin_name in settings.enabled_plugins:
        results.append(_run_plugin_check(settings, plugin_name))
    return results


def has_check_errors(results: list[ModuleCheckResult]) -> bool:
    return any(result.has_errors() for result in results)


def _run_plugin_check(settings: Settings, plugin_name: str) -> ModuleCheckResult:
    if plugin_name == "jira":
        return _check_jira(settings)
    if plugin_name == "database":
        return _check_database(settings)
    if plugin_name == "log_search":
        return _check_log_search(settings)
    if plugin_name == "dingtalk":
        return _check_dingtalk(settings)
    if plugin_name == "remote_fs":
        return _check_remote_fs(settings)
    return ModuleCheckResult(
        module=plugin_name,
        lines=(CheckLine("error", f"unsupported plugin: {plugin_name}"),),
    )


def _check_jira(settings: Settings) -> ModuleCheckResult:
    config_lines = _config_block(
        f"base_url={settings.jira_base_url}",
        f"project_key={settings.jira_project_key}",
    )
    try:
        check_jira_connectivity(settings, timeout_seconds=5)
    except RuntimeError as exc:
        return ModuleCheckResult(
            module="jira",
            lines=config_lines + (
                CheckLine("error", str(exc)),
                CheckLine("info", GENERIC_CONNECTIVITY_INFO),
            ),
        )
    return ModuleCheckResult(
        module="jira",
        lines=(
            CheckLine("ok", "config is valid"),
            CheckLine("ok", "connectivity passed"),
        ),
    )


def _check_database(settings: Settings) -> ModuleCheckResult:
    if settings.database is None:
        return ModuleCheckResult(
            module="database",
            lines=(CheckLine("error", "missing config: database section"),),
        )
    database = settings.database
    summary_parts = [
        f"type={database.db_type}",
        f"host={database.host}",
        f"port={database.port}",
        f"user={database.user}",
    ]
    if database.db_type == DB_TYPE_SQLSERVER:
        summary_parts.append(f"driver={database.driver}")
    config_lines = _config_block(*summary_parts)
    try:
        check_database_connectivity(
            database,
            timeout_seconds=database.connect_timeout_seconds,
        )
    except RuntimeError as exc:
        return ModuleCheckResult(
            module="database",
            lines=config_lines + (
                CheckLine("error", str(exc)),
                CheckLine("info", GENERIC_CONNECTIVITY_INFO),
            ),
        )
    return ModuleCheckResult(
        module="database",
        lines=(
            CheckLine("ok", "config is valid"),
            CheckLine("ok", "connectivity passed"),
        ),
    )


def _check_log_search(settings: Settings) -> ModuleCheckResult:
    assert settings.log_search is not None
    return ModuleCheckResult(
        module="log_search",
        lines=(
            CheckLine("ok", "config is valid"),
            CheckLine("info", f"log_base_dir={settings.log_search.log_base_dir}"),
        ),
    )


def _check_dingtalk(settings: Settings) -> ModuleCheckResult:
    return ModuleCheckResult(
        module="dingtalk",
        lines=(
            CheckLine("ok", "config is valid"),
            CheckLine("info", f"webhook_url={settings.dingtalk_webhook_url}"),
        ),
    )


def _check_remote_fs(settings: Settings) -> ModuleCheckResult:
    assert settings.remote_fs is not None
    root_names = ", ".join(root.name for root in settings.remote_fs.roots)
    return ModuleCheckResult(
        module="remote_fs",
        lines=(
            CheckLine("ok", "config is valid"),
            CheckLine("info", f"roots={root_names}"),
        ),
    )


def _group_config_error(message: str) -> list[ModuleCheckResult]:
    prefix = "Invalid configuration for enabled plugins:\n"
    if not message.startswith(prefix):
        return [ModuleCheckResult(module="config", lines=(CheckLine("error", message),))]
    grouped: dict[str, list[CheckLine]] = {}
    for raw_line in message[len(prefix):].splitlines():
        line = raw_line.strip()
        if not line.startswith("- "):
            continue
        item = line[2:]
        module, _, detail = item.partition(": ")
        if not detail:
            module = "config"
            detail = item
        grouped.setdefault(module, []).append(CheckLine("error", detail))
    return [
        ModuleCheckResult(module=module, lines=tuple(lines))
        for module, lines in grouped.items()
    ]


def _config_block(*items: str) -> tuple[CheckLine, ...]:
    lines = [CheckLine("plain", "current config:")]
    lines.extend(CheckLine("plain", f"- {item}") for item in items)
    return tuple(lines)


def print_check_report(results: list[ModuleCheckResult]) -> None:
    if not results:
        print("all checks passed")
        return
    for index, result in enumerate(results):
        if index:
            print()
        print(f"[module] {result.module}")
        for line in result.lines:
            if line.level == "plain":
                print(line.message)
                continue
            print(f"[{line.level}] {line.message}")
    if not has_check_errors(results):
        print()
        print("all checks passed")
