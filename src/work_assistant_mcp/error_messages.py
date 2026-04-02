from __future__ import annotations


def format_http_service_error(
    *,
    service_name: str,
    operation: str,
    status_code: int | None,
    auth_env_names: tuple[str, ...] = (),
) -> str:
    if status_code == 401:
        message = f"{service_name} authentication failed while {operation} (HTTP 401)."
        if auth_env_names:
            joined = _join_human_list(auth_env_names)
            return f"{message} Check {joined}."
        return message
    if status_code == 403:
        return f"{service_name} denied permission while {operation} (HTTP 403)."
    if status_code is not None:
        return f"{service_name} API returned HTTP {status_code} while {operation}."
    return f"{service_name} API encountered an unknown error while {operation}."


def _join_human_list(items: tuple[str, ...]) -> str:
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"
