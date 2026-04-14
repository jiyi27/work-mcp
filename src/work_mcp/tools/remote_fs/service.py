from __future__ import annotations


import fnmatch
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiofiles

from ...config import RemoteFsSettings
from .constants import (
    BINARY_CHECK_BYTES,
    DEFAULT_CONTEXT_LINES,
    DEFAULT_READ_LINES,
    MAX_CONTEXT_LINES,
    MAX_FILE_SIZE_BYTES,
    MAX_READ_LINES,
    MAX_REVERSE_MATCHES,
    MAX_SEARCH_MATCHES,
    MAX_TREE_ENTRIES,
)
from .path_guard import PathNotAllowedError, resolve_allowed_path
from .strings import (
    HINT_BINARY_FILE_NOT_SUPPORTED,
    HINT_FILE_TOO_LARGE,
    HINT_LIST_TREE_COMPLETE,
    HINT_LIST_TREE_PATH_NOT_FOUND,
    HINT_LIST_TREE_TRUNCATED,
    HINT_NOT_A_DIRECTORY,
    HINT_NOT_A_FILE,
    HINT_NO_ROOTS,
    HINT_PATH_NOT_ALLOWED,
    HINT_PATH_NOT_FOUND,
    HINT_READ_FILE_COMPLETE,
    HINT_READ_FILE_EMPTY,
    HINT_READ_FILE_INVALID_ARGUMENT,
    HINT_READ_FILE_LINE_OUT_OF_RANGE,
    HINT_READ_FILE_TRUNCATED,
    HINT_REVERSE_SEARCH_COMPLETE,
    HINT_REVERSE_SEARCH_INVALID_ARGUMENT,
    HINT_REVERSE_SEARCH_INVALID_REGEX,
    HINT_REVERSE_SEARCH_NO_MATCHES,
    HINT_REVERSE_SEARCH_TRUNCATED,
    HINT_ROOTS_FOUND,
    HINT_SEARCH_COMPLETE,
    HINT_SEARCH_INVALID_ARGUMENT,
    HINT_SEARCH_INVALID_REGEX,
    HINT_SEARCH_NO_MATCHES,
    HINT_SEARCH_TRUNCATED,
)


def _is_binary(path: Path) -> bool:
    """Return True if the file appears to be binary by checking for null bytes."""
    try:
        with path.open("rb") as f:
            chunk = f.read(BINARY_CHECK_BYTES)
        return b"\x00" in chunk
    except OSError:
        return False


