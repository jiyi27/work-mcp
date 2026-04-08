from __future__ import annotations

from typing import Any


def build_transition_inspection(
    *,
    issue_key: str,
    issue: dict[str, Any],
    transitions: list[dict[str, Any]],
    statuses: list[dict[str, Any]] | None = None,
    status_categories: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    fields = issue.get("fields")
    if not isinstance(fields, dict):
        fields = {}

    status = fields.get("status")
    if not isinstance(status, dict):
        status = {}

    current_status = _serialize_status(status)
    available_transitions = [_serialize_transition(item) for item in transitions]
    available_target_statuses = _dedupe_preserving_order(
        item["target_status"]
        for item in available_transitions
        if item["target_status"]
    )

    return {
        "issue": {
            "key": issue_key,
            "summary": str(fields.get("summary") or ""),
            "current_status": current_status,
        },
        "status_categories": [
            _serialize_status_category(item) for item in (status_categories or [])
        ],
        "statuses": [_serialize_status(item) for item in (statuses or [])],
        "available_target_statuses": available_target_statuses,
        "available_transitions": available_transitions,
    }


def _serialize_transition(transition: dict[str, Any]) -> dict[str, str]:
    target = transition.get("to")
    if not isinstance(target, dict):
        target = {}

    serialized_target = _serialize_status(target)
    return {
        "transition_id": str(transition.get("id") or "").strip(),
        "transition_name": str(transition.get("name") or "").strip(),
        "target_status": serialized_target["name"],
        "target_status_category_key": serialized_target["status_category_key"],
        "target_status_category_name": serialized_target["status_category_name"],
    }


def _serialize_status(status: dict[str, Any]) -> dict[str, str]:
    category = status.get("statusCategory")
    if not isinstance(category, dict):
        category = {}

    return {
        "name": str(status.get("name") or "").strip(),
        "status_category_key": str(category.get("key") or "").strip(),
        "status_category_name": str(category.get("name") or "").strip(),
    }


def _serialize_status_category(category: dict[str, Any]) -> dict[str, str]:
    return {
        "id": str(category.get("id") or "").strip(),
        "key": str(category.get("key") or "").strip(),
        "name": str(category.get("name") or "").strip(),
        "color_name": str(category.get("colorName") or "").strip(),
    }


def _dedupe_preserving_order(values: Any) -> list[str]:
    seen: set[str] = set()
    results: list[str] = []
    for raw in values:
        value = str(raw).strip()
        if not value:
            continue
        lowered = value.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        results.append(value)
    return results
