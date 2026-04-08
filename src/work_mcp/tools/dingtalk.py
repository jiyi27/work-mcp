from __future__ import annotations

import base64
import hashlib
import hmac
import time
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from mcp.server.fastmcp import FastMCP

from ..config import Settings
from ..error_messages import format_http_service_error
from ..hints import DINGTALK_INTERNAL_ERROR_HINT, required_param_hint
from ..http import HttpRequestError, request_json
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


def register_dingtalk_tools(mcp: FastMCP, settings: Settings) -> None:
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
                "hint": required_param_hint("title"),
            }
        if not markdown:
            error("dingtalk.validation_failed", {"field": "markdown"})
            return {
                "success": False,
                "error_type": "invalid_input",
                "hint": required_param_hint("markdown"),
            }

        configure_logger(log_dir=settings.log_dir, level=settings.log_level)
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": markdown,
            },
        }
        webhook_url = _build_signed_webhook_url(
            settings.dingtalk_webhook_url,
            settings.dingtalk_secret,
        )

        try:
            result = request_json(
                method="POST",
                url=webhook_url,
                headers={"Content-Type": "application/json"},
                payload=payload,
                timeout=10,
                service_name="DingTalk",
            )
        except HttpRequestError as exc:
            topic = "dingtalk.request_failed" if exc.status_code is not None else "dingtalk.network_failed"
            error(topic, {}, exc=exc)
            return {
                "success": False,
                "error_type": "internal_error",
                "message": format_http_service_error(
                    service_name="DingTalk",
                    operation="sending the webhook message",
                    status_code=exc.status_code,
                    error_message=exc.message,
                ),
                "hint": DINGTALK_INTERNAL_ERROR_HINT,
            }

        if not isinstance(result, dict):
            error("dingtalk.invalid_response", {"response_type": type(result).__name__})
            return {
                "success": False,
                "error_type": "internal_error",
                "message": "DingTalk API encountered an unknown error while sending the webhook message.",
                "hint": DINGTALK_INTERNAL_ERROR_HINT,
            }

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
                "hint": DINGTALK_INTERNAL_ERROR_HINT,
            }

        info("dingtalk.sent", {"title": title})
        return {"success": True}