def _format_mtime(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _matches_path_glob(relative_path: Path, path_glob: str) -> bool:
    relative_str = relative_path.as_posix()
    if fnmatch.fnmatch(relative_str, path_glob):
        return True
    if path_glob.startswith("**/"):
        return fnmatch.fnmatch(relative_str, path_glob.removeprefix("**/"))
    return False


class RemoteFsService:
    def __init__(self, settings: RemoteFsSettings) -> None:
        self._settings = settings
        self._root_paths = tuple(r.path for r in settings.roots)

    def _resolve(self, raw_path: str) -> Path:
        """Resolve a path through the shared access guard. Raises PathNotAllowedError."""
        return resolve_allowed_path(raw_path, self._root_paths)

    def _resolve_directory(self, raw_path: str) -> tuple[Path | None, dict[str, Any] | None]:
        try:
            resolved = self._resolve(raw_path)
        except PathNotAllowedError:
            return None, {
                "success": False,
                "error_type": "path_not_allowed",
                "hint": HINT_PATH_NOT_ALLOWED,
            }

        if not resolved.exists():
            return None, {
                "success": False,
                "error_type": "path_not_found",
                "hint": HINT_LIST_TREE_PATH_NOT_FOUND,
            }
        if not resolved.is_dir():
            return None, {
                "success": False,
                "error_type": "not_a_directory",
                "hint": HINT_NOT_A_DIRECTORY,
            }
        return resolved, None

    def _resolve_text_file(self, raw_path: str) -> tuple[Path | None, dict[str, Any] | None]:
        try:
            resolved = self._resolve(raw_path)
        except PathNotAllowedError:
            return None, {
                "success": False,
                "error_type": "path_not_allowed",
                "hint": HINT_PATH_NOT_ALLOWED,
            }

        if not resolved.exists():
            return None, {
                "success": False,
                "error_type": "path_not_found",
                "hint": HINT_PATH_NOT_FOUND,
            }
        if resolved.is_dir():
            return None, {
                "success": False,
                "error_type": "not_a_file",
                "hint": HINT_NOT_A_FILE,
            }
        if resolved.stat().st_size > MAX_FILE_SIZE_BYTES:
            return None, {
                "success": False,
                "error_type": "file_too_large",
                "hint": HINT_FILE_TOO_LARGE,
            }
        if _is_binary(resolved):
            return None, {
                "success": False,
                "error_type": "binary_file_not_supported",
                "hint": HINT_BINARY_FILE_NOT_SUPPORTED,
            }
        return resolved, None

    # ------------------------------------------------------------------
    # get_allowed_roots
    # ------------------------------------------------------------------

    def get_allowed_roots(self) -> dict[str, Any]:
        roots_data = [
            {
                "name": r.name,
                "path": str(r.path),
                "kind": r.kind,
                "description": r.description,
            }
            for r in self._settings.roots
        ]
        if not roots_data:
            return {"success": True, "roots": [], "hint": HINT_NO_ROOTS}
        return {"success": True, "roots": roots_data, "hint": HINT_ROOTS_FOUND}

    # ------------------------------------------------------------------
    # list_tree
    # ------------------------------------------------------------------

    def list_tree(self, path: str, depth: int) -> dict[str, Any]:
        depth = max(1, depth)
        resolved, error = self._resolve_directory(path)
        if error is not None:
            return error

        entries: list[dict[str, Any]] = []
        truncated = False
        self._walk_tree(resolved, depth, 1, entries)
        if len(entries) > MAX_TREE_ENTRIES:
            entries = entries[:MAX_TREE_ENTRIES]
            truncated = True

        return {
            "success": True,
            "path": str(resolved),
            "entries": entries,
            "truncated": truncated,
            "hint": HINT_LIST_TREE_TRUNCATED if truncated else HINT_LIST_TREE_COMPLETE,
        }

    def _walk_tree(
        self,
        current: Path,
        max_depth: int,
        current_depth: int,
        entries: list[dict[str, Any]],
    ) -> None:
        if current_depth > max_depth:
            return
        # Early exit when we have collected enough entries.
        if len(entries) > MAX_TREE_ENTRIES:
            return

        try:
            children = sorted(current.iterdir(), key=lambda p: p.name)
        except PermissionError:
            return

        for child in children:
            if len(entries) > MAX_TREE_ENTRIES:
                return
            try:
                stat = child.stat()
            except OSError:
                continue
            entry: dict[str, Any] = {
                "path": str(child),
                "name": child.name,
                "type": "directory" if child.is_dir() else "file",
                "size": stat.st_size if not child.is_dir() else None,
                "mtime": _format_mtime(stat.st_mtime),
                "depth": current_depth,
            }
            entries.append(entry)
            if child.is_dir() and current_depth < max_depth:
                self._walk_tree(child, max_depth, current_depth + 1, entries)

    # ------------------------------------------------------------------
    # search_files
    # ------------------------------------------------------------------

    async def search_files(
        self,
        query: str,
        root: str,
        path_glob: str,
        regex: bool,
        max_matches: int,
    ) -> dict[str, Any]:
        query = query.strip()
        normalized_query = query.lower()
        root = root.strip()
        path_glob = path_glob.strip()
        max_matches = min(max(1, max_matches), MAX_SEARCH_MATCHES)

        if not query and not path_glob:
            return {
                "success": False,
                "error_type": "invalid_argument",
                "hint": HINT_SEARCH_INVALID_ARGUMENT,
            }

        # Determine which roots to search.
        search_roots: list[Path] = []
        if root:
            # Match by name or by path.
            matched = False
            for r in self._settings.roots:
                if root == r.name or root == str(r.path):
                    search_roots.append(r.path)
                    matched = True
                    break
            if not matched:
                resolved_root, error = self._resolve_directory(root)
                if error is not None:
                    return error
                search_roots.append(resolved_root)
        else:
            search_roots = [r.path for r in self._settings.roots]

        # Compile regex if needed.
        pattern: re.Pattern[str] | None = None
        if query and regex:
            try:
                pattern = re.compile(query, re.IGNORECASE)
            except re.error:
                return {
                    "success": False,
                    "error_type": "invalid_regex",
                    "hint": HINT_SEARCH_INVALID_REGEX,
                }

        matches: list[dict[str, Any]] = []
        truncated = False

        for search_root in search_roots:
            if truncated:
                break
            truncated = await self._search_in_root(
                search_root, normalized_query, path_glob, pattern, max_matches, matches,
            )

        if not matches:
            return {
                "success": True,
                "query": query or None,
                "matches": [],
                "match_count": 0,
                "truncated": False,
                "hint": HINT_SEARCH_NO_MATCHES,
            }

        return {
            "success": True,
            "query": query or None,
            "matches": matches,
            "match_count": len(matches),
            "truncated": truncated,
            "hint": HINT_SEARCH_TRUNCATED if truncated else HINT_SEARCH_COMPLETE,
        }

    async def _search_in_root(
        self,
        root: Path,
        normalized_query: str,
        path_glob: str,
        pattern: re.Pattern[str] | None,
        max_matches: int,
        matches: list[dict[str, Any]],
    ) -> bool:
        """Walk files under root and collect matches. Returns True if truncated."""
        for dirpath, _dirnames, filenames in os.walk(root):
            for filename in filenames:
                if len(matches) >= max_matches:
                    return True

                file_path = Path(dirpath) / filename

                # Apply glob filter on the path relative to root.
                if path_glob:
                    relative = file_path.relative_to(root)
                    if not _matches_path_glob(relative, path_glob):
                        continue

                # Name-only search: no query, just glob matching.
                if not normalized_query:
                    matches.append({
                        "path": str(file_path),
                        "line": None,
                        "preview": None,
                    })
                    continue

                # Skip binary files silently.
                if _is_binary(file_path):
                    continue

                # Content search.
                try:
                    async with aiofiles.open(
                        file_path, encoding="utf-8", errors="replace",
                    ) as f:
                        line_no = 0
                        async for line in f:
                            line_no += 1
                            if len(matches) >= max_matches:
                                return True
                            hit = False
                            if pattern is not None:
                                hit = pattern.search(line) is not None
                            else:
                                hit = normalized_query in line.lower()
                            if hit:
                                matches.append({
                                    "path": str(file_path),
                                    "line": line_no,
                                    "preview": line.rstrip("\n\r"),
                                })
                except OSError:
                    continue

        return len(matches) >= max_matches

    # ------------------------------------------------------------------
    # read_file
    # ------------------------------------------------------------------

    async def read_file(
        self,
        path: str,
        start_line: int,
        max_lines: int,
        tail: int,
    ) -> dict[str, Any]:
        resolved, error = self._resolve_text_file(path)
        if error is not None:
            return error

        # Validate parameters.
        max_lines = min(max_lines, MAX_READ_LINES) if max_lines > 0 else DEFAULT_READ_LINES
        if tail < 0 or (tail == 0 and start_line < 1):
            return {
                "success": False,
                "error_type": "invalid_argument",
                "hint": HINT_READ_FILE_INVALID_ARGUMENT,
            }

        async with aiofiles.open(
            resolved, encoding="utf-8", errors="replace",
        ) as f:
            all_lines = (await f.read()).splitlines()

        total_lines = len(all_lines)

        if total_lines == 0:
            return {
                "success": True,
                "path": str(resolved),
                "start_line": 0,
                "end_line": 0,
                "total_lines": 0,
                "content": "",
                "truncated": False,
                "hint": HINT_READ_FILE_EMPTY,
            }

        # Determine the slice.
        if tail > 0:
            tail = min(tail, MAX_READ_LINES)
            actual_start = max(total_lines - tail, 0)
            actual_end = total_lines
        else:
            actual_start = start_line - 1  # convert to 0-based
            if actual_start >= total_lines:
                return {
                    "success": False,
                    "error_type": "line_out_of_range",
                    "hint": HINT_READ_FILE_LINE_OUT_OF_RANGE,
                }
            actual_end = min(actual_start + max_lines, total_lines)

        selected = all_lines[actual_start:actual_end]
        truncated = actual_end < total_lines

        # Format with line numbers.
        numbered_lines: list[str] = []
        width = len(str(actual_end))
        for i, line in enumerate(selected, start=actual_start + 1):
            numbered_lines.append(f"{i:>{width}}\t{line}")
        content = "\n".join(numbered_lines) + "\n" if numbered_lines else ""

        result: dict[str, Any] = {
            "success": True,
            "path": str(resolved),
            "start_line": actual_start + 1,
            "end_line": actual_end,
            "total_lines": total_lines,
            "content": content,
            "truncated": truncated,
            "hint": HINT_READ_FILE_TRUNCATED if truncated else HINT_READ_FILE_COMPLETE,
        }
        if tail > 0:
            result["tail"] = tail
        return result

    # ------------------------------------------------------------------
    # search_file_reverse
    # ------------------------------------------------------------------

    async def search_file_reverse(
        self,
        path: str,
        query: str,
        max_matches: int,
        before: int,
        after: int,
        regex: bool,
    ) -> dict[str, Any]:
        query = query.strip()
        if not query:
            return {
                "success": False,
                "error_type": "invalid_argument",
                "hint": HINT_REVERSE_SEARCH_INVALID_ARGUMENT,
            }
        normalized_query = query.lower()

        max_matches = min(max(1, max_matches), MAX_REVERSE_MATCHES)
        before = min(max(0, before), MAX_CONTEXT_LINES)
        after = min(max(0, after), MAX_CONTEXT_LINES)
        resolved, error = self._resolve_text_file(path)
        if error is not None:
            return error

        # Compile regex if needed.
        pattern: re.Pattern[str] | None = None
        if regex:
            try:
                pattern = re.compile(query, re.IGNORECASE)
            except re.error:
                return {
                    "success": False,
                    "error_type": "invalid_regex",
                    "hint": HINT_REVERSE_SEARCH_INVALID_REGEX,
                }

        async with aiofiles.open(
            resolved, encoding="utf-8", errors="replace",
        ) as f:
            all_lines = (await f.read()).splitlines()

        matches: list[dict[str, Any]] = []
        truncated = False

        for line_idx in range(len(all_lines) - 1, -1, -1):
            if len(matches) >= max_matches:
                truncated = True
                break

            line = all_lines[line_idx]
            hit = (
                pattern.search(line) is not None
                if pattern is not None
                else normalized_query in line.lower()
            )
            if not hit:
                continue

            before_start = max(0, line_idx - before)
            after_end = min(len(all_lines), line_idx + 1 + after)

            matches.append({
                "line": line_idx + 1,
                "match": line,
                "before": all_lines[before_start:line_idx],
                "after": all_lines[line_idx + 1:after_end],
            })

        if not matches:
            return {
                "success": True,
                "path": str(resolved),
                "query": query,
                "matches": [],
                "match_count": 0,
                "order": "newest_first",
                "truncated": False,
                "hint": HINT_REVERSE_SEARCH_NO_MATCHES,
            }

        return {
            "success": True,
            "path": str(resolved),
            "query": query,
            "matches": matches,
            "match_count": len(matches),
            "order": "newest_first",
            "truncated": truncated,
            "hint": (
                HINT_REVERSE_SEARCH_TRUNCATED
                if truncated
                else HINT_REVERSE_SEARCH_COMPLETE
            ),
        }
