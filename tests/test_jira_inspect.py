from __future__ import annotations

from work_mcp.tools.jira.inspect import build_transition_inspection


def test_build_transition_inspection_includes_status_categories_and_unique_targets() -> None:
    payload = build_transition_inspection(
        issue_key="IOS-123",
        issue={
            "key": "IOS-123",
            "fields": {
                "summary": "Crash on launch",
                "status": {
                    "name": "已接收",
                    "statusCategory": {"key": "indeterminate", "name": "In Progress"},
                },
            },
        },
        transitions=[
            {
                "id": "31",
                "name": "Resolve",
                "to": {
                    "name": "已解决",
                    "statusCategory": {"key": "done", "name": "Done"},
                },
            },
            {
                "id": "32",
                "name": "Fast Resolve",
                "to": {
                    "name": "已解决",
                    "statusCategory": {"key": "done", "name": "Done"},
                },
            },
            {
                "id": "33",
                "name": "Reopen",
                "to": {
                    "name": "处理中",
                    "statusCategory": {"key": "indeterminate", "name": "In Progress"},
                },
            },
        ],
        statuses=[
            {
                "name": "待处理",
                "statusCategory": {"key": "new", "name": "To Do"},
            },
            {
                "name": "已接收",
                "statusCategory": {"key": "indeterminate", "name": "In Progress"},
            },
            {
                "name": "已解决",
                "statusCategory": {"key": "done", "name": "Done"},
            },
        ],
        status_categories=[
            {"id": 2, "key": "new", "name": "To Do", "colorName": "blue-gray"},
            {"id": 4, "key": "indeterminate", "name": "In Progress", "colorName": "yellow"},
            {"id": 3, "key": "done", "name": "Done", "colorName": "green"},
        ],
    )

    assert payload == {
        "issue": {
            "key": "IOS-123",
            "summary": "Crash on launch",
            "current_status": {
                "name": "已接收",
                "status_category_key": "indeterminate",
                "status_category_name": "In Progress",
            },
        },
        "status_categories": [
            {
                "id": "2",
                "key": "new",
                "name": "To Do",
                "color_name": "blue-gray",
            },
            {
                "id": "4",
                "key": "indeterminate",
                "name": "In Progress",
                "color_name": "yellow",
            },
            {
                "id": "3",
                "key": "done",
                "name": "Done",
                "color_name": "green",
            },
        ],
        "statuses": [
            {
                "name": "待处理",
                "status_category_key": "new",
                "status_category_name": "To Do",
            },
            {
                "name": "已接收",
                "status_category_key": "indeterminate",
                "status_category_name": "In Progress",
            },
            {
                "name": "已解决",
                "status_category_key": "done",
                "status_category_name": "Done",
            },
        ],
        "available_target_statuses": ["已解决", "处理中"],
        "available_transitions": [
            {
                "transition_id": "31",
                "transition_name": "Resolve",
                "target_status": "已解决",
                "target_status_category_key": "done",
                "target_status_category_name": "Done",
            },
            {
                "transition_id": "32",
                "transition_name": "Fast Resolve",
                "target_status": "已解决",
                "target_status_category_key": "done",
                "target_status_category_name": "Done",
            },
            {
                "transition_id": "33",
                "transition_name": "Reopen",
                "target_status": "处理中",
                "target_status_category_key": "indeterminate",
                "target_status_category_name": "In Progress",
            },
        ],
    }
