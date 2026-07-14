"""FastAPI dependencies for orchestration domain services."""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.session import get_db
from backend.modules.orchestration.services.application import OrchestrationApplicationService
from backend.modules.orchestration.services.approvals_domain import ApprovalsService
from backend.modules.orchestration.services.execution_domain import ExecutionService
from backend.modules.orchestration.services.github_sync_domain import GithubSyncService
from backend.modules.orchestration.services.knowledge_domain import KnowledgeService
from backend.modules.orchestration.services.memory_domain import MemoryService
from backend.modules.orchestration.services.service import OrchestrationService


def get_orchestration_service(db: AsyncSession = Depends(get_db)) -> OrchestrationService:
    return OrchestrationService(db)


def get_orchestration_application_service(
    db: AsyncSession = Depends(get_db),
) -> OrchestrationApplicationService:
    return OrchestrationApplicationService(db)


def get_approvals_service(db: AsyncSession = Depends(get_db)) -> ApprovalsService:
    return ApprovalsService(db)


def get_execution_service(db: AsyncSession = Depends(get_db)) -> ExecutionService:
    return ExecutionService(db)


def get_memory_service(db: AsyncSession = Depends(get_db)) -> MemoryService:
    return MemoryService(db)


def get_knowledge_service(db: AsyncSession = Depends(get_db)) -> KnowledgeService:
    return KnowledgeService(MemoryService(db))


def get_github_sync_service(db: AsyncSession = Depends(get_db)) -> GithubSyncService:
    return GithubSyncService(db)
