"""Legacy planned-placeholder run use cases owned by orchestration."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.logging import get_logger
from backend.modules.identity_access.models import User
from backend.modules.observability.logging import log_event
from backend.modules.orchestration.execution.execution_workflow import (
    ensure_workflow_state,
    mark_step,
)
from backend.modules.orchestration.models import RunEvent, TaskRun
from backend.modules.orchestration.repository import OrchestrationRepository
from backend.modules.orchestration.services.service import OrchestrationService
from backend.modules.orchestration.workspace import RunWorkspaceService
from backend.modules.projects.orchestration_models import OrchestratorTask, TaskArtifact

logger = get_logger(__name__)


class PlannedRunTaskNotFoundError(LookupError):
    pass


class PlannedRunNotFoundError(LookupError):
    pass


class PlanApprovalConflictError(RuntimeError):
    pass


class PlannedRunService:
    """Own the compatibility plan/run lifecycle without owning HTTP transport."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        workspace: RunWorkspaceService | None = None,
    ) -> None:
        self.db = db
        self.repo = OrchestrationRepository(db)
        self.orchestration = OrchestrationService(db)
        self.workspace = workspace or RunWorkspaceService()

    @staticmethod
    def _plan_for_task(task: OrchestratorTask, agent_ids: list[str]) -> list[dict[str, Any]]:
        actors = agent_ids or ([task.assigned_agent_id] if task.assigned_agent_id else [])
        if not actors:
            actors = ["unassigned"]
        return [
            {
                "id": "understand_task",
                "title": f"Review task: {task.title}",
                "actor": actors[0],
                "status": "pending",
                "metadata": {"source": "deterministic_placeholder_planner"},
            },
            {
                "id": "gather_context",
                "title": "Gather project, task, and memory context",
                "actor": actors[0],
                "status": "pending",
                "metadata": {"tools": ["file_read_stub", "web_search_stub"]},
            },
            {
                "id": "draft_output",
                "title": "Draft final task output and artifacts",
                "actor": actors[-1],
                "status": "pending",
                "metadata": {"requires_human_review": False},
            },
        ]

    async def get_run(self, user: User, run_id: str) -> TaskRun:
        run = await self.repo.get_run(user.id, run_id)
        if run is None:
            raise PlannedRunNotFoundError("Run not found")
        return run

    async def list_run_events(self, user: User, run_id: str) -> list[RunEvent]:
        run = await self.get_run(user, run_id)
        return await self.repo.list_run_events(run.id)

    async def list_run_artifacts(self, user: User, run_id: str) -> list[TaskArtifact]:
        run = await self.get_run(user, run_id)
        return await self.repo.list_run_artifacts(run.id)

    async def list_workspace_files(self, user: User, run_id: str):
        run = await self.get_run(user, run_id)
        return await self.workspace.list_files(run)

    async def create_planned_run(
        self,
        user: User,
        task_id: str,
        payload: dict[str, Any] | None = None,
    ) -> TaskRun:
        task = await self.repo.get_task_by_id(task_id)
        if task is None:
            raise PlannedRunTaskNotFoundError("Task not found")
        try:
            project = await self.orchestration.get_project(user, task.project_id)
        except Exception as exc:
            if getattr(exc, "status_code", None) == 404:
                raise PlannedRunTaskNotFoundError("Task not found") from exc
            raise

        request = dict(payload or {})
        assigned_ids = [
            str(item) for item in request.get("assigned_agent_ids", []) if str(item).strip()
        ]
        if not assigned_ids and task.assigned_agent_id:
            assigned_ids = [task.assigned_agent_id]
        plan_steps = self._plan_for_task(task, assigned_ids)
        run = await self.repo.create_run(
            project_id=task.project_id,
            task_id=task.id,
            triggered_by_user_id=user.id,
            worker_agent_id=(
                assigned_ids[0] if assigned_ids and assigned_ids[0] != "unassigned" else None
            ),
            run_mode=str(request.get("run_mode") or "planned_placeholder"),
            status="awaiting_approval",
            input_payload_json={"requested_by": "agent_task_run_api", **request},
            output_payload_json={},
        )
        run.checkpoint_json = ensure_workflow_state(
            run.checkpoint_json,
            run_mode=run.run_mode,
            steps=plan_steps,
            run_id=run.id,
        )
        run.output_payload_json = {"plan": plan_steps}
        await self.repo.create_run_event(
            run_id=run.id,
            task_id=task.id,
            event_type="plan_generated",
            message="Deterministic placeholder plan generated; awaiting approval.",
            payload_json={"plan": plan_steps},
        )
        await self.db.commit()
        await self.db.refresh(run)
        log_event(
            logger,
            "planned_run_created",
            user_id=user.id,
            company_id=getattr(project, "company_id", None),
            project_id=task.project_id,
            task_id=task.id,
            run_id=run.id,
            status=run.status,
        )
        return run

    async def approve_plan(self, user: User, run_id: str) -> TaskRun:
        authorized_run = await self.get_run(user, run_id)
        run = await self.repo.get_run_for_worker(authorized_run.id)
        if run is None:
            raise PlannedRunNotFoundError("Run not found")
        if run.status != "awaiting_approval":
            raise PlanApprovalConflictError("Run is not awaiting plan approval.")

        run.status = "running"
        run.started_at = datetime.now(UTC)
        steps = list((run.output_payload_json or {}).get("plan") or [])
        await self.repo.create_run_event(
            run_id=run.id,
            task_id=run.task_id,
            event_type="plan_approved",
            message="Plan approved; placeholder execution started.",
            payload_json={"approved_by_user_id": user.id},
        )
        for index, step in enumerate(steps):
            step_id = str(step.get("id") or f"step_{index}")
            run.checkpoint_json = mark_step(
                run.checkpoint_json,
                step_id=step_id,
                status="in_progress",
            )
            await self.repo.create_run_event(
                run_id=run.id,
                task_id=run.task_id,
                event_type="run_step_started",
                message=str(step.get("title") or step_id),
                payload_json={"step_index": index, "step": step},
            )
            run.checkpoint_json = mark_step(
                run.checkpoint_json,
                step_id=step_id,
                status="completed",
            )
            await self.repo.create_run_event(
                run_id=run.id,
                task_id=run.task_id,
                event_type="run_step_completed",
                message=str(step.get("title") or step_id),
                payload_json={
                    "step_index": index,
                    "step": step,
                    "output": "placeholder_completed",
                },
            )
            log_event(
                logger,
                "planned_run_step_completed",
                user_id=user.id,
                project_id=run.project_id,
                task_id=run.task_id,
                run_id=run.id,
                step_id=step_id,
                status="completed",
            )

        final_output = (
            "Placeholder run completed after human plan approval. "
            "Real LLM/tool execution is still disabled."
        )
        stored = await self.workspace.write_artifact(run, "final-output.md", final_output)
        await self.repo.create_task_artifact(
            task_id=run.task_id,
            run_id=run.id,
            kind="final_output",
            title="final-output.md",
            content=final_output,
            metadata_json={
                "path_or_url": stored.location,
                "workspace_file": stored.path,
            },
        )
        run.status = "completed"
        run.completed_at = datetime.now(UTC)
        run.output_payload_json = {
            **(run.output_payload_json or {}),
            "final_output": final_output,
        }
        await self.repo.create_run_event(
            run_id=run.id,
            task_id=run.task_id,
            event_type="artifact_created",
            message="Final output artifact created.",
            payload_json={
                "artifact_name": "final-output.md",
                "path_or_url": stored.location,
            },
        )
        await self.db.commit()
        await self.db.refresh(run)
        log_event(
            logger,
            "planned_run_completed",
            user_id=user.id,
            project_id=run.project_id,
            task_id=run.task_id,
            run_id=run.id,
            status=run.status,
        )
        return run


__all__ = [
    "PlanApprovalConflictError",
    "PlannedRunNotFoundError",
    "PlannedRunService",
    "PlannedRunTaskNotFoundError",
]
