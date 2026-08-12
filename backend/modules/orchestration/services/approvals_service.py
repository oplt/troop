from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException

from backend.core.logging import get_logger
from backend.modules.identity_access.models import User
from backend.modules.memory.coordination import (
    MEMORY_COORDINATION_KEY,
)
from backend.modules.memory.metrics import increment_memory_metric
from backend.modules.orchestration.hitl_policy import (
    action_requires_approval as hitl_action_requires_approval,
)
from backend.modules.orchestration.models import (
    TaskRun,
)
from backend.modules.projects.orchestration_models import (
    OrchestratorProject,
    OrchestratorTask,
)

logger = get_logger(__name__)

from backend.modules.memory.entry_types import (
    SEMANTIC_ENTRY_TYPES as _CANONICAL_SEMANTIC_ENTRY_TYPES,
)

SEMANTIC_ENTRY_TYPES = frozenset(_CANONICAL_SEMANTIC_ENTRY_TYPES)


class OrchestrationApprovalsServiceMixin:
    async def list_approvals(self, user: User):
        return await self.repo.list_approvals(user.id)

    async def decide_approval(self, user: User, approval_id: str, status: str, reason: str | None):
        approval = await self.repo.get_approval(user.id, approval_id)
        if not approval:
            raise HTTPException(status_code=404, detail="Approval request not found")
        if approval.status != "pending":
            raise HTTPException(
                status_code=409,
                detail=f"Approval request is already {approval.status} and cannot be decided again.",
            )
        if status == "rejected" and not str(reason or "").strip():
            raise HTTPException(status_code=422, detail="A rejection reason is required.")
        approval.status = status
        approval.reason = reason
        approval.approved_by_user_id = user.id
        approval.resolved_at = datetime.now(UTC)
        if status == "approved" and approval.approval_type in {
            "github_comment",
            "github_progress_comment",
            "github_manager_closure",
        } and approval.issue_link_id:
            await self._post_approved_github_comment(approval)
        elif status == "approved" and approval.approval_type == "github_create_pr":
            await self._approve_github_create_pr(approval)
        elif status == "approved" and approval.approval_type == "github_pr_review_comment":
            await self._approve_github_pr_review_comment(approval)
        elif status == "approved" and approval.approval_type == "github_issue_sync":
            await self._approve_github_issue_sync(approval)
        elif approval.approval_type == "agent_memory_write":
            memory_entry_id = (approval.payload_json or {}).get("memory_entry_id")
            if memory_entry_id:
                memory = await self.repo.get_agent_memory(user.id, memory_entry_id)
                if memory:
                    if status == "approved":
                        memory.status = "approved"
                        memory.approved_by_user_id = user.id
                        if memory.project_id:
                            proj = await self.db.get(OrchestratorProject, memory.project_id)
                            if proj:
                                await self._maybe_promote_agent_memory_to_semantic(user, proj, memory)
                    else:
                        memory.status = "rejected"
                        memory.deleted_at = datetime.now(UTC)
        elif approval.approval_type == "semantic_memory_write":
            payload = approval.payload_json or {}
            op = payload.get("operation")
            req_user_id = approval.requested_by_user_id or user.id
            req_user = await self.db.get(User, req_user_id) or user
            if approval.project_id and status == "approved":
                project = await self.get_project(req_user, approval.project_id)
                if op == "create":
                    await self._persist_semantic_memory_row(
                        req_user, project, dict(payload.get("payload") or {})
                    )
                elif op == "update":
                    entry_id = str(payload.get("entry_id") or "")
                    updates = dict(payload.get("updates") or {})
                    entry = await self.get_semantic_memory_entry_for_project(
                        req_user, approval.project_id, entry_id
                    )
                    await self._apply_semantic_entry_updates(entry, updates)
                    await self.db.commit()
                    await self.db.refresh(entry)
                    self._schedule_semantic_embedding(entry.id)
                elif op == "delete":
                    entry_id = str(payload.get("entry_id") or "")
                    entry = await self.get_semantic_memory_entry_for_project(
                        req_user, approval.project_id, entry_id
                    )
                    await self.db.delete(entry)
                    await self.db.commit()
            if bool((approval.payload_json or {}).get("promotion_suggested")):
                if status == "approved":
                    increment_memory_metric("promotion_semantic_approval_accepted")
                elif status == "rejected":
                    increment_memory_metric("promotion_semantic_approval_rejected")
        elif approval.approval_type == "task_assignment_change":
            if status == "approved" and approval.task_id:
                task = await self.db.get(OrchestratorTask, approval.task_id)
                if task:
                    payload = approval.payload_json or {}
                    task.assigned_agent_id = payload.get("to_assigned_agent_id")
        elif approval.approval_type == "task_mark_complete":
            if status == "approved" and approval.task_id:
                task = await self.db.get(OrchestratorTask, approval.task_id)
                if task:
                    payload = approval.payload_json or {}
                    target_status = str(payload.get("to_status") or "completed")
                    if target_status not in TASK_STATUS_VALUES:
                        target_status = "completed"
                    await self._transition_task_status(
                        task,
                        target_status,
                        reason="approval granted for task completion",
                    )
        elif approval.approval_type == "shared_memory_write":
            if status == "approved" and approval.task_id:
                task = await self.db.get(OrchestratorTask, approval.task_id)
                if task:
                    payload = approval.payload_json or {}
                    meta = dict(task.metadata_json or {})
                    cur = dict(meta.get(MEMORY_COORDINATION_KEY) or {})
                    cur["shared"] = str(payload.get("shared") or "")
                    meta[MEMORY_COORDINATION_KEY] = cur
                    task.metadata_json = meta
        elif status == "approved" and approval.run_id:
            # The common resume path below handles the durable queue transition.
            # Keep this branch explicit so approval types without a side effect still
            # receive the same worker resume behavior.
            pass
        elif status == "rejected" and approval.task_id:
            task = await self.db.get(OrchestratorTask, approval.task_id)
            if task and task.status in {"approved", "completed"}:
                await self._transition_task_status(
                    task,
                    "planned",
                    reason="approval rejected, reopening work",
                )
            # Rejected approvals trigger re-plan
            if approval.run_id:
                run = await self.db.get(TaskRun, approval.run_id)
                if run and run.status not in {"completed", "failed", "cancelled"}:
                    run.status = "failed"
                    run.error_message = f"Approval rejected: {reason or 'No reason provided'}"
                    await self._emit_run_event(
                        run,
                        event_type="approval_rejected",
                        level="warning",
                        message=f"Run marked as failed due to rejected approval: {reason or 'No reason provided'}",
                        payload={"approval_id": approval.id, "reason": reason},
                    )
                    if task:
                        await self._transition_task_status(
                            task,
                            "planned",
                            run=run,
                            reason="re-plan triggered by rejected approval",
                        )

        # Some approval types have their own side-effect branch above (for example
        # task_mark_complete). Rejection handling must still be applied uniformly;
        # otherwise a rejected completion request could leave a run blocked forever.
        if status == "rejected" and approval.task_id:
            task = await self.db.get(OrchestratorTask, approval.task_id)
            if task and task.status in {"blocked", "approved", "completed"}:
                await self._transition_task_status(
                    task,
                    "planned",
                    reason="approval rejected; task returned to planning",
                )
            if approval.run_id:
                run = await self.db.get(TaskRun, approval.run_id)
                if run and run.status not in {"completed", "failed", "cancelled"}:
                    run.status = "failed"
                    run.error_message = f"Approval rejected: {reason or 'No reason provided'}"
                    await self._emit_run_event(
                        run,
                        event_type="approval_rejected",
                        level="warning",
                        message="Run failed because a required approval was rejected.",
                        payload={"approval_id": approval.id, "reason": reason},
                    )
        resume_run_id: str | None = None
        if status == "approved" and approval.run_id:
            run = await self.db.get(TaskRun, approval.run_id)
            if run and run.status == "blocked":
                run.status = "queued"
                run.error_message = None
                run.completed_at = None
                task = await self.db.get(OrchestratorTask, run.task_id) if run.task_id else None
                if task and task.status == "blocked":
                    await self._transition_task_status(
                        task,
                        "planned",
                        run=run,
                        reason="approval granted; durable run resume queued",
                    )
                await self._emit_run_event(
                    run,
                    event_type="unblocked",
                    level="info",
                    message="Run queued for durable resume after human approval.",
                    payload={"approval_id": approval.id, "reason": reason},
                )
                resume_run_id = run.id

        await self.audit_repo.log(
            user_id=user.id,
            action=f"orchestration.approval.{status}",
            resource_type="approval_request",
            resource_id=approval.id,
            metadata={
                "approval_type": approval.approval_type,
                "project_id": approval.project_id,
                "task_id": approval.task_id,
                "run_id": approval.run_id,
                "reason": reason,
            },
        )
        await self.db.commit()
        if resume_run_id:
            from backend.modules.orchestration.execution.durable_execution import (
                submit_orchestration_run,
            )

            submit_orchestration_run(resume_run_id)
        try:
            from backend.modules.workforce.services.workflow_hooks import on_approval_decided

            await on_approval_decided(self.db, approval.id)
        except Exception:
            logger.exception(
                "workflow_approval_decided_hook_failed approval_id=%s",
                approval.id,
            )
        await self.db.refresh(approval)
        return approval

    async def get_pending_approvals_count(self, user: User) -> int:
        """Return the count of pending approvals for the user."""
        approvals = await self.repo.list_approvals(user.id, status="pending")
        return len(approvals)

    def action_requires_approval(
        self,
        project: OrchestratorProject,
        action_type: str,
    ) -> bool:
        """Check if an action type requires approval based on project gate config.

        Protected actions remain gated at every autonomy level. Autonomous mode only
        short-circuits optional, non-destructive actions.
        """
        settings = self._project_execution_settings(project)
        return hitl_action_requires_approval(settings, action_type)
