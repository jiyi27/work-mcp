from __future__ import annotations

from email.message import Message
from unittest.mock import patch
from urllib.error import HTTPError

from work_mcp.http import HttpRequestError, request_json


def _http_error(*, code: int, body: str, content_type: str) -> HTTPError:
    headers = Message()
    headers["Content-Type"] = content_type
    return HTTPError(
        url="https://jira.example.invalid/rest/api/2/search",
        code=code,
        msg="Unauthorized",
        hdrs=headers,
        fp=None,
    )


def test_request_json_summarizes_html_http_error_body() -> None:
    error = _http_error(
        code=401,
        content_type="text/html; charset=utf-8",
        body=(
            "<html><body><h1>Unauthorized (401)</h1>"
            "<p>Basic Authentication Failure - Reason : AUTHENTICATED_FAILED</p>"
            "</body></html>"
        ),
    )

    with patch("work_mcp.http.urlopen", side_effect=error), patch.object(
        error,
        "read",
        return_value=(
            b"<html><body><h1>Unauthorized (401)</h1>"
            b"<p>Basic Authentication Failure - Reason : AUTHENTICATED_FAILED</p>"
            b"</body></html>"
        ),
    ):
        try:
            request_json(
                method="GET",
                url="https://jira.example.invalid/rest/api/2/search",
                timeout=30,
                service_name="Jira",
            )
        except HttpRequestError as exc:
            assert exc.status_code == 401
            assert exc.message == "Jira request failed with HTTP 401: authentication failed"
        else:
            raise AssertionError("Expected HttpRequestError")


def test_request_json_returns_unknown_upstream_error_when_body_is_unparseable() -> None:
    error = _http_error(
        code=502,
        content_type="application/octet-stream",
        body="",
    )

    with patch("work_mcp.http.urlopen", side_effect=error), patch.object(
        error,
        "read",
        return_value=b"",
    ):
        try:
            request_json(
                method="GET",
                url="https://jira.example.invalid/rest/api/2/search",
                timeout=30,
                service_name="Jira",
            )
        except HttpRequestError as exc:
            assert exc.status_code == 502
            assert exc.message == "Jira request failed with HTTP 502: unknown upstream error"
        else:
            raise AssertionError("Expected HttpRequestError")
