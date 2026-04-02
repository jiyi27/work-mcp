from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class JiraIssue:
    key: str
    summary: str
    description: str
    status: str
    issue_type: str
    priority: str
    updated: str
    attachments: tuple[dict[str, Any], ...]

    @classmethod
    def from_api(cls, raw_issue: dict[str, Any]) -> "JiraIssue":
        fields = raw_issue.get("fields", {})
        status = fields.get("status") or {}
        issue_type = fields.get("issuetype") or {}
        priority = fields.get("priority") or {}
        attachments = fields.get("attachment") or []
        return cls(
            key=str(raw_issue.get("key", "")),
            summary=str(fields.get("summary") or ""),
            description=str(fields.get("description") or ""),
            status=str(status.get("name") or ""),
            issue_type=str(issue_type.get("name") or ""),
            priority=str(priority.get("name") or ""),
            updated=str(fields.get("updated") or ""),
            attachments=tuple(
                item for item in attachments if isinstance(item, dict)
            ),
        )
