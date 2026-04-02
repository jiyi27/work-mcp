from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from mcp.server.fastmcp import FastMCP

from ..config import get_settings
from ..logger import configure as configure_logger
from ..logger import error, info


def _build_signed_webhook_url(webhook_url: str, secret: str | None) -> str:
    if not secret:
        return webhook_url

    timestamp = str(round(time.time() * 1000))
    string_to_sign = f"{timestamp}\n{secret}".encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), string_to_sign, hashlib.sha256).digest()
    sign = base64.b64encode(digest).decode("utf-8")

    parts = urlsplit(webhook_url)
    query_items = parse_qsl(parts.query, keep_blank_values=True)
    query_items = [
        (key, value)
        for key, value in query_items
        if key not in {"timestamp", "sign"}
    ]
    query_items.extend([("timestamp", timestamp), ("sign", sign)])
    signed_query = urlencode(query_items)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, signed_query, parts.fragment))


def register_dingtalk_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    def dingtalk_send_markdown(title: str, markdown: str) -> dict[str, Any]:
        """Send a formatted notification to the DingTalk group.

        Use this to report task progress, completion, errors, or any update
        that the user or team should be aware of.
        """
        title = title.strip()
        markdown = markdown.strip()
        if not title:
            error("dingtalk.validation_failed", {"field": "title"})
            return {
                "success": False,
                "error_type": "invalid_input",
                "hint": "`title` must not be empty. Fix the parameter and retry.",
            }
        if not markdown:
            error("dingtalk.validation_failed", {"field": "markdown"})
            return {
                "success": False,
                "error_type": "invalid_input",
                "hint": "`markdown` must not be empty. Fix the parameter and retry.",
            }

        settings = get_settings()
        configure_logger(log_dir=settings.log_dir, level=settings.log_level)
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": markdown,
            },
        }
        body = json.dumps(payload).encode("utf-8")
        webhook_url = _build_signed_webhook_url(
            settings.dingtalk_webhook_url,
            settings.dingtalk_secret,
        )
        request = Request(
            webhook_url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urlopen(request, timeout=10) as response:
                response_body = response.read().decode("utf-8")
        except HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            error(
                "dingtalk.request_failed",
                {"status_code": exc.code, "response_body": error_body},
                exc=exc,
            )
            return {
                "success": False,
                "error_type": "internal_error",
                "message": f"DingTalk webhook request failed with HTTP {exc.code}: {error_body}",
                "hint": "An internal error occurred. Stop and tell the user in your reply: the notification could not be sent.",
            }
        except URLError as exc:
            error("dingtalk.network_failed", {"reason": str(exc.reason)}, exc=exc)
            return {
                "success": False,
                "error_type": "internal_error",
                "message": f"Failed to reach DingTalk webhook: {exc.reason}",
                "hint": "An internal error occurred. Stop and tell the user in your reply: the notification could not be sent.",
            }

        result = json.loads(response_body)
        if result.get("errcode") != 0:
            error(
                "dingtalk.upstream_error",
                {
                    "errcode": result.get("errcode"),
                    "errmsg": result.get("errmsg", ""),
                },
            )
            return {
                "success": False,
                "error_type": "internal_error",
                "message": f"DingTalk returned error {result.get('errcode')}: {result.get('errmsg', '')}",
                "hint": "An internal error occurred. Stop and tell the user in your reply: the notification could not be sent.",
            }

        info("dingtalk.sent", {"title": title})
        return {"success": True}
