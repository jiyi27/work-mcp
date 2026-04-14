from __future__ import annotations

from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP

from ...config import Settings
from .service import RemoteFsService
from .strings import (
    GET_ALLOWED_ROOTS_DESCRIPTION,
    LIST_TREE_DESCRIPTION,
    READ_FILE_DESCRIPTION,
    SEARCH_FILE_REVERSE_DESCRIPTION,
    SEARCH_FILES_DESCRIPTION,
    TOOL_GET_ALLOWED_ROOTS,
    TOOL_LIST_TREE,
    TOOL_READ_FILE,
    TOOL_SEARCH_FILE_REVERSE,
    TOOL_SEARCH_FILES,
)


def register_remote_fs_tools(mcp: FastMCP, settings: Settings) -> None:
    svc = RemoteFsService(settings.remote_fs)  # type: ignore[arg-type]

    @mcp.tool(name=TOOL_GET_ALLOWED_ROOTS, description=GET_ALLOWED_ROOTS_DESCRIPTION)
    def get_allowed_roots() -> dict[str, Any]:
        return svc.get_allowed_roots()

    @mcp.tool(name=TOOL_LIST_TREE, description=LIST_TREE_DESCRIPTION)
    def list_tree(
        path: str,
        depth: Annotated[int, "Number of directory levels to expand."] = 1,
    ) -> dict[str, Any]:
        return svc.list_tree(path, depth)

    @mcp.tool(name=TOOL_SEARCH_FILES, description=SEARCH_FILES_DESCRIPTION)
    async def search_files(
        query: Annotated[
            str,
            "Text to find in file contents. Omit to search by file name only using path_glob.",
        ] = "",
        root: Annotated[
            str,
            "Root name or path to limit the search scope. Omit to search all roots.",
        ] = "",
        path_glob: Annotated[
            str, "File name filter such as **/*.py or **/*.log."
        ] = "",
        regex: Annotated[bool, "Treat query as a regular expression."] = False,
        max_matches: int = 50,
    ) -> dict[str, Any]:
        return await svc.search_files(query, root, path_glob, regex, max_matches)

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
        name=TOOL_SEARCH_FILE_REVERSE, description=SEARCH_FILE_REVERSE_DESCRIPTION
    )
    async def search_file_reverse(
        path: str,
        query: str,
        max_matches: Annotated[int, "Maximum number of matches to return."] = 20,
        before: Annotated[int, "Number of context lines before each match."] = 3,
        after: Annotated[int, "Number of context lines after each match."] = 3,
        regex: Annotated[bool, "Treat query as a regular expression."] = False,
    ) -> dict[str, Any]:
        return await svc.search_file_reverse(
            path, query, max_matches, before, after, regex,
        )
