from __future__ import annotations

from ...hints import STOP_AND_NOTIFY_USER_INSTRUCTION
from .constants import (
    MAX_FILE_SIZE_MB,
    MAX_REVERSE_MATCHES,
    MAX_SEARCH_MATCHES,
    MAX_TREE_ENTRIES,
)

# ---------------------------------------------------------------------------
# Tool names — single source of truth for registrations and cross-tool hints.
# ---------------------------------------------------------------------------
TOOL_DESCRIBE_ENVIRONMENT = "remote_describe_environment"
TOOL_LIST_TREE = "remote_list_tree"
TOOL_GREP = "remote_grep"
TOOL_READ_FILE = "remote_read_file"
TOOL_SEARCH_FILE = "remote_search_file"

# ---------------------------------------------------------------------------
# Tool descriptions — short, agent-oriented.
# ---------------------------------------------------------------------------
DESCRIBE_ENVIRONMENT_DESCRIPTION = """\
Return the remote server's root directories with their paths and descriptions.

Use this early in a remote-debugging session to learn what environment information is
available here, such as where synced project code, logs, config, runtime files, or
other useful server-side resources might live.

Skip this if the relevant roots are already known from earlier in the conversation.
"""

LIST_TREE_DESCRIPTION = f"""\
List the direct children of a known directory on the remote server filesystem, not the local workspace.

Use this after {TOOL_DESCRIBE_ENVIRONMENT} to explore an unfamiliar remote directory one level at a time.
"""

GREP_DESCRIPTION = """\
Search the remote server filesystem by file content or by file name.

Content search: provide query to grep file contents. Returns one result per matched
file — the first matching line, total match count in that file, and path. Results are
capped at 20 files; no offset pagination is available, so pair query with path_glob
to stay under the cap.

Filename search: omit query and set path_glob to find files by name pattern
(e.g. **/*.log). Returns matching file paths with no line numbers.

Use this for remote config, deployed code, nginx, entrypoints, or server-side logs.
"""

READ_FILE_DESCRIPTION = f"""\
Read a selected text range from a known file on the remote server filesystem, not the local workspace.

Use this only after identifying the remote path through {TOOL_DESCRIBE_ENVIRONMENT}, {TOOL_LIST_TREE}, or {TOOL_GREP}.
"""

