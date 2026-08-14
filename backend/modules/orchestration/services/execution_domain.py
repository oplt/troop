"""Run lifecycle, approvals, routing, and provider orchestration."""

from __future__ import annotations

from backend.modules.orchestration.services.base import (
    OrchestrationRunQueryMixin,
    OrchestrationServiceBase,
)
from backend.modules.orchestration.services.execution_backend import ExecutionCapabilitiesMixin


class ExecutionService(
    OrchestrationRunQueryMixin,
    OrchestrationServiceBase,
    ExecutionCapabilitiesMixin,
):
    """Run execution, task transitions, agent routing, and approval gates."""
