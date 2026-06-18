"""Semantic, episodic, and working memory orchestration."""

from __future__ import annotations

from backend.modules.memory.service import OrchestrationMemoryServiceMixin
from backend.modules.orchestration.services.base import (
    OrchestrationRunQueryMixin,
    OrchestrationServiceBase,
)
from backend.modules.projects.service import OrchestrationProjectsServiceMixin
from backend.modules.projects.tasks_service import OrchestrationTasksServiceMixin


class MemoryService(
    OrchestrationRunQueryMixin,
    OrchestrationServiceBase,
    OrchestrationMemoryServiceMixin,
    OrchestrationProjectsServiceMixin,
    OrchestrationTasksServiceMixin,
):
    """Project memory settings, semantic/episodic stores, and ingest workers."""
