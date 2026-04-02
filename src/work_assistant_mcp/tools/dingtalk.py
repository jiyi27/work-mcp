from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from mcp.server.fastmcp import FastMCP

from ..config import get_settings


def register_dingtalk_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    def dingtalk_send_markdown(title: str, markdown: str) -> dict[str, Any]:
        """Send a markdown message to the configured DingTalk robot webhook."""
        title = title.strip()
        markdown = markdown.strip()
        if not title:
            raise RuntimeError("`title` must not be empty.")
        if not markdown:
            raise RuntimeError("`markdown` must not be empty.")

        settings = get_settings()
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": markdown,
            },
        }
        body = json.dumps(payload).encode("utf-8")
        request = Request(
            settings.dingtalk_webhook_url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urlopen(request, timeout=10) as response:
                response_body = response.read().decode("utf-8")
        except HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"DingTalk webhook request failed with HTTP {exc.code}: {error_body}"
            ) from exc
        except URLError as exc:
            raise RuntimeError(f"Failed to reach DingTalk webhook: {exc.reason}") from exc

        result = json.loads(response_body)
        if result.get("errcode") != 0:
            raise RuntimeError(
                "DingTalk webhook returned an error: "
                f"{result.get('errcode')} {result.get('errmsg', '')}"
            )

        return {
            "ok": True,
            "errcode": result.get("errcode"),
            "errmsg": result.get("errmsg"),
        }
