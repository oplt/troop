from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.ai.providers import AiProviderRegistry
from backend.modules.audit.repository import AuditRepository
from backend.modules.github.service import OrchestrationGithubServiceMixin
from backend.modules.memory.service import OrchestrationMemoryServiceMixin
from backend.modules.orchestration.execution.execution_service import (
    OrchestrationExecutionServiceMixin,
)
from backend.modules.orchestration.repository import OrchestrationRepository
from backend.modules.orchestration.services.approvals_service import (
    OrchestrationApprovalsServiceMixin,
)
from backend.modules.orchestration.services.brainstorm_service import (
    OrchestrationBrainstormServiceMixin,
)
from backend.modules.orchestration.services.evals_service import OrchestrationEvalsServiceMixin
from backend.modules.orchestration.services.providers_service import (
    OrchestrationProvidersServiceMixin,
)
from backend.modules.orchestration.services.routing_service import OrchestrationRoutingServiceMixin
from backend.modules.projects.service import OrchestrationProjectsServiceMixin
from backend.modules.projects.tasks_service import OrchestrationTasksServiceMixin
from backend.modules.team.service import TeamServiceMixin

logger = logging.getLogger(__name__)


TASK_TRANSITIONS: dict[str, set[str]] = {
    "backlog": {"queued", "archived"},
    "queued": {"planned", "blocked", "failed", "archived"},
    "planned": {"in_progress", "blocked", "archived", "failed"},
    "in_progress": {"blocked", "needs_review", "completed", "failed", "planned"},
    "blocked": {"planned", "in_progress", "failed", "archived"},
    "needs_review": {"approved", "planned", "blocked", "failed"},
    "approved": {"completed", "planned", "archived"},
    "completed": {"synced_to_github", "planned", "archived"},
    "failed": {"planned", "queued", "archived"},
    "synced_to_github": {"archived", "planned"},
    "archived": set(),
}

from backend.modules.memory.entry_types import (
    SEMANTIC_ENTRY_TYPES as _CANONICAL_SEMANTIC_ENTRY_TYPES,
)

SEMANTIC_ENTRY_TYPES = frozenset(_CANONICAL_SEMANTIC_ENTRY_TYPES)

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


class OrchestrationService(
    OrchestrationEvalsServiceMixin,
    OrchestrationApprovalsServiceMixin,
    OrchestrationGithubServiceMixin,
    OrchestrationMemoryServiceMixin,
    OrchestrationBrainstormServiceMixin,
    OrchestrationProvidersServiceMixin,
    OrchestrationRoutingServiceMixin,
    OrchestrationExecutionServiceMixin,
    OrchestrationTasksServiceMixin,
    OrchestrationProjectsServiceMixin,
    TeamServiceMixin,
):
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = OrchestrationRepository(db)
        self.audit_repo = AuditRepository(db)
        self.ai_providers = AiProviderRegistry()


    _TOOL_MIN_PERMISSION: dict[str, str] = {
        "fs_read": "read-only",
        "repo_search": "read-only",
        "web_fetch": "read-only",
        "web_search": "read-only",
        "github_comment": "comment-only",
        "github_label_issue": "code-write",
        "github_create_pr": "code-write",
        "fs_write": "code-write",
        "code_execute": "code-write",
        "db_query": "code-write",
    }
    _PERMISSION_RANK: dict[str, int] = {"read-only": 1, "comment-only": 2, "code-write": 3, "merge-blocked": 3}
    _MERGE_BLOCKED_TOOLS: frozenset[str] = frozenset({"github_create_pr", "github_label_issue"})
