"""Manager-worker execution composition."""

from backend.modules.orchestration.execution.manager_worker.dispatcher import (
    ManagerWorkerDispatcherMixin,
)
from backend.modules.orchestration.execution.manager_worker.planner import ManagerWorkerPlannerMixin
from backend.modules.orchestration.execution.manager_worker.review import ManagerWorkerReviewMixin
from backend.modules.orchestration.execution.manager_worker.single_agent import (
    ManagerWorkerSingleAgentMixin,
)


class ExecutionManagerWorkerMixin(
    ManagerWorkerPlannerMixin,
    ManagerWorkerSingleAgentMixin,
    ManagerWorkerDispatcherMixin,
    ManagerWorkerReviewMixin,
):
    """Single-agent, manager-worker, and review run execution paths."""
