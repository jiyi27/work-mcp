from __future__ import annotations

from ...hints import STOP_AND_NOTIFY_USER_INSTRUCTION

# Tool names — single source of truth used in registrations and cross-tool hints.
TOOL_LIST_LOG_FILES = "list_log_files"
TOOL_SEARCH_LOG = "search_log"

# Tool descriptions
LIST_LOG_FILES_DESCRIPTION = f"""\
List one level of files and subdirectories under the log root or a relative log path.

Use this to navigate the log directory tree and identify which file to search.
Start with path="" to see the log root, then drill into subdirectories as needed.
Each file entry includes its path, which can be passed directly to {TOOL_SEARCH_LOG}.
"""

SEARCH_LOG_DESCRIPTION = f"""\
Search a single log file for lines containing a query string and return matching lines with context.

Use this after {TOOL_LIST_LOG_FILES} to search a specific file. Provide a known identifier
such as a request ID, trace ID, error message, or status code.
"""

# Hints returned inside tool responses to guide the calling agent.
HINT_LIST_LOG_FILES_SUCCESS = (
    f"The result shows one level of the log directory tree for the returned path. "
    f"Continue calling {TOOL_LIST_LOG_FILES} with a directory path to drill down. "
    f"Use {TOOL_SEARCH_LOG} only after you identify a file to search."
)

HINT_PATH_OUTSIDE_BASE = (
    "The path resolves outside the configured log directory. "
    f"{STOP_AND_NOTIFY_USER_INSTRUCTION}"
)

HINT_NO_RESULTS = (
    f"No matching lines found in this file. The query may not exist in this log.\n\n"
    f"Before trying other files:\n"
    f"1. Check the source code to confirm this log file is where the event you are searching for "
    f"would be written — it may belong to a different category or service.\n"
    f"2. Verify that the code path was actually executed — an exception or early return earlier "
    f"in the flow may have prevented this log line from being written.\n\n"
    f"If you have confirmed both of the above and still cannot find the log, and this log is "
    f"required to continue the bug investigation, stop and ask the user to provide the relevant "
    f"log content directly."
)

HINT_FILE_NOT_FOUND = (
    f"Verify the path is correct. "
    f"Paths passed to {TOOL_SEARCH_LOG} must be relative to the log root — do not use absolute "
    f"paths or construct paths manually. "
    f"The `path` field in each entry returned by {TOOL_LIST_LOG_FILES} is already in the correct "
    f"format and can be passed directly. "
    f"Call {TOOL_LIST_LOG_FILES} with path=\"\" to browse from the log root and confirm the "
    f"correct file path."
)
