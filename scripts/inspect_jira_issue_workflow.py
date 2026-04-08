from __future__ import annotations

import argparse
import json
import sys

from work_mcp.config import get_settings
from work_mcp.logger import configure as configure_logger
from work_mcp.tools.jira.client import JiraApiError, JiraClient
from work_mcp.tools.jira.inspect import build_transition_inspection


INSPECTION_FIELDS = ("summary", "status")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect one Jira issue's current status and currently available transitions. "
            "Use the returned target status names to fill jira.start_target_status or "
            "jira.resolve_target_status."
        )
    )
    parser.add_argument("issue_key", help="Jira issue key, for example IOS-123.")
    return parser.parse_args()


def main() -> None:
    try:
        args = _parse_args()
        settings = get_settings()
        configure_logger(log_dir=settings.log_dir, level=settings.log_level)

        client = JiraClient(settings)
        issue = client.get_issue(args.issue_key, fields=INSPECTION_FIELDS)
        if issue is None:
            raise RuntimeError(f"Jira issue not found: {args.issue_key}")

        status_categories = client.get_status_categories()
        statuses = client.get_statuses()
        transitions = client.get_transitions(args.issue_key)
        payload = build_transition_inspection(
            issue_key=str(issue.get("key") or args.issue_key),
            issue=issue,
            transitions=transitions,
            statuses=statuses,
            status_categories=status_categories,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    except JiraApiError as exc:
        print(f"inspect_jira_issue_workflow failed: JiraApiError: {exc.message}", file=sys.stderr)
        raise SystemExit(1) from exc
    except Exception as exc:
        print(f"inspect_jira_issue_workflow failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
