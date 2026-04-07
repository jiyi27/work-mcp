from __future__ import annotations

from ...hints import STOP_NOTIFY_AND_ASK_USER_HOW_TO_PROCEED_INSTRUCTION


JIRA_INVESTIGATE_ISSUE_HINT = (
    "If you cannot determine the root cause or the issue appears to already be resolved, "
    "stop processing, summarize your findings, tell the user in your reply, "
    "and ask the user how you should proceed."
)

JIRA_TRANSITION_FAILURE_HINT = (
    "The Jira workflow change could not be completed. "
    "Stop execution, summarize what you completed, tell the user in your reply "
    "with the current status, target status, and available target statuses, "
    "and ask the user how you should proceed."
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
