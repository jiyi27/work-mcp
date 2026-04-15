from __future__ import annotations

from ...hints import STOP_AND_NOTIFY_USER_INSTRUCTION
from .constants import (
    MAX_FILE_SIZE_MB,
    MAX_SEARCH_MATCHES,
    MAX_TREE_ENTRIES,
)

# ---------------------------------------------------------------------------
# Tool names — single source of truth for registrations and cross-tool hints.
# ---------------------------------------------------------------------------
TOOL_DESCRIBE_ENVIRONMENT = "remote_describe_environment"
TOOL_LIST_TREE = "remote_list_tree"
TOOL_SEARCH_FILES = "remote_search_files"
TOOL_READ_FILE = "remote_read_file"
TOOL_SEARCH_FILE_REVERSE = "remote_search_file_reverse"

# ---------------------------------------------------------------------------
# Tool descriptions — short, agent-oriented.
# ---------------------------------------------------------------------------
DESCRIBE_ENVIRONMENT_DESCRIPTION = """\
Return the remote server's root directories with their paths, roles, and descriptions.

Use this early in a remote-debugging session to learn what environment information is
available here, such as where synced project code, logs, config, runtime files, or
other useful server-side resources might live.

Skip this if the relevant roots are already known from earlier in the conversation.
"""

LIST_TREE_DESCRIPTION = """\
List the direct children of a known directory on the remote server filesystem, not the local workspace.

Use this after remote_describe_environment to explore an unfamiliar remote directory one level at a time.
"""

SEARCH_FILES_DESCRIPTION = """\
Search file contents or file names on the remote server filesystem, not the local workspace.

Use this for remote config, deployed code, nginx, entrypoints, bootstrap files, or server-side logs.

For filename-only search, leave query empty and use path_glob.
"""

READ_FILE_DESCRIPTION = """\
Read a selected text range from a known file on the remote server filesystem, not the local workspace.

Use this only after identifying the remote path through remote_describe_environment, remote_list_tree, or remote_search_files.
"""

SEARCH_FILE_REVERSE_DESCRIPTION = """\
Search a known remote text file from the end and return the newest matches first.

Use this for server or test-machine log inspection when the remote log path is already known.
"""

# ---------------------------------------------------------------------------
# Shared hints — reused across multiple tools.
# ---------------------------------------------------------------------------
HINT_PATH_NOT_ALLOWED = (
    "The path is outside all configured roots. "
    f"{STOP_AND_NOTIFY_USER_INSTRUCTION}: the requested path is not accessible."
)

HINT_PATH_NOT_FOUND = (
    "The path does not exist. Do not guess a replacement path. Use "
    f"{TOOL_DESCRIBE_ENVIRONMENT}, {TOOL_LIST_TREE}, or {TOOL_SEARCH_FILES} "
    "to locate the correct path."
)

HINT_NOT_A_FILE = (
    f"The path is a directory, not a file. Use {TOOL_LIST_TREE} to inspect "
    "its contents."
)

HINT_NOT_A_DIRECTORY = (
    f"The path is a file, not a directory. Use {TOOL_READ_FILE} to read a "
    "range from it."
)

HINT_BINARY_FILE_NOT_SUPPORTED = (
    "The file appears to be binary. Do not retry with the same tool. "
    f"{STOP_AND_NOTIFY_USER_INSTRUCTION}: this tool only supports text files."
)

HINT_FILE_TOO_LARGE = (
    f"The file is larger than {MAX_FILE_SIZE_MB} MB. Do not read it directly with "
    f"{TOOL_READ_FILE} or {TOOL_SEARCH_FILE_REVERSE}. Narrow the target file first "
    f"or {STOP_AND_NOTIFY_USER_INSTRUCTION}: the file is too large for this tool."
)

# ---------------------------------------------------------------------------
# describe_environment hints
# ---------------------------------------------------------------------------
HINT_ROOTS_FOUND = (
    "The remote environment description may include useful roots such as code, logs, "
    "config, or runtime data, and it may also omit information you still need. If the "
    "returned roots are enough, continue with "
    f"{TOOL_LIST_TREE} or {TOOL_SEARCH_FILES}. If something is still unclear, explore "
    "within those returned roots first. You can only access the roots returned here; "
    "files outside them are not accessible. If the needed path or resource appears to "
    "be outside those roots, stop and ask the user to help resolve that gap."
)

HINT_NO_ROOTS = (
    "No roots are configured on the server. "
    f"{STOP_AND_NOTIFY_USER_INSTRUCTION}: the remote inspection tools have "
    "no allowed roots configured."
)

