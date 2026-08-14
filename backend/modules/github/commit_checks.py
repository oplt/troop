"""GitHub commit-time precondition helpers."""

from __future__ import annotations

from backend.modules.github.models import GithubIssueLink
from backend.modules.orchestration.tool_execution_context import arguments_hash


def github_issue_precondition_fingerprint(issue_link: GithubIssueLink) -> str:
    """Fingerprint issue linkage state bound at approval time."""
    synced_at = issue_link.last_synced_at.isoformat() if issue_link.last_synced_at else None
    return arguments_hash(
        {
            "issue_link_id": issue_link.id,
            "repository_id": issue_link.repository_id,
            "issue_number": issue_link.issue_number,
            "state": issue_link.state,
            "last_synced_at": synced_at,
        }
    )
