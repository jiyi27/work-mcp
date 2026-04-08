from __future__ import annotations

from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

import aiofiles

from ...config import LogSearchSettings
from ...hints import required_param_hint
from .strings import (
    HINT_FILE_NOT_FOUND,
    HINT_LIST_LOG_FILES_SUCCESS,
    HINT_NO_RESULTS,
    HINT_PATH_OUTSIDE_BASE,
    TOOL_LIST_LOG_FILES,
    TOOL_SEARCH_LOG,
)

# Maximum matching lines returned per search call; results beyond this are truncated.
_MAX_RESULTS = 5
# Number of lines captured before and after each matching line as context.
_CONTEXT_LINES = 1
# Maximum number of files shown per directory listing (directories are not capped).
_MAX_LISTED_FILES = 10


class LogSearchService:
    def __init__(self, settings: LogSearchSettings) -> None:
        self._settings = settings
        self._base = Path(settings.log_base_dir).resolve()

    def _safe_resolve(self, relative: str) -> Path | None:
        """Resolve a path relative to log_base_dir. Returns None if outside base."""
        target = (self._base / relative).resolve()
        try:
            target.relative_to(self._base)
        except ValueError:
            return None
        return target

    def list_files(self, path: str = "") -> dict[str, Any]:
        relative = path.strip()
        if relative in {".", "./"}:
            relative = ""
        if relative.endswith("/"):
            relative = relative.rstrip("/")

        target = self._safe_resolve(relative)
        if target is None:
            return {
                "success": False,
                "error_type": "path_outside_base",
                "hint": HINT_PATH_OUTSIDE_BASE,
            }
        if not target.exists():
            return {
                "success": False,
                "error_type": "path_not_found",
                "hint": (
                    f"Path '{relative or '.'}' does not exist. "
                    f"Call {TOOL_LIST_LOG_FILES} with an existing directory path."
                ),
            }
        if not target.is_dir():
            return {
                "success": False,
                "error_type": "not_a_directory",
                "hint": (
                    f"'{relative}' is a file, not a directory. "
                    f"Use {TOOL_SEARCH_LOG} to search files."
                ),
            }

        dirs: list[dict[str, Any]] = []
        files: list[tuple[float, dict[str, Any]]] = []
        for child in target.iterdir():
            rel = str(child.relative_to(self._base))
            if child.is_dir():
                dirs.append({"name": child.name, "type": "dir", "path": rel})
            else:
                stat = child.stat()
                files.append((
                    stat.st_mtime,
                    {
                        "name": child.name,
                        "type": "file",
                        "path": rel,
                        "size_kb": round(stat.st_size / 1024, 1),
                        "mtime": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    },
                ))

        dirs.sort(key=lambda entry: entry["name"])
        files.sort(key=lambda item: (-item[0], item[1]["name"]))
        entries = dirs + [entry for _, entry in files[:_MAX_LISTED_FILES]]

        return {
            "success": True,
            "path": relative,
            "entries": entries,
            "hint": HINT_LIST_LOG_FILES_SUCCESS,
        }

    async def search(self, file_path: str, query: str) -> dict[str, Any]:
        file_path = file_path.strip()
        query = query.strip()

        if not file_path:
            return {
                "success": False,
                "error_type": "invalid_input",
                "hint": required_param_hint("file_path"),
            }
        if not query:
            return {
                "success": False,
                "error_type": "invalid_input",
                "hint": required_param_hint("query"),
            }

        target = self._safe_resolve(file_path)
        if target is None:
            return {
                "success": False,
                "error_type": "path_outside_base",
                "hint": HINT_PATH_OUTSIDE_BASE,
            }
        if not target.exists():
            return {
                "success": False,
                "error_type": "file_not_found",
                "hint": f"File '{file_path}' does not exist. {HINT_FILE_NOT_FOUND}",
            }
        # P1: reject directories — agent may pass a dir path from list_log_files
        if target.is_dir():
            return {
                "success": False,
                "error_type": "not_a_file",
                "hint": (
                    f"'{file_path}' is a directory. "
                    f"Call {TOOL_LIST_LOG_FILES} to list its contents."
                ),
            }

        # Stream line by line — pre_buffer holds the sliding window of recent lines
        # for pre-context; post_collectors accumulates post-context into each result.
        pre_buffer: deque[str] = deque(maxlen=_CONTEXT_LINES)
        results: list[dict[str, Any]] = []
        # Each entry: (post_context_list, remaining_post_lines)
        post_collectors: list[tuple[list[str], int]] = []
        truncated = False
        line_no = 0

        async with aiofiles.open(target, encoding="utf-8", errors="replace") as f:
            async for raw_line in f:
                line_no += 1
                line = raw_line.rstrip("\n")

                # Feed line to any open post-context collectors
                still_open = []
                for post_ctx, remaining in post_collectors:
                    post_ctx.append(line)
                    if remaining > 1:
                        still_open.append((post_ctx, remaining - 1))
                post_collectors = still_open

                if query.lower() in line.lower():
                    if len(results) >= _MAX_RESULTS:
                        truncated = True
                        break
                    post_context: list[str] = []
                    results.append({
                        "line_no": line_no,
                        "match": line,
                        "pre_context": list(pre_buffer),
                        "post_context": post_context,
                    })
                    post_collectors.append((post_context, _CONTEXT_LINES))

                pre_buffer.append(line)

        if not results:
            return {
                "success": True,
                "results": [],
                "hint": HINT_NO_RESULTS,
            }

        response: dict[str, Any] = {"success": True, "results": results}
        if truncated:
            response["truncated"] = True
            response["hint"] = (
                f"Results capped at {_MAX_RESULTS}. "
                "Use a more specific query to narrow results."
            )
        return response
