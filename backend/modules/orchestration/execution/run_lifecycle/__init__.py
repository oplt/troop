"""Run lifecycle composition."""

from backend.modules.orchestration.execution.run_lifecycle.budget import ExecutionRunBudgetMixin
from backend.modules.orchestration.execution.run_lifecycle.commands import ExecutionRunCommandsMixin
from backend.modules.orchestration.execution.run_lifecycle.events import ExecutionRunEventsMixin
from backend.modules.orchestration.execution.run_lifecycle.execution import (
    ExecutionRunExecutionMixin,
)
from backend.modules.orchestration.execution.run_lifecycle.workflow import ExecutionRunWorkflowMixin


class ExecutionRunLifecycleMixin(
    ExecutionRunWorkflowMixin,
    ExecutionRunBudgetMixin,
    ExecutionRunCommandsMixin,
    ExecutionRunExecutionMixin,
    ExecutionRunEventsMixin,
):
    """Start, execute, cancel, resume, retry, and workflow checkpointing."""
