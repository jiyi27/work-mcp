from __future__ import annotations

from ...hints import STOP_NOTIFY_AND_ASK_USER_HOW_TO_PROCEED_INSTRUCTION

# Tool names — single source of truth used in registrations and cross-tool hints.
TOOL_SEARCH_LOGS = "search_logs"
TOOL_LIST_LOG_SERVICES = "list_log_services"

# Tool descriptions
SEARCH_LOGS_DESCRIPTION = """\
Search recent server logs for a service and return matching JSON log entries.

Use this when debugging a bug or tracing a request — provide a known identifier
such as a requestId, traceId, or topic value to find all related log entries.
"""

LIST_LOG_SERVICES_DESCRIPTION = (
    f"List all services available for log search, with their most recent log file and modification time.\n\n"
    f"Call this before {TOOL_SEARCH_LOGS} when you do not know the correct service name."
)

# Hints returned inside tool responses to guide the calling agent.
HINT_NO_SERVICES_CONFIGURED = (
    "No log services are configured. "
    f"{STOP_NOTIFY_AND_ASK_USER_HOW_TO_PROCEED_INSTRUCTION}"
)

HINT_INVALID_SERVICE = (
    f"The service name is not recognized. "
    f"Call {TOOL_LIST_LOG_SERVICES} to get valid names, then retry with the correct service."
)

HINT_NO_RESULTS = (
    f"No matching log entries found. "
    f"Try a different query string, or call {TOOL_LIST_LOG_SERVICES} to verify the service name."
)
