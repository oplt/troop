"""Brainstorm lifecycle and discourse analysis boundary."""

from __future__ import annotations

from backend.modules.github.service import OrchestrationGithubServiceMixin
from backend.modules.orchestration.execution.execution_service import (
    OrchestrationExecutionServiceMixin,
)
from backend.modules.orchestration.services.base import (
    OrchestrationRunQueryMixin,
    OrchestrationServiceBase,
)
from backend.modules.orchestration.services.brainstorm_service import (
    OrchestrationBrainstormServiceMixin,
)
from backend.modules.orchestration.services.routing_service import OrchestrationRoutingServiceMixin
from backend.modules.projects.service import OrchestrationProjectsServiceMixin
from backend.modules.projects.tasks_service import OrchestrationTasksServiceMixin
from backend.modules.team.service import TeamServiceMixin


class BrainstormService(
    OrchestrationRunQueryMixin,
    OrchestrationServiceBase,
    OrchestrationBrainstormServiceMixin,
    OrchestrationExecutionServiceMixin,
    OrchestrationGithubServiceMixin,
    OrchestrationProjectsServiceMixin,
    OrchestrationTasksServiceMixin,
    OrchestrationRoutingServiceMixin,
    TeamServiceMixin,
):
    """Brainstorm creation, execution startup, and consensus telemetry."""
