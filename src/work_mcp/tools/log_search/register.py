from __future__ import annotations

from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP

from ...config import Settings
from .service import LogSearchService
from .strings import (
    LIST_LOG_FILES_DESCRIPTION,
    SEARCH_LOG_DESCRIPTION,
    TOOL_LIST_LOG_FILES,
    TOOL_SEARCH_LOG,
)


def register_log_search_tools(mcp: FastMCP, settings: Settings) -> None:
    svc = LogSearchService(settings.log_search)  # type: ignore[arg-type]

    @mcp.tool(name=TOOL_LIST_LOG_FILES, description=LIST_LOG_FILES_DESCRIPTION)
    def list_log_files(
        path: Annotated[str | None, "Path relative to the log base directory. Omit or pass empty string to list the log root."] = None,
    ) -> dict[str, Any]:
        return svc.list_files(path or "")

    @mcp.tool(name=TOOL_SEARCH_LOG, description=SEARCH_LOG_DESCRIPTION)
    async def search_log(
        file_path: Annotated[str, f"Path to the log file relative to the log base directory. Obtained from the path field in {TOOL_LIST_LOG_FILES} results."],
        query: Annotated[str, "Substring to match against log lines. Case-insensitive."],
    ) -> dict[str, Any]:
        return await svc.search(file_path, query)
