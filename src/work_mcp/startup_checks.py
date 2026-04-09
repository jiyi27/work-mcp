from __future__ import annotations

from collections.abc import Callable

from .config import Settings
from .tools.database.factory import check_database_connectivity
from .tools.jira.client import check_jira_connectivity


StartupCheck = Callable[[Settings, int], object]


def _check_database(settings: Settings, timeout_seconds: int) -> object:
    if settings.database is None:
        raise RuntimeError("missing database settings in environment or .env")
    return check_database_connectivity(
        settings.database,
        timeout_seconds=timeout_seconds,
    )


def _check_jira(settings: Settings, timeout_seconds: int) -> object:
    return check_jira_connectivity(
        settings,
        timeout_seconds=timeout_seconds,
    )


STARTUP_CHECK_REGISTRY: dict[str, StartupCheck] = {
    "database": _check_database,
    "jira": _check_jira,
}


def run_startup_checks(settings: Settings) -> None:
    if not settings.startup.healthcheck.enabled:
        return

    timeout_seconds = settings.startup.healthcheck.timeout_seconds
    errors: list[str] = []
    for plugin_name in settings.enabled_plugins:
        check_fn = STARTUP_CHECK_REGISTRY.get(plugin_name)
        if check_fn is None:
            continue
        try:
            check_fn(settings, timeout_seconds)
        except RuntimeError as exc:
            errors.append(f"{plugin_name}: {exc}")

    if errors:
        lines = "\n".join(f"- {item}" for item in errors)
        raise RuntimeError(f"Startup dependency checks failed:\n{lines}")
