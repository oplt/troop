"""Collapsed execution capability stack (single inheritance node).

Domain services compose ``OrchestrationRunQueryMixin`` + ``OrchestrationServiceBase`` with
``ExecutionCapabilitiesMixin`` instead of listing nine separate mixins in the MRO.  Behavior is
unchanged; this is the first step toward port-based composition (P4.4).
"""

from __future__ import annotations

from backend.modules.github.service import OrchestrationGithubServiceMixin
from backend.modules.memory.service import OrchestrationMemoryServiceMixin
from backend.modules.orchestration.execution.execution_service import (
    OrchestrationExecutionServiceMixin,
)
from backend.modules.orchestration.services.approvals_service import (
    OrchestrationApprovalsServiceMixin,
)
from backend.modules.orchestration.services.providers_service import (
    OrchestrationProvidersServiceMixin,
)
from backend.modules.orchestration.services.routing_service import OrchestrationRoutingServiceMixin
from backend.modules.projects.service import OrchestrationProjectsServiceMixin
from backend.modules.projects.tasks_service import OrchestrationTasksServiceMixin
from backend.modules.team.service import TeamServiceMixin


class ExecutionCapabilitiesMixin(
    OrchestrationExecutionServiceMixin,
    OrchestrationApprovalsServiceMixin,
    OrchestrationRoutingServiceMixin,
    OrchestrationProvidersServiceMixin,
    OrchestrationGithubServiceMixin,
    OrchestrationMemoryServiceMixin,
    OrchestrationTasksServiceMixin,
    OrchestrationProjectsServiceMixin,
    TeamServiceMixin,
):
    """Run execution, routing, providers, memory, tasks, projects, and team helpers."""