SEARCH_FILE_DESCRIPTION = f"""\
Search a single known file on the remote server and return matched lines with nearby context.

Use this for log inspection or focused file analysis when the exact remote file path is
already known. Set from_end=true to scan from the end and surface the newest matches first.
Set from_end=false to scan from the beginning when chronological order matters.

For cross-file content search or to locate the file path first, use {TOOL_GREP} instead.
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
    f"{TOOL_DESCRIBE_ENVIRONMENT}, {TOOL_LIST_TREE}, or {TOOL_GREP} "
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
    f"{TOOL_READ_FILE} or {TOOL_SEARCH_FILE}. Narrow the target file first "
    f"or {STOP_AND_NOTIFY_USER_INSTRUCTION}: the file is too large for this tool."
)

# ---------------------------------------------------------------------------
# describe_environment hints
# ---------------------------------------------------------------------------
HINT_ROOTS_FOUND = (
    f"Use returned roots to explore with {TOOL_LIST_TREE}, {TOOL_GREP}, or "
    f"{TOOL_READ_FILE}. Only returned roots are accessible. If the needed path is "
    "outside them, stop and ask the user."
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
    "The directory listing is complete. Entries are grouped with directories first, "
    "then files; each group is sorted by most recently modified, then by name. "
    "Choose a relevant subdirectory and call "
    f"{TOOL_LIST_TREE} again, or use {TOOL_READ_FILE} or {TOOL_GREP} if you already know the target."
)


def build_list_tree_truncated_hint(offset: int, next_offset: int) -> str:
    return (
        f"The directory listing is capped at {MAX_TREE_ENTRIES} entries per page to keep "
        "responses manageable. Entries are grouped with directories first, then files; "
        "each group is sorted by most recently modified, then by name. "
        f"Call {TOOL_LIST_TREE} again with offset={next_offset} for "
        f"the next page (this page started at offset={offset}). If you already know a "
        f"narrower target, use {TOOL_GREP} with a path_glob instead."
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
SEARCH_SCOPE_GUIDANCE = (
    "Verify the query text, file pattern, and chosen root before retrying."
)

RUNTIME_CODE_CONFIRMATION_GUIDANCE = (
    "If you are debugging behavior from code, check the relevant code logic to confirm "
    "this is the exact runtime string, file name, config key, or log text you "
    "should be searching for."
)

SYNC_OR_TRIGGER_GUIDANCE = (
    "If you are searching logs or debugging runtime behavior, also consider "
    "whether the code has not synced to the server yet, or the request / "
    "interface did not trigger successfully, so the expected file write or "
    "log line never happened. Ignore this if you are searching for other "
    "kinds of content such as config, filenames, or static code."
)

LOG_REVERSE_SEARCH_GUIDANCE = (
    "These matches come from a broad cross-file search and are not intended to "
    "identify the newest log entry. If the target is a log file and you already "
    f"know its path, use {TOOL_SEARCH_FILE} with from_end=true to find the most recent "
    "matching log lines first."
)

HINT_SEARCH_COMPLETE = (
    "Matches were found. For content search results, use "
    f"{TOOL_READ_FILE} to read a range around the returned line number. "
    f"For filename-only results (line is null), use {TOOL_READ_FILE} or "
    f"{TOOL_SEARCH_FILE} to inspect the file."
)

HINT_SEARCH_TRUNCATED = (
    f"The search reached the limit of {MAX_SEARCH_MATCHES} matched files — results are "
    "capped to avoid exhausting the context window and there is no offset pagination. "
    "There may be more matching files not shown. Narrow the search with a more specific "
    f"root, path_glob, or query before retrying. {LOG_REVERSE_SEARCH_GUIDANCE}"
)

HINT_SEARCH_NO_MATCHES = (
    "No matches were found. "
    f"{SEARCH_SCOPE_GUIDANCE} "
    f"{RUNTIME_CODE_CONFIRMATION_GUIDANCE} "
    f"{SYNC_OR_TRIGGER_GUIDANCE} "
    f"If the target is a log file and you already know its path, use {TOOL_SEARCH_FILE} "
    "with from_end=true instead of broad cross-file search. For filename-only search, leave query "
    "empty and set path_glob."
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
    "The file has more lines beyond the returned range — see total_lines in the response "
    "for the full size. Each call is capped to keep responses context-efficient. "
    f"Call {TOOL_READ_FILE} again with a different start_line or tail to read another section."
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
# search_file hints
# ---------------------------------------------------------------------------
def build_search_file_complete_hint(*, from_end: bool) -> str:
    direction = (
        "Results were scanned from the end of the file, so the newest matches appear first."
        if from_end
        else "Results were scanned from the beginning of the file, so matches follow file order."
    )
    return (
        f"{direction} Use the returned context to analyze the issue. If more surrounding "
        f"lines are needed, call {TOOL_READ_FILE} for the matched path and line range."
    )

def build_search_file_truncated_hint(*, from_end: bool) -> str:
    direction = (
        f"Results were scanned from the end of the file, and the newest {MAX_REVERSE_MATCHES} matches were returned because from_end=true."
        if from_end
        else f"Results were scanned from the beginning of the file, and the first {MAX_REVERSE_MATCHES} matches were returned because from_end=false."
    )
    return (
        f"{direction} Results are capped to avoid flooding the context with file content. "
        "There may be more matches outside the returned window. To see fewer, more targeted "
        f"results, retry with a more specific query. To read surrounding context for a specific "
        f"hit, call {TOOL_READ_FILE} with the matched path and line range."
    )

def build_search_file_no_matches_hint(*, from_end: bool) -> str:
    direction = (
        "No matches were found when scanning from the end of this file."
        if from_end
        else "No matches were found when scanning from the beginning of this file."
    )
    return (
        f"{direction} Verify the query text against the exact runtime string you expect "
        "from the relevant code logic. Verify this is the correct remote log or runtime "
        f"file; if the path may be wrong, use {TOOL_LIST_TREE} or {TOOL_GREP} first. "
        f"{SYNC_OR_TRIGGER_GUIDANCE}"
    )

HINT_SEARCH_FILE_INVALID_ARGUMENT = (
    "The search arguments are invalid. Provide a non-empty query."
)

HINT_SEARCH_FILE_INVALID_REGEX = (
    "The query is not a valid regular expression. Fix the pattern and retry."
)