# ---------------------------------------------------------------------------
# list_tree hints
# ---------------------------------------------------------------------------
HINT_LIST_TREE_COMPLETE = (
    "The directory listing is complete. Choose a relevant subdirectory and call "
    f"{TOOL_LIST_TREE} again, or use {TOOL_READ_FILE} or {TOOL_SEARCH_FILES} if "
    "you already know the target."
)


def build_list_tree_truncated_hint(offset: int, next_offset: int) -> str:
    return (
        f"The directory listing reached the server limit ({MAX_TREE_ENTRIES} entries). "
        f"If you need more entries, call {TOOL_LIST_TREE} again with offset={next_offset}. "
        f"This page started at offset={offset}. If you already know a narrower target, "
        f"use {TOOL_SEARCH_FILES} with a narrower root or path_glob."
    )


def build_list_tree_hint(
    *,
    truncated: bool,
    offset: int,
    next_offset: int,
) -> str:
    return (
        build_list_tree_truncated_hint(offset, next_offset)
        if truncated
        else HINT_LIST_TREE_COMPLETE
    )

HINT_LIST_TREE_PATH_NOT_FOUND = (
    "The directory path does not exist. Verify the path against the allowed "
    f"roots or use {TOOL_LIST_TREE} on a higher-level directory first."
)

HINT_LIST_TREE_INVALID_OFFSET = (
    "The requested offset is invalid. Use offset 0 or a positive integer to continue "
    f"paging through {TOOL_LIST_TREE} results."
)

# ---------------------------------------------------------------------------
# search_files hints
# ---------------------------------------------------------------------------
HINT_SEARCH_COMPLETE = (
    "Matches were found. Pick the most relevant file, then use "
    f"{TOOL_READ_FILE} to read a small range around the returned line."
)

HINT_SEARCH_TRUNCATED = (
    f"The search result reached the server limit ({MAX_SEARCH_MATCHES} matches). "
    "Narrow the search with a more specific root, path_glob, or query before "
    "retrying."
)

HINT_SEARCH_NO_MATCHES = (
    "No matches were found. Check the query text, file pattern, and chosen "
    "root. If the target is a log file and you already know its path, use "
    f"{TOOL_SEARCH_FILE_REVERSE} instead of broad cross-file search. For filename-only "
    "search, leave query empty and set path_glob."
)

HINT_SEARCH_INVALID_REGEX = (
    "The query is not a valid regular expression. Fix the pattern and retry."
)

HINT_SEARCH_INVALID_ARGUMENT = (
    "At least one of query or path_glob is required. Provide a content query, "
    "a file name pattern, or both."
)

# ---------------------------------------------------------------------------
# read_file hints
# ---------------------------------------------------------------------------
HINT_READ_FILE_COMPLETE = (
    "The requested range was returned. Continue analysis, or call "
    f"{TOOL_READ_FILE} again with a different range if more context is needed."
)

HINT_READ_FILE_TRUNCATED = (
    "More lines exist outside the returned range. If more context is needed, "
    f"call {TOOL_READ_FILE} again with the next range."
)

HINT_READ_FILE_EMPTY = "The file exists but contains no text lines."

HINT_READ_FILE_INVALID_ARGUMENT = (
    "The requested line range is invalid. Use a positive start_line, positive "
    "max_lines, and a non-negative tail."
)

HINT_READ_FILE_LINE_OUT_OF_RANGE = (
    "The requested start_line is beyond the end of the file. Use a smaller "
    "start_line or read from the tail instead."
)

# ---------------------------------------------------------------------------
# search_file_reverse hints
# ---------------------------------------------------------------------------
HINT_REVERSE_SEARCH_COMPLETE = (
    "Recent matches were found. Use the returned context to analyze the issue. "
    f"If more surrounding lines are needed, call {TOOL_READ_FILE} for the "
    "matched path and line range."
)

HINT_REVERSE_SEARCH_TRUNCATED = (
    "The newest matches reached the server limit. If you need fewer but richer "
    "results, retry with a more specific query or smaller match count."
)

HINT_REVERSE_SEARCH_NO_MATCHES = (
    "No matches were found in this file. Verify the query text. If the file "
    f"path may be wrong, use {TOOL_LIST_TREE} or {TOOL_SEARCH_FILES} first."
)

HINT_REVERSE_SEARCH_INVALID_ARGUMENT = (
    "The search arguments are invalid. Provide a non-empty query and valid "
    "positive limits for matches and context lines."
)

HINT_REVERSE_SEARCH_INVALID_REGEX = (
    "The query is not a valid regular expression. Fix the pattern and retry."
)
