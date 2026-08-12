"""Workforce constants: generic task lifecycle + legacy status aliases."""

from __future__ import annotations

# Target generic statuses (prompt §4). Legacy GitHub statuses remain readable.
GENERIC_TASK_STATUSES = frozenset(
    {
        "backlog",
        "ready",
        "planned",
        "in_progress",
        "needs_input",
        "blocked",
        "needs_review",
        "needs_approval",
        "completed",
        "archived",
        "cancelled",
    }
)

# Map legacy persisted statuses → generic equivalents for display/API.
LEGACY_STATUS_ALIASES: dict[str, str] = {
    "queued": "ready",
    "approved": "needs_approval",  # historical: approved meant ready to complete
    "failed": "blocked",
    "synced_to_github": "completed",  # GitHub sync is now an event/artifact, not a status
    "todo": "ready",
    "done": "completed",
    "review": "needs_review",
}

# Extended transitions: keep old keys for backward compatibility + add generic ones.
TASK_TRANSITIONS: dict[str, set[str]] = {
    "backlog": {"ready", "queued", "planned", "archived", "cancelled"},
    "ready": {"planned", "in_progress", "blocked", "archived", "cancelled"},
    "queued": {"ready", "planned", "blocked", "failed", "archived", "cancelled"},
    "planned": {"in_progress", "blocked", "archived", "failed", "cancelled", "needs_input"},
    "in_progress": {
        "blocked",
        "needs_input",
        "needs_review",
        "needs_approval",
        "completed",
        "failed",
        "planned",
        "cancelled",
    },
    "needs_input": {"in_progress", "planned", "blocked", "cancelled", "archived"},
    "blocked": {"planned", "in_progress", "ready", "failed", "archived", "cancelled"},
    "needs_review": {
        "needs_approval",
        "approved",
        "planned",
        "blocked",
        "failed",
        "in_progress",
        "cancelled",
    },
    "needs_approval": {"completed", "approved", "planned", "blocked", "cancelled"},
    "approved": {"completed", "planned", "archived", "needs_approval"},
    "completed": {"synced_to_github", "planned", "archived", "cancelled"},
    "failed": {"planned", "queued", "ready", "archived", "cancelled"},
    "synced_to_github": {"archived", "planned", "completed"},
    "cancelled": {"backlog", "archived"},
    "archived": set(),
}

SKILL_SCOPES = frozenset({"task", "project", "organization", "template", "global"})
SKILL_STATUSES = frozenset({"draft", "testing", "active", "deprecated", "archived"})
SKILL_DRAFT_SOURCES = frozenset(
    {
        "manual",
        "markdown_import",
        "task_generation",
        "project_generation",
        "agent_recommendation",
        "skill_clone",
        "improvement",
    }
)

ANALYZER_VERSION = "1.0.0"

# Native tools registered into ToolDefinition on seed.
NATIVE_TOOL_CATALOG: list[dict] = [
    {
        "slug": "web_search",
        "name": "Web Search",
        "description": "Search the public web",
        "risk_level": "low",
        "requires_approval": False,
    },
    {
        "slug": "web_fetch",
        "name": "Web Fetch",
        "description": "Fetch a URL",
        "risk_level": "low",
        "requires_approval": False,
    },
    {
        "slug": "knowledge_search",
        "name": "Knowledge Search",
        "description": "Search project/org knowledge",
        "risk_level": "low",
        "requires_approval": False,
    },
    {
        "slug": "repo_search",
        "name": "Repository Search",
        "description": "Search linked repositories",
        "risk_level": "low",
        "requires_approval": False,
    },
    {
        "slug": "fs_read",
        "name": "Filesystem Read",
        "description": "Read files in workspace",
        "risk_level": "low",
        "requires_approval": False,
    },
    {
        "slug": "fs_write",
        "name": "Filesystem Write",
        "description": "Write files in workspace",
        "risk_level": "high",
        "requires_approval": True,
    },
    {
        "slug": "code_execute",
        "name": "Code Execute",
        "description": "Execute code in sandbox",
        "risk_level": "high",
        "requires_approval": True,
    },
    {
        "slug": "db_query",
        "name": "Database Query",
        "description": "Run read/write DB queries",
        "risk_level": "critical",
        "requires_approval": True,
    },
    {
        "slug": "github_comment",
        "name": "GitHub Comment",
        "description": "Comment on GitHub issues/PRs",
        "risk_level": "medium",
        "requires_approval": True,
        "provider_type": "github",
    },
    {
        "slug": "github_label_issue",
        "name": "GitHub Label Issue",
        "description": "Add/remove GitHub issue labels",
        "risk_level": "medium",
        "requires_approval": True,
        "provider_type": "github",
    },
    {
        "slug": "github_create_pr",
        "name": "GitHub Create PR",
        "description": "Open a pull request",
        "risk_level": "high",
        "requires_approval": True,
        "provider_type": "github",
    },
]

DEFAULT_ACTION_POLICIES: list[dict] = [
    {"action_key": "web_search", "decision": "autonomous", "risk_level": "low"},
    {"action_key": "knowledge_read", "decision": "autonomous", "risk_level": "low"},
    {"action_key": "external_email_send", "decision": "approval_required", "risk_level": "high"},
    {"action_key": "social_publish", "decision": "approval_required", "risk_level": "high"},
    {"action_key": "ad_budget_change", "decision": "approval_required", "risk_level": "critical"},
    {"action_key": "delete_record", "decision": "approval_required", "risk_level": "critical"},
    {"action_key": "merge_pull_request", "decision": "approval_required", "risk_level": "high"},
    {
        "action_key": "shell_destructive_action",
        "decision": "prohibited",
        "risk_level": "critical",
    },
]
