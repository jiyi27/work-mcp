from __future__ import annotations

from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP

from ...config import Settings
from .service import LogSearchService
from .strings import (
    LIST_LOG_SERVICES_DESCRIPTION,
    SEARCH_LOGS_DESCRIPTION,
    TOOL_LIST_LOG_SERVICES,
    TOOL_SEARCH_LOGS,
)


def register_log_search_tools(mcp: FastMCP, settings: Settings) -> None:
    svc = LogSearchService(settings.log_search)  # type: ignore[arg-type]

    @mcp.tool(name=TOOL_SEARCH_LOGS, description=SEARCH_LOGS_DESCRIPTION)
    async def search_logs(
        service: Annotated[str, f"Service name to search. Call {TOOL_LIST_LOG_SERVICES} if you do not know the exact name."],
        query: Annotated[str, "Substring to match against raw log lines, e.g. a requestId value, traceId, or topic name."],
        limit: Annotated[int, "Maximum number of matching entries to return. Defaults to 10."] = 10,
    ) -> dict[str, Any]:
        return await svc.search(service, query, limit)

    @mcp.tool(name=TOOL_LIST_LOG_SERVICES, description=LIST_LOG_SERVICES_DESCRIPTION)
    async def list_log_services() -> dict[str, Any]:
        return await svc.list_services()
