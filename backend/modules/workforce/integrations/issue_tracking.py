"""Provider-neutral issue tracker normalization and approval fingerprints."""

from __future__ import annotations

from typing import Any

from backend.modules.orchestration.tool_execution_context import arguments_hash


def _issue_ref(arguments: dict[str, Any]) -> tuple[str, str]:
    issue_id = str(arguments.get("issue_id") or "")
    issue_key = str(arguments.get("issue_key") or "")
    return issue_id, issue_key


def canonical_jira_issue_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    issue_id, issue_key = _issue_ref(arguments)
    return {
        "provider": "jira",
        "connector_installation_id": str(arguments.get("connector_installation_id") or ""),
        "cloud_id": str(arguments.get("cloud_id") or ""),
        "issue_id": issue_id,
        "issue_key": issue_key,
        "project_key": str(arguments.get("project_key") or ""),
        "issue_type": str(arguments.get("issue_type") or "Task"),
        "summary": str(arguments.get("summary") or ""),
        "description": str(arguments.get("description") or arguments.get("body") or ""),
        "comment_body": str(arguments.get("comment_body") or arguments.get("comment") or ""),
        "priority": str(arguments.get("priority") or ""),
        "assignee_account_id": str(arguments.get("assignee_account_id") or ""),
    }


def canonical_linear_issue_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    issue_id, issue_key = _issue_ref(arguments)
    return {
        "provider": "linear",
        "connector_installation_id": str(arguments.get("connector_installation_id") or ""),
        "team_id": str(arguments.get("team_id") or ""),
        "issue_id": issue_id or issue_key,
        "issue_key": issue_key,
        "title": str(arguments.get("title") or arguments.get("summary") or ""),
        "description": str(arguments.get("description") or arguments.get("body") or ""),
        "comment_body": str(arguments.get("comment_body") or arguments.get("comment") or ""),
        "state_id": str(arguments.get("state_id") or ""),
        "priority": str(arguments.get("priority") or ""),
        "assignee_id": str(arguments.get("assignee_id") or ""),
    }


def jira_issue_arguments_hash(arguments: dict[str, Any]) -> str:
    return arguments_hash(canonical_jira_issue_arguments(arguments))


def linear_issue_arguments_hash(arguments: dict[str, Any]) -> str:
    return arguments_hash(canonical_linear_issue_arguments(arguments))
