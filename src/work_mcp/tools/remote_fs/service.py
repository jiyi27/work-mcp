from __future__ import annotations


import fnmatch
import os
import re
from pathlib import Path
from typing import Any

import aiofiles

from ...config import RemoteFsSettings
from .constants import (
    BINARY_CHECK_BYTES,
    DEFAULT_READ_LINES,
    HIDE_TOP_LEVEL_DOTFILES,
    LIST_TREE_IGNORED_DIRECTORY_NAMES,
    LIST_TREE_IGNORED_DIRECTORY_SUFFIXES,
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
    HINT_LIST_TREE_INVALID_OFFSET,
    HINT_LIST_TREE_PATH_NOT_FOUND,
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
    build_list_tree_hint,
)


def _is_binary(path: Path) -> bool:
    """Return True if the file appears to be binary by checking for null bytes."""
    try:
        with path.open("rb") as f:
            chunk = f.read(BINARY_CHECK_BYTES)
        return b"\x00" in chunk
    except OSError:
        return False


def _matches_path_glob(relative_path: Path, path_glob: str) -> bool:
    relative_str = relative_path.as_posix()
    if fnmatch.fnmatch(relative_str, path_glob):
        return True
    if path_glob.startswith("**/"):
        return fnmatch.fnmatch(relative_str, path_glob.removeprefix("**/"))
    return False


def _should_skip_tree_directory(path: Path) -> bool:
    if path.name in LIST_TREE_IGNORED_DIRECTORY_NAMES:
        return True
    parts = path.parts
    return any(
        len(parts) >= len(suffix) and parts[-len(suffix):] == suffix
        for suffix in LIST_TREE_IGNORED_DIRECTORY_SUFFIXES
    )


def _is_hidden(path: Path) -> bool:
    return path.name.startswith(".")


def _should_skip_root_level_entry(parent: Path, child: Path) -> bool:
    if not HIDE_TOP_LEVEL_DOTFILES:
        return False
    return parent == child.parent and _is_hidden(child)


