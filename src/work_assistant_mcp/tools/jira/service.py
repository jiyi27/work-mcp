from __future__ import annotations

import base64
from typing import Any

from ...config import Settings
from ...hints import (
    INTERNAL_ERROR_RETRY_HINT,
    jira_accept_invalid_status_hint,
    jira_issue_not_found_hint,
    jira_project_not_allowed_hint,
    jira_resolve_invalid_status_hint,
    required_param_hint,
)
from ...logger import error, info, warning
from .client import JiraApiError, JiraClient
from .models import JiraIssue


JIRA_ISSUE_FIELDS = (
    "summary",
    "description",
    "status",
    "priority",
    "issuetype",
    "attachment",
    "updated",
)
OPEN_STATUS_CLAUSE = "statusCategory != Done"
BUG_ISSUE_TYPES = frozenset({"bug", "故障"})
TODO_STATUS_NAMES = frozenset({"todo", "待办", "open", "backlog", "new"})
ACCEPTED_STATUS_NAMES = frozenset({"已接收", "accepted", "in progress", "进行中"})


class JiraService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = JiraClient(settings)

    def get_current_fault(self) -> dict[str, Any]:
        info("jira.get_current_fault.started", {})
        try:
            issue = self._find_latest_assigned_fault()
        except JiraApiError as exc:
            error("jira.get_current_fault.api_error", {}, exc=exc)
            return self._internal_error(f"Jira API error while fetching the current fault: {exc.message}")

        if issue is None:
            info("jira.get_current_fault.not_found", {})
            return {"found": False}

        attachments = self._serialize_attachments(issue)
        info(
            "jira.get_current_fault.succeeded",
            {"issue_key": issue.key, "attachment_count": len(attachments)},
        )
        return {
            "found": True,
            "issue": {
                "key": issue.key,
                "summary": issue.summary,
                "description": issue.description,
                "status": issue.status,
                "priority": issue.priority,
                "issue_type": issue.issue_type,
            },
            "attachments": attachments,
        }

    def accept_issue(self, issue_key: str) -> dict[str, Any]:
        # The model only provides an issue key. Transition choice stays server-side so
        # the workflow change is constrained by trusted config instead of model output.
        return self._transition_issue(
            issue_key=issue_key.strip(),
            expected_statuses=TODO_STATUS_NAMES,
            transition_names=self._settings.jira_accept_transitions,
            invalid_status_hint=jira_accept_invalid_status_hint(issue_key),
            success_topic="jira.accept_issue.succeeded",
            operation_label="accepting",
        )

    def resolve_issue(self, issue_key: str) -> dict[str, Any]:
        # Keep the action surface minimal: issue_key identifies the target issue, while
        # the allowed resolve transition is selected from config to reduce bad or unsafe writes.
        return self._transition_issue(
            issue_key=issue_key.strip(),
            expected_statuses=ACCEPTED_STATUS_NAMES,
            transition_names=self._settings.jira_resolve_transitions,
            invalid_status_hint=jira_resolve_invalid_status_hint(issue_key),
            success_topic="jira.resolve_issue.succeeded",
            operation_label="resolving",
        )

    def _transition_issue(
        self,
        *,
        issue_key: str,
        expected_statuses: frozenset[str],
        transition_names: tuple[str, ...],
        invalid_status_hint: str,
        success_topic: str,
        operation_label: str,
    ) -> dict[str, Any]:
        if not issue_key:
            return {
                "success": False,
                "error_type": "invalid_input",
                "hint": required_param_hint("issue_key"),
            }

        try:
            issue = self._get_issue_by_key(issue_key)
        except JiraApiError as exc:
            error(success_topic.replace(".succeeded", ".lookup_failed"), {"issue_key": issue_key}, exc=exc)
            return self._internal_error(f"Jira API error while looking up {issue_key}: {exc.message}")

        if issue is None:
            warning(success_topic.replace(".succeeded", ".issue_not_found"), {"issue_key": issue_key})
            return {
                "success": False,
                "error_type": "issue_not_found",
                "hint": jira_issue_not_found_hint(issue_key),
            }

        if not self._is_allowed_project(issue.key):
            warning(success_topic.replace(".succeeded", ".project_not_allowed"), {"issue_key": issue.key})
            return {
                "success": False,
                "error_type": "project_not_allowed",
                "hint": jira_project_not_allowed_hint(issue.key),
            }

        if issue.status.lower() not in expected_statuses:
            warning(
                success_topic.replace(".succeeded", ".invalid_status"),
                {"issue_key": issue_key, "current_status": issue.status},
            )
            return {
                "success": False,
                "error_type": "invalid_status",
                "hint": invalid_status_hint,
            }

        try:
            transitions = self._client.get_transitions(issue_key)
        except JiraApiError as exc:
            error(success_topic.replace(".succeeded", ".transitions_failed"), {"issue_key": issue_key}, exc=exc)
            return self._internal_error(
                f"Jira API error while fetching transitions for {issue_key}: {exc.message}"
            )

        selected = self._find_transition(transitions, transition_names)
        if selected is None:
            warning(success_topic.replace(".succeeded", ".transition_not_found"), {"issue_key": issue_key})
            return self._internal_error(
                f"No configured Jira workflow transition matched for {issue_key}. Server configuration may need updating."
            )

        transition_id = str(selected.get("id") or "")
        if not transition_id:
            return self._internal_error(
                f"Jira returned a transition without an id while {operation_label} {issue_key}."
            )

        try:
            self._client.transition_issue(issue_key, transition_id)
        except JiraApiError as exc:
            error(
                success_topic.replace(".succeeded", ".transition_failed"),
                {"issue_key": issue_key, "transition_id": transition_id},
                exc=exc,
            )
            return self._internal_error(
                f"Jira API error while {operation_label} {issue_key}: {exc.message}"
            )

        info(
            success_topic,
            {"issue_key": issue_key, "transition_id": transition_id, "transition_name": selected.get("name")},
        )
        return {"success": True, "issue_key": issue_key}

    def _find_latest_assigned_fault(self) -> JiraIssue | None:
        issues = self._client.search_issues(
            jql=self._build_assigned_fault_jql(),
            fields=JIRA_ISSUE_FIELDS,
            max_results=10,
        )
        parsed = [JiraIssue.from_api(item) for item in issues]
        bug_issues = [item for item in parsed if item.issue_type.strip().lower() in BUG_ISSUE_TYPES]
        if not bug_issues:
            return None
        return bug_issues[0]

    def _get_issue_by_key(self, issue_key: str) -> JiraIssue | None:
        issues = self._client.search_issues(
            jql=f'key = "{issue_key}"',
            fields=("status", "summary", "description", "priority", "issuetype", "updated"),
            max_results=1,
        )
        if not issues:
            return None
        return JiraIssue.from_api(issues[0])

    def _build_assigned_fault_jql(self) -> str:
        if not self._settings.jira_project_key:
            raise RuntimeError(
                "Missing JIRA_PROJECT_KEY in environment or .env. Configure one Jira project key."
            )
        return (
            f'project = "{self._settings.jira_project_key}" AND assignee = currentUser() '
            f"AND {OPEN_STATUS_CLAUSE} ORDER BY updated DESC"
        )

    def _is_allowed_project(self, issue_key: str) -> bool:
        configured_project = self._settings.jira_project_key
        if not configured_project:
            return False
        issue_project = issue_key.split("-", 1)[0].strip()
        if not issue_project:
            return False
        return issue_project.lower() == configured_project.lower()

    def _serialize_attachments(self, issue: JiraIssue) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for attachment in issue.attachments[: self._settings.jira_attachment_max_images]:
            mime_type = str(attachment.get("mimeType") or "")
            if not mime_type.startswith("image/"):
                continue

            content_url = str(attachment.get("content") or "")
            if not content_url:
                continue

            try:
                raw = self._client.download_attachment(content_url)
            except JiraApiError as exc:
                warning(
                    "jira.get_current_fault.attachment_failed",
                    {"issue_key": issue.key, "filename": attachment.get("filename", "")},
                    exc=exc,
                )
                continue

            if len(raw) > self._settings.jira_attachment_max_bytes:
                warning(
                    "jira.get_current_fault.attachment_too_large",
                    {
                        "issue_key": issue.key,
                        "filename": attachment.get("filename", ""),
                        "size_bytes": len(raw),
                    },
                )
                continue

            results.append(
                {
                    "filename": str(attachment.get("filename") or ""),
                    "mime_type": mime_type,
                    "base64": base64.b64encode(raw).decode("ascii"),
                }
            )
        return results

    @staticmethod
    def _find_transition(
        transitions: list[dict[str, Any]], preferred_names: tuple[str, ...]
    ) -> dict[str, Any] | None:
        for name in preferred_names:
            for item in transitions:
                transition_name = item.get("name")
                if isinstance(transition_name, str) and transition_name.lower() == name.lower():
                    return item
        return None

    @staticmethod
    def _internal_error(message: str) -> dict[str, Any]:
        return {
            "success": False,
            "error_type": "internal_error",
            "message": message,
            "hint": INTERNAL_ERROR_RETRY_HINT,
        }
