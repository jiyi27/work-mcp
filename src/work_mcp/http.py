from __future__ import annotations

import html
import json
import re
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
            _format_http_error_message(
                service_name=service_name,
                status_code=exc.code,
                body=error_body,
                content_type=exc.headers.get("Content-Type"),
            ),
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


def _format_http_error_message(
    *,
    service_name: str,
    status_code: int,
    body: str,
    content_type: str | None,
) -> str:
    summary = _extract_error_summary(body=body, content_type=content_type)
    if not summary:
        return f"{service_name} request failed with HTTP {status_code}: unknown upstream error"
    return f"{service_name} request failed with HTTP {status_code}: {summary}"


def _extract_error_summary(*, body: str, content_type: str | None) -> str | None:
    normalized_content_type = (content_type or "").lower()

    if "json" in normalized_content_type:
        summary = _extract_json_error_summary(body)
        if summary:
            return summary

    if "<html" in body.lower() or "text/html" in normalized_content_type:
        return _extract_html_error_summary(body)

    summary = _normalize_error_text(body)
    if not summary:
        return None
    return _truncate(summary, 240)


def _extract_json_error_summary(body: str) -> str | None:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return None

    if isinstance(payload, dict):
        error_messages = payload.get("errorMessages")
        if isinstance(error_messages, list):
            texts = [_normalize_error_text(str(item)) for item in error_messages]
            summary = "; ".join(text for text in texts if text)
            if summary:
                return _truncate(summary, 240)

        errors = payload.get("errors")
        if isinstance(errors, dict):
            parts = []
            for key, value in errors.items():
                text = _normalize_error_text(str(value))
                if text:
                    parts.append(f"{key}: {text}")
            summary = "; ".join(parts)
            if summary:
                return _truncate(summary, 240)

        for key in ("message", "error", "detail"):
            value = payload.get(key)
            if value is None:
                continue
            summary = _normalize_error_text(str(value))
            if summary:
                return _truncate(summary, 240)

    if isinstance(payload, list):
        texts = [_normalize_error_text(str(item)) for item in payload]
        summary = "; ".join(text for text in texts if text)
        if summary:
            return _truncate(summary, 240)

    return None


def _extract_html_error_summary(body: str) -> str | None:
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", body, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    summary = _normalize_error_text(text)
    if not summary:
        return "received an HTML error page"

    lowered = summary.lower()
    if "basic authentication failure" in lowered or "authenticated_failed" in lowered:
        return "authentication failed"
    if "unauthorized" in lowered:
        return "unauthorized"
    if "forbidden" in lowered:
        return "forbidden"

    return _truncate(summary, 240)


def _normalize_error_text(value: str) -> str:
    normalized = html.unescape(value)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."
