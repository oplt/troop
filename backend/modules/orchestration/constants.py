"""Shared orchestration constants — single source for task rules and webhook allowlists."""

from __future__ import annotations

from backend.modules.workforce.constants import (
    LEGACY_STATUS_ALIASES,
    TASK_TRANSITIONS,
)

__all__ = ["TASK_TRANSITIONS", "LEGACY_STATUS_ALIASES", "GITHUB_WEBHOOK_EVENT_ALLOWLIST"]

GITHUB_WEBHOOK_EVENT_ALLOWLIST = frozenset(
    {
        "installation",
        "installation_repositories",
        "issues",
        "issue_comment",
        "pull_request",
        "pull_request_review",
        "pull_request_review_comment",
        "push",
        "projects_v2_item",
    }
)
