from __future__ import annotations

import base64
from typing import Any

from ...config import Settings
from ...error_messages import format_http_service_error
from ...hints import (
    INTERNAL_ERROR_RETRY_HINT,
    required_param_hint,
)
from ...logger import error
from .client import JiraApiError, JiraClient
from .models import JiraIssue
from .strings import (
    JIRA_IMAGE_ATTACHMENT_CONTEXT_MISSING_HINT,
    JIRA_INVESTIGATE_ISSUE_HINT,
    JIRA_TRANSITION_FAILURE_HINT,
    jira_assignee_not_allowed_hint,
    jira_attachment_not_found_hint,
    jira_issue_not_found_hint,
    jira_project_not_allowed_hint,
)


JIRA_ISSUE_FIELDS = (
    "summary",
    "description",
    "status",
    "priority",
    "issuetype",
    "assignee",
    "attachment",
    "updated",
)


def _api_error_message(operation: str, exc: JiraApiError) -> str:
    return format_http_service_error(
        service_name="Jira",
        operation=operation,
        status_code=exc.status_code,
        error_message=exc.message,
        auth_env_names=("JIRA_BASE_URL", "JIRA_API_TOKEN"),
    )


class JiraService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = JiraClient(settings)

    def get_latest_assigned_issue(self) -> dict[str, Any]:
        try:
            issue = self._get_latest_assigned_issue()
        except JiraApiError as exc:
            error("jira.get_latest_assigned_issue.api_error", {}, exc=exc)
            return self._internal_error(_api_error_message("fetching the latest assigned issue", exc))

        if issue is None:
            return {"found": False}

        attachments = self._serialize_attachments(issue)
        result = {
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
            "hint": JIRA_INVESTIGATE_ISSUE_HINT,
        }
        if attachments:
            result["image_handling_hint"] = JIRA_IMAGE_ATTACHMENT_CONTEXT_MISSING_HINT
        return result

    def get_attachment_image(self, issue_key: str, attachment_id: str) -> dict[str, Any]:
        issue_key = issue_key.strip()
        attachment_id = attachment_id.strip()
        if not issue_key:
            return {
                "success": False,
                "error_type": "invalid_input",
                "hint": required_param_hint("issue_key"),
            }
        if not attachment_id:
            return {
                "success": False,
                "error_type": "invalid_input",
                "hint": required_param_hint("attachment_id"),
            }

        try:
            issue = self._get_issue_by_key(issue_key)
        except JiraApiError as exc:
            error("jira.get_attachment_image.lookup_failed", {"issue_key": issue_key}, exc=exc)
            return self._internal_error(_api_error_message(f"looking up {issue_key}", exc))

        if issue is None:
            return {
                "success": False,
                "error_type": "issue_not_found",
                "hint": jira_issue_not_found_hint(issue_key),
            }

        if not self._is_allowed_project(issue.key):
            return {
                "success": False,
                "error_type": "project_not_allowed",
                "hint": jira_project_not_allowed_hint(issue.key),
            }

        try:
            current_user_identifiers = self._client.get_current_user_identifiers()
        except JiraApiError as exc:
            error("jira.get_attachment_image.assignee_check_failed", {"issue_key": issue_key}, exc=exc)
            return self._internal_error(_api_error_message(f"checking assignee for {issue_key}", exc))

        if not issue.assignee.identifiers().intersection(current_user_identifiers):
            return {
                "success": False,
                "error_type": "assignee_not_allowed",
                "hint": jira_assignee_not_allowed_hint(issue.key),
            }

        attachment = self._find_image_attachment(issue, attachment_id)
        if attachment is None:
            return {
                "success": False,
                "error_type": "attachment_not_found",
                "hint": jira_attachment_not_found_hint(
                    issue.key, attachment_id
                ),
            }

        content_url = str(attachment.get("content") or "")
        if not content_url:
            return self._internal_error(
                f"Jira attachment {attachment_id} on {issue_key} did not include a downloadable content URL."
            )

        try:
            raw = self._client.download_attachment(content_url)
        except JiraApiError as exc:
            error(
                "jira.get_attachment_image.download_failed",
                {"issue_key": issue.key, "attachment_id": attachment_id},
                exc=exc,
            )
            return self._internal_error(
                _api_error_message(f"downloading attachment {attachment_id} on {issue_key}", exc)
            )

        if len(raw) > self._settings.jira_attachment_max_bytes:
            return self._internal_error(
                f"Jira attachment {attachment_id} on {issue_key} exceeded the configured size limit."
            )

        mime_type = str(attachment.get("mimeType") or "")
        return {
            "success": True,
            "issue_key": issue.key,
            "attachment": {
                "attachment_id": attachment_id,
                "filename": str(attachment.get("filename") or ""),
                "mime_type": mime_type,
                "base64": base64.b64encode(raw).decode("ascii"),
            },
        }

    def start_issue(self, issue_key: str) -> dict[str, Any]:
        return self._transition_issue(
            issue_key=issue_key.strip(),
            target_status=self._settings.jira_start_target_status,
            success_topic="jira.start_issue.succeeded",
            operation_label="start",
        )

    def resolve_issue(self, issue_key: str) -> dict[str, Any]:
        return self._transition_issue(
            issue_key=issue_key.strip(),
            target_status=self._settings.jira_resolve_target_status,
            success_topic="jira.resolve_issue.succeeded",
            operation_label="resolve",
        )

    def _transition_issue(
        self,
        *,
        issue_key: str,
        target_status: str,
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
            return self._internal_error(_api_error_message(f"looking up {issue_key}", exc))

        if issue is None:
            return {
                "success": False,
                "error_type": "issue_not_found",
                "hint": jira_issue_not_found_hint(issue_key),
            }

        if not self._is_allowed_project(issue.key):
            return {
                "success": False,
                "error_type": "project_not_allowed",
                "hint": jira_project_not_allowed_hint(issue.key),
            }

        try:
            current_user_identifiers = self._client.get_current_user_identifiers()
        except JiraApiError as exc:
            error(success_topic.replace(".succeeded", ".assignee_check_failed"), {"issue_key": issue_key}, exc=exc)
            return self._internal_error(_api_error_message(f"checking assignee for {issue_key}", exc))

        if not issue.assignee.identifiers().intersection(current_user_identifiers):
            return {
                "success": False,
                "error_type": "assignee_not_allowed",
                "hint": jira_assignee_not_allowed_hint(issue.key),
            }

        try:
            transitions = self._client.get_transitions(issue_key)
        except JiraApiError as exc:
            error(success_topic.replace(".succeeded", ".transitions_failed"), {"issue_key": issue_key}, exc=exc)
            return self._internal_error(_api_error_message(f"fetching transitions for {issue_key}", exc))

        selected = self._find_transition_to_status(transitions, target_status)
        available_statuses = self._available_transition_statuses(transitions)
        if selected is None:
            return {
                "success": False,
                "error_type": "transition_not_available",
                "message": f"Could not {operation_label} {issue_key} because no available Jira transition reaches {target_status}.",
                "current_status": issue.status,
                "target_status": target_status,
                "available_statuses": available_statuses,
                "hint": JIRA_TRANSITION_FAILURE_HINT,
            }
        if isinstance(selected, list):
            matching_transition_names = [
                str(item.get("name") or "") for item in selected if str(item.get("name") or "").strip()
            ]
            return {
                "success": False,
                "error_type": "transition_ambiguous",
                "message": f"Could not {operation_label} {issue_key} because multiple available Jira transitions reach {target_status}.",
                "current_status": issue.status,
                "target_status": target_status,
                "available_statuses": available_statuses,
                "matching_transition_names": matching_transition_names,
                "hint": JIRA_TRANSITION_FAILURE_HINT,
            }

        transition_id = str(selected.get("id") or "")
        if not transition_id:
            return self._internal_error(
                f"Jira returned a transition without an id while trying to {operation_label} {issue_key}."
            )

        try:
            self._client.transition_issue(issue_key, transition_id)
        except JiraApiError as exc:
            error(
                success_topic.replace(".succeeded", ".transition_failed"),
                {"issue_key": issue_key, "transition_id": transition_id},
                exc=exc,
            )
            return self._internal_error(_api_error_message(f"{operation_label} {issue_key}", exc))

        return {"success": True, "issue_key": issue_key, "target_status": target_status}

    def _get_latest_assigned_issue(self) -> JiraIssue | None:
        issues = self._client.search_issues(
            jql=self._build_latest_assigned_issue_jql(),
            fields=JIRA_ISSUE_FIELDS,
            max_results=1,
        )
        if not issues:
            return None
        return JiraIssue.from_api(issues[0])

    def _get_issue_by_key(self, issue_key: str) -> JiraIssue | None:
        issue = self._client.get_issue(issue_key, fields=JIRA_ISSUE_FIELDS)
        if issue is None:
            return None
        return JiraIssue.from_api(issue)

    def _build_latest_assigned_issue_jql(self) -> str:
        if not self._settings.jira_project_key:
            raise RuntimeError(
                "Missing JIRA_PROJECT_KEY in environment or .env. Configure one Jira project key."
            )
        statuses = self._settings.jira_latest_assigned_statuses
        if not statuses:
            raise RuntimeError(
                "Missing jira.latest_assigned_statuses in config.yaml. Configure at least one Jira status."
            )
        statuses_clause = ", ".join(self._quote_jql_string(value) for value in statuses)
        return (
            f'project = "{self._settings.jira_project_key}" AND assignee = currentUser() '
            f"AND status in ({statuses_clause}) ORDER BY updated DESC"
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
        for attachment in issue.attachments:
            mime_type = str(attachment.get("mimeType") or "")
            if not mime_type.startswith("image/"):
                continue
            results.append(
                {
                    "attachment_id": str(attachment.get("id") or ""),
                    "filename": str(attachment.get("filename") or ""),
                    "mime_type": mime_type,
                    "size_bytes": int(attachment.get("size") or 0),
                }
            )
            if len(results) >= self._settings.jira_attachment_max_images:
                break
        return results

    @staticmethod
    def _quote_jql_string(value: str) -> str:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'

    @staticmethod
    def _find_image_attachment(issue: JiraIssue, attachment_id: str) -> dict[str, Any] | None:
        for attachment in issue.attachments:
            if str(attachment.get("id") or "").strip() != attachment_id:
                continue
            mime_type = str(attachment.get("mimeType") or "")
            if not mime_type.startswith("image/"):
                return None
            return attachment
        return None

    @classmethod
    def _find_transition_to_status(
        cls, transitions: list[dict[str, Any]], target_status: str
    ) -> dict[str, Any] | list[dict[str, Any]] | None:
        matches = [
            item
            for item in transitions
            if cls._transition_target_status(item).lower() == target_status.lower()
        ]
        if not matches:
            return None
        if len(matches) == 1:
            return matches[0]
        return matches

    @staticmethod
    def _transition_target_status(transition: dict[str, Any]) -> str:
        target = transition.get("to")
        if not isinstance(target, dict):
            return ""
        return str(target.get("name") or "").strip()

    @classmethod
    def _available_transition_statuses(cls, transitions: list[dict[str, Any]]) -> list[str]:
        seen: set[str] = set()
        statuses: list[str] = []
        for item in transitions:
            status = cls._transition_target_status(item)
            if not status:
                continue
            lowered = status.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            statuses.append(status)
        return statuses

    @staticmethod
    def _internal_error(message: str) -> dict[str, Any]:
        return {
            "success": False,
            "error_type": "internal_error",
            "message": message,
            "hint": INTERNAL_ERROR_RETRY_HINT,
        }
