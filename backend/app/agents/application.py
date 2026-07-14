"""Application use cases for the compatibility agent API."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agents.logging import log_agent_event
from backend.app.agents.workspace import write_artifact
from backend.modules.identity_access.models import User
from backend.modules.orchestration.execution.execution_workflow import (
    ensure_workflow_state,
    mark_step,
)
from backend.modules.orchestration.models import TaskArtifact
from backend.modules.orchestration.services.application import OrchestrationApplicationService
from backend.modules.projects.orchestration_models import OrchestratorTask


class AgentRunApplicationService:
    """Owns the agent API's planned-run and approval lifecycle."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.orchestration = OrchestrationApplicationService(db)

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

    async def create_planned_run(
        self,
        user: User,
        task_id: str,
        payload: dict[str, Any] | None = None,
    ):
        task = await self.db.get(OrchestratorTask, task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        await self.orchestration.get_project(user, task.project_id)
        request = dict(payload or {})
        assigned_ids = [
            str(item) for item in request.get("assigned_agent_ids", []) if str(item).strip()
        ]
        if not assigned_ids and task.assigned_agent_id:
            assigned_ids = [task.assigned_agent_id]
        plan_steps = self._plan_for_task(task, assigned_ids)
        run = await self.orchestration.repo.create_run(
            project_id=task.project_id,
            task_id=task.id,
            triggered_by_user_id=user.id,
            worker_agent_id=assigned_ids[0]
            if assigned_ids and assigned_ids[0] != "unassigned"
            else None,
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
        await self.orchestration.repo.create_run_event(
            run_id=run.id,
            task_id=task.id,
            event_type="plan_generated",
            message="Deterministic placeholder plan generated; awaiting approval.",
            payload_json={"plan": plan_steps},
        )
        await self.db.commit()
        await self.db.refresh(run)
        log_agent_event(
            "run_created",
            user_id=user.id,
            task_id=task.id,
            run_id=run.id,
            project_id=task.project_id,
        )
        log_agent_event(
            "plan_generated",
            user_id=user.id,
            task_id=task.id,
            run_id=run.id,
            project_id=task.project_id,
        )
        return run

    async def approve_plan(self, user: User, run_id: str):
        run = await self.orchestration.get_run(user, run_id)
        if run.status != "awaiting_approval":
            raise HTTPException(status_code=409, detail="Run is not awaiting plan approval.")
        run.status = "running"
        run.started_at = datetime.now(UTC)
        steps = list((run.output_payload_json or {}).get("plan") or [])
        await self.orchestration.repo.create_run_event(
            run_id=run.id,
            task_id=run.task_id,
            event_type="plan_approved",
            message="Plan approved; placeholder execution started.",
            payload_json={"approved_by_user_id": user.id},
        )
        log_agent_event(
            "plan_approved",
            user_id=user.id,
            run_id=run.id,
            task_id=run.task_id,
            project_id=run.project_id,
        )
        for index, step in enumerate(steps):
            step_id = str(step.get("id") or f"step_{index}")
            run.checkpoint_json = mark_step(
                run.checkpoint_json, step_id=step_id, status="in_progress"
            )
            await self.orchestration.repo.create_run_event(
                run_id=run.id,
                task_id=run.task_id,
                event_type="run_step_started",
                message=str(step.get("title") or step_id),
                payload_json={"step_index": index, "step": step},
            )
            run.checkpoint_json = mark_step(
                run.checkpoint_json, step_id=step_id, status="completed"
            )
            await self.orchestration.repo.create_run_event(
                run_id=run.id,
                task_id=run.task_id,
                event_type="run_step_completed",
                message=str(step.get("title") or step_id),
                payload_json={"step_index": index, "step": step, "output": "placeholder_completed"},
            )
            log_agent_event(
                "run_step_completed",
                user_id=user.id,
                run_id=run.id,
                task_id=run.task_id,
                project_id=run.project_id,
                step_id=step_id,
            )
        final_output = "Placeholder run completed after human plan approval. Real LLM/tool execution is still disabled."
        path = await write_artifact(self.db, run.id, "final-output.md", final_output)
        self.db.add(
            TaskArtifact(
                task_id=run.task_id,
                run_id=run.id,
                kind="final_output",
                title="final-output.md",
                content=final_output,
                metadata_json={"path_or_url": str(path), "workspace_file": "final-output.md"},
            )
        )
        run.status = "completed"
        run.completed_at = datetime.now(UTC)
        run.output_payload_json = {**(run.output_payload_json or {}), "final_output": final_output}
        await self.orchestration.repo.create_run_event(
            run_id=run.id,
            task_id=run.task_id,
            event_type="artifact_created",
            message="Final output artifact created.",
            payload_json={"artifact_name": "final-output.md", "path_or_url": str(path)},
        )
        await self.db.commit()
        await self.db.refresh(run)
        log_agent_event(
            "artifact_created",
            user_id=user.id,
            run_id=run.id,
            task_id=run.task_id,
            project_id=run.project_id,
            path_or_url=str(path),
        )
        return run


__all__ = ["AgentRunApplicationService"]
