"""Human approval workflows and gated action decisions."""

from __future__ import annotations

from backend.modules.github.service import OrchestrationGithubServiceMixin
from backend.modules.memory.service import OrchestrationMemoryServiceMixin
from backend.modules.orchestration.execution.execution_service import (
    OrchestrationExecutionServiceMixin,
)
from backend.modules.orchestration.services.approvals_service import (
    OrchestrationApprovalsServiceMixin,
)
from backend.modules.orchestration.services.base import (
    OrchestrationRunQueryMixin,
    OrchestrationServiceBase,
)
from backend.modules.orchestration.services.routing_service import OrchestrationRoutingServiceMixin
from backend.modules.projects.service import OrchestrationProjectsServiceMixin
from backend.modules.projects.tasks_service import OrchestrationTasksServiceMixin
from backend.modules.team.service import TeamServiceMixin


class ApprovalsService(
    OrchestrationRunQueryMixin,
    OrchestrationServiceBase,
    OrchestrationApprovalsServiceMixin,
    OrchestrationExecutionServiceMixin,
    OrchestrationGithubServiceMixin,
    OrchestrationMemoryServiceMixin,
    OrchestrationProjectsServiceMixin,
    OrchestrationTasksServiceMixin,
    OrchestrationRoutingServiceMixin,
    TeamServiceMixin,
):
    """Approval listing, approval decisions, and gated-action side effects."""
