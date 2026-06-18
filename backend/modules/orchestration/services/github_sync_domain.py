"""GitHub App connections, webhooks, and task sync."""

from __future__ import annotations

from backend.modules.github.service import OrchestrationGithubServiceMixin
from backend.modules.orchestration.execution.execution_service import (
    OrchestrationExecutionServiceMixin,
)
from backend.modules.orchestration.services.base import OrchestrationServiceBase
from backend.modules.orchestration.services.routing_service import OrchestrationRoutingServiceMixin
from backend.modules.projects.service import OrchestrationProjectsServiceMixin
from backend.modules.projects.tasks_service import OrchestrationTasksServiceMixin


class GithubSyncService(
    OrchestrationServiceBase,
    OrchestrationGithubServiceMixin,
    OrchestrationProjectsServiceMixin,
    OrchestrationTasksServiceMixin,
    OrchestrationRoutingServiceMixin,
    OrchestrationExecutionServiceMixin,
):
    """GitHub repository linking, webhook processing, and sync replay."""
