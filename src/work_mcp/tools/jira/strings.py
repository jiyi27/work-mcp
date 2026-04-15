from __future__ import annotations

from ...hints import STOP_NOTIFY_AND_ASK_USER_HOW_TO_PROCEED_INSTRUCTION


JIRA_LIST_OPEN_ASSIGNED_ISSUES_TOOL_NAME = "jira_list_open_assigned_issues"
JIRA_GET_ISSUE_DETAILS_TOOL_NAME = "jira_get_issue_details"
JIRA_START_ISSUE_TOOL_NAME = "jira_start_issue"
JIRA_RESOLVE_ISSUE_TOOL_NAME = "jira_resolve_issue"

JIRA_LIST_OPEN_ASSIGNED_ISSUES_SUCCESS_HINT = (
    "These are the user's currently open Jira issues. Stop here. In your reply, "
    "list them in the format `KEY: title`, then ask the user which issue key they want help with. "
    "Do not investigate any issue until the user selects one."
)

JIRA_LIST_OPEN_ASSIGNED_ISSUES_EMPTY_HINT = (
    "No open Jira issues were found for the current user in the configured project and status scope. "
    "Stop and tell the user in your reply that no open issues are currently visible. "
    "If this seems unexpected, suggest checking whether `jira.project_key` or "
    "`jira.latest_assigned_statuses` in `config.yaml` is configured correctly."
)

JIRA_GET_ISSUE_DETAILS_SUCCESS_HINT = (
    "This is the Jira issue the user selected. You may now investigate it. "
    "If the root cause is unclear, the issue appears already resolved, or important context is missing, "
    "stop, summarize your findings, tell the user in your reply, and ask how you should proceed."
)

JIRA_TRANSITION_FAILURE_HINT = (
    "The Jira workflow change could not be completed. "
    "Stop execution, summarize what you completed, tell the user in your reply "
    "with the current status, target status, and available target statuses, "
    "and ask the user how you should proceed."
)

JIRA_IMAGE_ATTACHMENT_CONTEXT_MISSING_HINT = (
    "This issue includes image attachments, but this tool does not return image contents yet. "
    "Do not assume the issue context is complete if the task may depend on visual details. "
    "Before proceeding with implementation or diagnosis, ask the user to summarize the relevant image contents."
)


def jira_issue_not_found_hint(issue_key: str) -> str:
    return (
        f"Issue {issue_key} was not found. "
        "Only retry with a different key if you are certain you used the wrong one; "
        f"do not guess. Otherwise {STOP_NOTIFY_AND_ASK_USER_HOW_TO_PROCEED_INSTRUCTION}"
    )


def jira_project_not_allowed_hint(issue_key: str) -> str:
    return (
        f"{issue_key} is outside the configured Jira project scope. "
        "Do not retry this write operation. "
        f"{STOP_NOTIFY_AND_ASK_USER_HOW_TO_PROCEED_INSTRUCTION}"
    )


def jira_issue_details_project_not_allowed_hint(issue_key: str) -> str:
    return (
        f"{issue_key} is outside the configured Jira project scope. "
        "Do not retry with a different issue key unless the user gives one explicitly. "
        f"{STOP_NOTIFY_AND_ASK_USER_HOW_TO_PROCEED_INSTRUCTION}"
    )


def jira_assignee_not_allowed_hint(issue_key: str) -> str:
    return (
        f"{issue_key} is not currently assigned to you. "
        "Do not retry this write operation unless the issue is reassigned to you. "
        f"{STOP_NOTIFY_AND_ASK_USER_HOW_TO_PROCEED_INSTRUCTION}"
    )


def jira_attachment_not_found_hint(issue_key: str, attachment_id: str) -> str:
    return (
        f"Attachment {attachment_id} was not found on {issue_key}, or it is not a supported image attachment. "
        "Do not guess another attachment id. "
        f"{STOP_NOTIFY_AND_ASK_USER_HOW_TO_PROCEED_INSTRUCTION}"
    )
