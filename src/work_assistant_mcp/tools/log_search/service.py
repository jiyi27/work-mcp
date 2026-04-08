from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import aiofiles

from ...config import LogSearchSettings
from ...hints import required_param_hint
from .constants import CONTEXT_LINES, MAX_FILE_SIZE_BYTES, MAX_FILE_SIZE_MB, MAX_LISTED_ENTRIES, MAX_RESULTS
from .strings import (
    HINT_FILE_NOT_FOUND,
    HINT_LIST_LOG_FILES_SUCCESS,
    HINT_LIST_PATH_NOT_FOUND,
    HINT_NO_RESULTS,
    HINT_PATH_OUTSIDE_BASE,
    HINT_TRUNCATED,
    TOOL_LIST_LOG_FILES,
    TOOL_SEARCH_LOG,
    file_too_large_hint,
)


class LogSearchService:
    def __init__(self, settings: LogSearchSettings) -> None:
        self._settings = settings
        self._base = Path(settings.log_base_dir).resolve()

    def _safe_resolve(self, relative: str) -> Path | None:
        """Return an absolute path under the log base directory, or None if it escapes it."""
        # Join the user-provided relative path to the configured base directory,
        # then normalize it into a final absolute path.
        resolved_path = (self._base / relative).resolve()

        try:
            # Ensure the normalized path is still inside the base directory.
            # This blocks path traversal such as "../secret.log".
            resolved_path.relative_to(self._base)
        except ValueError:
            return None

        return resolved_path

    def list_files(self, path: str = "") -> dict[str, Any]:
        requested_path = path.strip()
        # Normalize equivalent directory inputs so "." and trailing "/" map to the same path.
        if requested_path in {".", "./"}:
            requested_path = ""
        if requested_path.endswith("/"):
            requested_path = requested_path.rstrip("/")

        # Resolve the requested path and reject anything that escapes the configured log base.
        absolute_path = self._safe_resolve(requested_path)
        if absolute_path is None:
            return {
                "success": False,
                "error_type": "path_outside_base",
                "hint": HINT_PATH_OUTSIDE_BASE,
            }
        if not absolute_path.exists():
            return {
                "success": False,
                "error_type": "path_not_found",
                "hint": f"Path '{requested_path or '.'}' does not exist. {HINT_LIST_PATH_NOT_FOUND}",
            }
        if not absolute_path.is_dir():
            return {
                "success": False,
                "error_type": "not_a_directory",
                "hint": (
                    f"'{requested_path}' is a file, not a directory. "
                    f"Use {TOOL_SEARCH_LOG} to search files."
                ),
            }

        # Each file item may represent either a file or a directory in the requested path.
        # Keep the modification time alongside each item so we can sort newest-first before truncating.
        file_items_with_mtime: list[tuple[float, dict[str, Any]]] = []
        for item_path in absolute_path.iterdir():
            item_relative_path = str(item_path.relative_to(self._base))
            stat = item_path.stat()
            file_item: dict[str, Any] = {
                "name": item_path.name,
                "path": item_relative_path,
                "mtime": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            }
            if item_path.is_dir():
                file_item["type"] = "dir"
            else:
                file_item["type"] = "file"
                file_item["size_kb"] = round(stat.st_size / 1024, 1)
            file_items_with_mtime.append((stat.st_mtime, file_item))

        file_items_with_mtime.sort(key=lambda file_item_record: (-file_item_record[0], file_item_record[1]["name"]))
        file_items = [file_item for _, file_item in file_items_with_mtime[:MAX_LISTED_ENTRIES]]

        return {
            "success": True,
            "path": requested_path,
            "entries": file_items,
            "hint": HINT_LIST_LOG_FILES_SUCCESS,
        }

    async def search(self, file_path: str, query: str) -> dict[str, Any]:
        requested_file_path = file_path.strip()
        normalized_query = query.strip()

        if not requested_file_path:
            return {
                "success": False,
                "error_type": "invalid_input",
                "hint": required_param_hint("file_path"),
            }
        if not normalized_query:
            return {
                "success": False,
                "error_type": "invalid_input",
                "hint": required_param_hint("query"),
            }

        # Resolve the requested file path and reject anything outside the log base directory.
        absolute_path = self._safe_resolve(requested_file_path)
        if absolute_path is None:
            return {
                "success": False,
                "error_type": "path_outside_base",
                "hint": HINT_PATH_OUTSIDE_BASE,
            }
        if not absolute_path.exists():
            return {
                "success": False,
                "error_type": "file_not_found",
                "hint": f"File '{requested_file_path}' does not exist. {HINT_FILE_NOT_FOUND}",
            }
        # Reject directories here because list_log_files may return directory paths.
        if absolute_path.is_dir():
            return {
                "success": False,
                "error_type": "not_a_file",
                "hint": (
                    f"'{requested_file_path}' is a directory. "
                    f"Call {TOOL_LIST_LOG_FILES} to list its contents."
                ),
            }
        file_size = absolute_path.stat().st_size
        if file_size > MAX_FILE_SIZE_BYTES:
            return {
                "success": False,
                "error_type": "file_too_large",
                "hint": file_too_large_hint(MAX_FILE_SIZE_MB),
            }

        async with aiofiles.open(absolute_path, encoding="utf-8", errors="replace") as file_handle:
            file_lines = (await file_handle.read()).splitlines()

        lowered_query = normalized_query.lower()
        matched_results: list[dict[str, Any]] = []
        truncated = False
        # Scan from the end so we capture the newest matches first, then sort by line number before returning.
        for line_index in range(len(file_lines) - 1, -1, -1):
            matched_line = file_lines[line_index]
            if lowered_query not in matched_line.lower():
                continue
            if len(matched_results) >= MAX_RESULTS:
                truncated = True
                break

            matched_results.append({
                "line_no": line_index + 1,
                "match": matched_line,
                "pre_context": file_lines[max(0, line_index - CONTEXT_LINES):line_index],
                "post_context": file_lines[line_index + 1:line_index + 1 + CONTEXT_LINES],
            })

        if not matched_results:
            return {
                "success": True,
                "results": [],
                "hint": HINT_NO_RESULTS,
            }

        matched_results.sort(key=lambda item: item["line_no"])
        response: dict[str, Any] = {"success": True, "results": matched_results}
        if truncated:
            response["truncated"] = True
            response["hint"] = HINT_TRUNCATED
        return response
