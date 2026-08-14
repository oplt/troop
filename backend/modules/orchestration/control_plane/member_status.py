"""Member status derivation."""

from __future__ import annotations

from backend.modules.orchestration.models import (
    AgentProfile,
    ApprovalRequest,
    OrchestratorTask,
    TaskRun,
)


class ControlPlaneMemberStatusMixin:
    def _derive_member_status(
        self,
        agent: AgentProfile,
        runs: list[TaskRun],
        tasks: list[OrchestratorTask],
        approvals: list[ApprovalRequest],
    ) -> str:
        if not agent.is_active:
            return "disabled"
        if any(run.status == "blocked" for run in runs):
            return "blocked"
        if any(task.status == "needs_review" for task in tasks) or approvals:
            return "needs_review"
        if any(run.status == "in_progress" for run in runs):
            return "running"
        if any(run.status == "queued" for run in runs):
            return "queued"
        return "idle"
