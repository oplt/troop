"""Human-in-the-loop grants, escalations, and approval side effects."""

from backend.modules.orchestration.execution.hitl.approvals import ExecutionHitlApprovalsMixin
from backend.modules.orchestration.execution.hitl.grants import ExecutionHitlGrantsMixin


class ExecutionHitlMixin(ExecutionHitlGrantsMixin, ExecutionHitlApprovalsMixin):
    """HITL grant consumption and approval side effects."""
