from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.logging import get_logger
from backend.modules.orchestration.services.approvals_domain import ApprovalsService
from backend.modules.orchestration.services.base import (
    GITHUB_WEBHOOK_EVENT_ALLOWLIST,
    SEMANTIC_ENTRY_TYPES,
    TASK_TRANSITIONS,
    OrchestrationRunQueryMixin,
    OrchestrationServiceBase,
)
from backend.modules.orchestration.services.brainstorm_domain import BrainstormService
from backend.modules.orchestration.services.evals_domain import EvalsService
from backend.modules.orchestration.services.execution_domain import ExecutionService
from backend.modules.orchestration.services.github_sync_domain import GithubSyncService
from backend.modules.orchestration.services.knowledge_domain import KnowledgeService
from backend.modules.orchestration.services.memory_domain import MemoryService
from backend.modules.projects.service import OrchestrationProjectsServiceMixin
from backend.modules.projects.tasks_service import OrchestrationTasksServiceMixin
from backend.modules.team.service import TeamServiceMixin

logger = get_logger(__name__)

__all__ = [
    "ApprovalsService",
    "BrainstormService",
    "EvalsService",
    "ExecutionService",
    "GithubSyncService",
    "KnowledgeService",
    "MemoryService",
    "OrchestrationService",
    "GITHUB_WEBHOOK_EVENT_ALLOWLIST",
    "SEMANTIC_ENTRY_TYPES",
    "TASK_TRANSITIONS",
]

_DOMAIN_SERVICES = ("approvals", "execution", "memory", "github_sync", "evals", "brainstorm")


class OrchestrationService(
    OrchestrationRunQueryMixin,
    OrchestrationProjectsServiceMixin,
    OrchestrationTasksServiceMixin,
    TeamServiceMixin,
    OrchestrationServiceBase,
):
    """Facade composing domain services; evals/brainstorm stay on the shell."""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db)
        self.approvals = ApprovalsService(db)
        self.execution = ExecutionService(db)
        self.memory = MemoryService(db)
        self.github_sync = GithubSyncService(db)
        self.evals = EvalsService(db)
        self.brainstorm = BrainstormService(db)
        self._knowledge_facade = KnowledgeService(self.memory)

    @property
    def knowledge(self) -> KnowledgeService:
        return self._knowledge_facade

    def __getattr__(self, name: str):
        for attr in _DOMAIN_SERVICES:
            domain = object.__getattribute__(self, attr)
            if hasattr(domain, name):
                value = getattr(domain, name)
                if callable(value):
                    return value.__get__(domain, type(domain))
                return value
        raise AttributeError(f"{type(self).__name__!r} object has no attribute {name!r}")
