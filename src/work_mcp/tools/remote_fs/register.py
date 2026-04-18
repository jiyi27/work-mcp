from __future__ import annotations

from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP

from ...config import Settings
from .constants import MAX_SEARCH_MATCHES
from .service import RemoteFsService
from .strings import (
    DESCRIBE_ENVIRONMENT_DESCRIPTION,
    GREP_DESCRIPTION,
    LIST_TREE_DESCRIPTION,
    READ_FILE_DESCRIPTION,
    SEARCH_FILE_DESCRIPTION,
    TOOL_DESCRIBE_ENVIRONMENT,
    TOOL_GREP,
    TOOL_LIST_TREE,
    TOOL_READ_FILE,
    TOOL_SEARCH_FILE,
)


def register_remote_fs_tools(mcp: FastMCP, settings: Settings) -> None:
    svc = RemoteFsService(settings.remote_fs)  # type: ignore[arg-type]

    @mcp.tool(
        name=TOOL_DESCRIBE_ENVIRONMENT,
        description=DESCRIBE_ENVIRONMENT_DESCRIPTION,
    )
    def get_allowed_roots() -> dict[str, Any]:
        return svc.get_allowed_roots()

    @mcp.tool(name=TOOL_LIST_TREE, description=LIST_TREE_DESCRIPTION)
    def list_tree(
        path: str,
        offset: Annotated[int, "Zero-based offset for continuing a truncated listing."] = 0,
    ) -> dict[str, Any]:
        return svc.list_tree(path, offset)

    @mcp.tool(name=TOOL_GREP, description=GREP_DESCRIPTION)
    async def search_files(
        query: Annotated[
            str,
            "Text to find in file contents. Omit to search by file name only using path_glob.",
        ] = "",
        directory: Annotated[
            str,
            "Directory name or path to limit the search scope. Omit to search all directories.",
        ] = "",
        path_glob: Annotated[
            str, "File name filter such as **/*.py or **/*.log."
        ] = "",
        regex: Annotated[bool, "Treat query as a regular expression."] = False,
    ) -> dict[str, Any]:
        return await svc.search_files(query, directory, path_glob, regex, MAX_SEARCH_MATCHES)

    @mcp.tool(name=TOOL_READ_FILE, description=READ_FILE_DESCRIPTION)
    async def read_file(
        path: str,
        start_line: Annotated[int, "1-based line number to start from."] = 1,
        max_lines: Annotated[int, "Maximum number of lines to return."] = 200,
        tail: Annotated[
            int, "Read the last N lines. Overrides start_line when greater than 0."
        ] = 0,
    ) -> dict[str, Any]:
        return await svc.read_file(path, start_line, max_lines, tail)

    @mcp.tool(
        name=TOOL_SEARCH_FILE, description=SEARCH_FILE_DESCRIPTION
    )
    async def search_file(
        path: str,
        query: str,
        regex: Annotated[bool, "Treat query as a regular expression."] = False,
        from_end: Annotated[
            bool, "Scan from the end of the file when true, or from the beginning when false."
        ] = True,
    ) -> dict[str, Any]:
        return await svc.search_file(path, query, regex, from_end)
