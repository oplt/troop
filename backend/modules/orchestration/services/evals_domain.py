"""Evaluation and benchmark orchestration boundary."""

from __future__ import annotations

from backend.modules.github.service import OrchestrationGithubServiceMixin
from backend.modules.orchestration.execution.execution_service import (
    OrchestrationExecutionServiceMixin,
)
from backend.modules.orchestration.services.base import (
    OrchestrationRunQueryMixin,
    OrchestrationServiceBase,
)
from backend.modules.orchestration.services.evals_service import OrchestrationEvalsServiceMixin
from backend.modules.orchestration.services.providers_service import (
    OrchestrationProvidersServiceMixin,
)
from backend.modules.projects.service import OrchestrationProjectsServiceMixin
from backend.modules.projects.tasks_service import OrchestrationTasksServiceMixin
from backend.modules.team.service import TeamServiceMixin


class EvalsService(
    OrchestrationRunQueryMixin,
    OrchestrationServiceBase,
    OrchestrationEvalsServiceMixin,
    OrchestrationExecutionServiceMixin,
    OrchestrationProvidersServiceMixin,
    OrchestrationGithubServiceMixin,
    OrchestrationProjectsServiceMixin,
    OrchestrationTasksServiceMixin,
    TeamServiceMixin,
):
    """Benchmarks, PR assistant review, schedules, and workflow templates."""