def _apply_directory_filters(dirnames: list[str], current: Path, root: Path) -> None:
    kept = []
    for dirname in dirnames:
        child = current / dirname
        if _should_skip_tree_directory(child):
            continue
        if current == root and _should_skip_root_level_entry(current, child):
            continue
        kept.append(dirname)
    dirnames[:] = kept


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

    def list_tree(self, path: str, offset: int) -> dict[str, Any]:
        if offset < 0:
            return {
                "success": False,
                "error_type": "invalid_argument",
                "hint": HINT_LIST_TREE_INVALID_OFFSET,
            }

        # Verify path is within allowed roots and is an existing directory.
        dir_path, error = self._resolve_directory(path)
        if error is not None:
            return error

        # Each item describes one file or directory found during the walk,
        # e.g. {"path": "/data/a.txt", "type": "file"}
        fs_nodes: list[dict[str, Any]] = []
        self._walk_tree(dir_path, fs_nodes)
        fs_nodes.sort(
            key=lambda entry: (
                0 if entry["type"] == "directory" else 1,
                Path(entry["path"]).name,
            )
        )
        total_count = len(fs_nodes)
        page_entries = fs_nodes[offset:offset + MAX_TREE_ENTRIES]
        returned_count = len(page_entries)
        result_entries = [
            {"path": entry["path"], "type": entry["type"]}
            for entry in page_entries
        ]
        next_offset = offset + returned_count
        truncated = next_offset < total_count

        return {
            "success": True,
            "path": str(dir_path),
            "entries": result_entries,
            "offset": offset,
            "returned_count": returned_count,
            "next_offset": next_offset,
            "truncated": truncated,
            "hint": build_list_tree_hint(
                truncated=truncated,
                offset=offset,
                next_offset=next_offset,
            ),
        }

    def _walk_tree(self, current: Path, entries: list[dict[str, Any]]) -> None:
        try:
            children = sorted(current.iterdir(), key=lambda p: p.name)
        except PermissionError:
            return

        for child in children:
            if _should_skip_root_level_entry(current, child):
                continue
            if child.is_dir() and _should_skip_tree_directory(child):
                continue
            entry: dict[str, Any] = {
                "path": str(child),
                "type": "directory" if child.is_dir() else "file",
            }
            entries.append(entry)

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
                # root may be a subdirectory of a configured root — verify it is allowed and is a directory.
                dir_path, error = self._resolve_directory(root)
                if error is not None:
                    return error
                search_roots.append(dir_path)
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

        # Each item is a matched file, e.g. {"path": "/data/a.txt", "line": 42, "preview": "..."}
        search_hits: list[dict[str, Any]] = []
        truncated = False

        for search_root in search_roots:
            if truncated:
                break
            truncated = await self._search_in_root(
                search_root, normalized_query, path_glob, pattern, max_matches, search_hits,
            )

        if not search_hits:
            return {
                "success": True,
                "matches": [],
                "truncated": False,
                "hint": HINT_SEARCH_NO_MATCHES,
            }

        return {
            "success": True,
            "matches": search_hits,
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
        search_hits: list[dict[str, Any]],
    ) -> bool:
        """Walk files under root and collect one result per matched file."""
        for dirpath, dirnames, filenames in os.walk(root):
            current_dir = Path(dirpath)
            _apply_directory_filters(dirnames, current_dir, root)
            for filename in filenames:
                if len(search_hits) >= max_matches:
                    return True

                file_path = current_dir / filename
                if current_dir == root and _should_skip_root_level_entry(current_dir, file_path):
                    continue

                # Apply glob filter on the path relative to root.
                if path_glob:
                    relative_path = file_path.relative_to(root)
                    if not _matches_path_glob(relative_path, path_glob):
                        continue

                # Name-only search: no query, just glob matching.
                if not normalized_query:
                    search_hits.append({
                        "path": str(file_path),
                        "line": None,
                        "match_count": 0,
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
                        first_match_line: int | None = None
                        first_preview: str | None = None
                        match_count = 0
                        async for line in f:
                            line_no += 1
                            hit = False
                            if pattern is not None:
                                hit = pattern.search(line) is not None
                            else:
                                hit = normalized_query in line.lower()
                            if hit:
                                match_count += 1
                                if first_match_line is None:
                                    first_match_line = line_no
                                    first_preview = line.rstrip("\n\r")
                        if first_match_line is not None:
                            search_hits.append({
                                "path": str(file_path),
                                "line": first_match_line,
                                "match_count": match_count,
                                "preview": first_preview,
                            })
                except OSError:
                    continue

        return len(search_hits) >= max_matches

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
        # Verify path is within allowed roots, is a file, and is readable text.
        file_path, error = self._resolve_text_file(path)
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
            file_path, encoding="utf-8", errors="replace",
        ) as f:
            all_lines = (await f.read()).splitlines()

        total_lines = len(all_lines)

        if total_lines == 0:
            return {
                "success": True,
                "path": str(file_path),
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
            "path": str(file_path),
            "start_line": actual_start + 1,
            "end_line": actual_end,
            "total_lines": total_lines,
            "content": content,
            "truncated": truncated,
            "hint": HINT_READ_FILE_TRUNCATED if truncated else HINT_READ_FILE_COMPLETE,
        }
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
        # Verify path is within allowed roots, is a file, and is readable text.
        file_path, error = self._resolve_text_file(path)
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
            file_path, encoding="utf-8", errors="replace",
        ) as f:
            all_lines = (await f.read()).splitlines()

        # Each item is a matched line with context,
        # e.g. {"line": 42, "match": "foo bar", "before": [...], "after": [...]}
        search_hits: list[dict[str, Any]] = []
        truncated = False

        for line_idx in range(len(all_lines) - 1, -1, -1):
            if len(search_hits) >= max_matches:
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

            search_hits.append({
                "line": line_idx + 1,
                "match": line,
                "before": all_lines[before_start:line_idx],
                "after": all_lines[line_idx + 1:after_end],
            })

        if not search_hits:
            return {
                "success": True,
                "path": str(file_path),
                "matches": [],
                "truncated": False,
                "hint": HINT_REVERSE_SEARCH_NO_MATCHES,
            }

        return {
            "success": True,
            "path": str(file_path),
            "matches": search_hits,
            "truncated": truncated,
            "hint": (
                HINT_REVERSE_SEARCH_TRUNCATED
                if truncated
                else HINT_REVERSE_SEARCH_COMPLETE
            ),
        }
