from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class JiraUser:
    account_id: str
    key: str
    username: str
    email: str

    @classmethod
    def from_api(cls, raw_user: Any) -> "JiraUser":
        if not isinstance(raw_user, dict):
            return cls(account_id="", key="", username="", email="")
        return cls(
            account_id=str(raw_user.get("accountId") or ""),
            key=str(raw_user.get("key") or ""),
            username=str(raw_user.get("name") or ""),
            email=str(raw_user.get("emailAddress") or ""),
        )

    def identifiers(self) -> frozenset[str]:
        values = (self.account_id, self.key, self.username, self.email)
        return frozenset(value.strip().lower() for value in values if value and value.strip())


@dataclass(frozen=True)
class JiraIssue:
    key: str
    summary: str
    description: str
    status: str
    issue_type: str
    priority: str
    updated: str
    assignee: JiraUser
    attachments: tuple[dict[str, Any], ...]

    @classmethod
    def from_api(cls, raw_issue: dict[str, Any]) -> "JiraIssue":
        fields = raw_issue.get("fields", {})
        status = fields.get("status") or {}
        issue_type = fields.get("issuetype") or {}
        priority = fields.get("priority") or {}
        assignee = JiraUser.from_api(fields.get("assignee"))
        attachments = fields.get("attachment") or []
        return cls(
            key=str(raw_issue.get("key", "")),
            summary=str(fields.get("summary") or ""),
            description=str(fields.get("description") or ""),
            status=str(status.get("name") or ""),
            issue_type=str(issue_type.get("name") or ""),
            priority=str(priority.get("name") or ""),
            updated=str(fields.get("updated") or ""),
            assignee=assignee,
            attachments=tuple(
                item for item in attachments if isinstance(item, dict)
            ),
        )
