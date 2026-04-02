from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class HttpRequestError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def request_json(
    *,
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    query: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
    timeout: int,
    service_name: str,
) -> Any:
    raw = request_bytes(
        method=method,
        url=url,
        headers=_build_json_headers(headers, payload),
        query=query,
        payload=payload,
        timeout=timeout,
        service_name=service_name,
    )
    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise HttpRequestError(f"{service_name} returned invalid JSON.") from exc


def request_bytes(
    *,
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    query: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
    timeout: int,
    service_name: str,
) -> bytes:
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")

    request = Request(
        _build_url(url, query),
        data=body,
        headers=headers or {},
        method=method,
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.read()
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise HttpRequestError(
            f"{service_name} request failed with HTTP {exc.code}: {error_body}",
            status_code=exc.code,
        ) from exc
    except URLError as exc:
        raise HttpRequestError(f"Failed to reach {service_name}: {exc.reason}") from exc


def _build_url(url: str, query: dict[str, Any] | None) -> str:
    if not query:
        return url
    return f"{url}?{urlencode(query)}"


def _build_json_headers(
    headers: dict[str, str] | None,
    payload: dict[str, Any] | None,
) -> dict[str, str]:
    merged = dict(headers or {})
    if payload is not None:
        merged["Content-Type"] = "application/json"
    return merged
