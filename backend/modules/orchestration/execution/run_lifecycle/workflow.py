"""Workflow checkpoint definitions and step marking."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from backend.modules.identity_access.models import User
from backend.modules.orchestration.execution.execution_workflow import (
    enqueue_signal,
    ensure_workflow_state,
    get_workflow_artifact,
    mark_step,
    set_workflow_artifact,
    summarize_trace,
    workflow_state,
)
from backend.modules.orchestration.execution.external_actions import external_action_workflow_step
from backend.modules.orchestration.execution.result_contracts import (
    durable_workflow_payload,
)
from backend.modules.orchestration.models import TaskRun


class ExecutionRunWorkflowMixin:
    def _workflow_steps_for_run(self, run: TaskRun) -> list[dict[str, Any]]:
        if run.run_mode == "manager_worker":
            return [
                {"id": "planning", "title": "Planning", "actor": "supervisor"},
                {"id": "subtask_dispatch", "title": "Subtask dispatch", "actor": "supervisor"},
                {"id": "worker_execution", "title": "Worker execution", "actor": "worker_pool"},
                {"id": "blocker_resolution", "title": "Blocker resolution", "actor": "supervisor"},
                {"id": "review", "title": "Review", "actor": "reviewer"},
                {"id": "artifact_publish", "title": "Artifact publish", "actor": "system"},
                external_action_workflow_step(),
            ]
        if run.run_mode == "review":
            return [
                {"id": "review", "title": "Review", "actor": "reviewer"},
                {"id": "artifact_publish", "title": "Artifact publish", "actor": "system"},
                external_action_workflow_step(),
            ]
        return [
            {"id": "build_prompt", "title": "Build prompt", "actor": "system"},
            {"id": "plan_execution", "title": "Plan execution", "actor": "supervisor"},
            {"id": "run_tools", "title": "Run tools", "actor": "worker_pool"},
            {"id": "model_response", "title": "Model response", "actor": "worker"},
            {"id": "persist_output", "title": "Persist outputs", "actor": "system"},
        ]

    def _ensure_run_workflow(self, run: TaskRun) -> dict[str, Any]:
        run.checkpoint_json = ensure_workflow_state(
            run.checkpoint_json,
            run_mode=run.run_mode,
            steps=self._workflow_steps_for_run(run),
            run_id=run.id,
        )
        return workflow_state(run.checkpoint_json)

    def _workflow_trace_payload(self, run: TaskRun) -> list[dict[str, Any]]:
        return summarize_trace(run.checkpoint_json)

    async def _child_runs_for_parent(self, parent_run_id: str) -> list[TaskRun]:
        return await self.repo.list_child_runs(parent_run_id)

    async def _mark_run_step(
        self,
        run: TaskRun,
        *,
        step_id: str,
        status: str,
        message: str,
        event_type: str = "workflow_step",
        level: str = "info",
        metadata: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        step_id = self._normalize_workflow_step_id(step_id)
        run.checkpoint_json = mark_step(
            run.checkpoint_json,
            step_id=step_id,
            status=status,
            error=error,
            metadata=metadata,
        )
        await self._emit_run_event(
            run,
            event_type=event_type,
            level=level,
            message=message,
            payload={
                "step_id": step_id,
                "status": status,
                "trace": self._workflow_trace_payload(run),
                **dict(metadata or {}),
            },
        )

    def _workflow_checkpoint_artifact(self, run: TaskRun, key: str, default: Any = None) -> Any:
        return get_workflow_artifact(run.checkpoint_json, key, default)

    def _set_workflow_checkpoint_artifact(self, run: TaskRun, *, key: str, value: Any) -> None:
        run.checkpoint_json = set_workflow_artifact(run.checkpoint_json, key=key, value=value)

    def _durable_workflow_payload(self, run: TaskRun) -> dict[str, Any]:
        self._ensure_run_workflow(run)
        return durable_workflow_payload(
            run.checkpoint_json,
            resumable=self._run_is_resumable(run),
        )

    async def signal_run_workflow(
        self,
        user: User,
        run_id: str,
        signal_name: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        run = await self.get_run(user, run_id)
        normalized_name = str(signal_name or "").strip().lower()
        if normalized_name not in {"pause", "resume", "retry_step", "update_objective", "add_note"}:
            raise HTTPException(status_code=400, detail="Unsupported workflow signal")
        run.checkpoint_json = enqueue_signal(
            run.checkpoint_json,
            signal_name=normalized_name,
            payload=payload or {},
            requested_by_user_id=user.id,
        )
        await self._emit_run_event(
            run,
            event_type="workflow_signal_queued",
            message=f"Workflow signal '{normalized_name}' queued.",
            payload={"signal_name": normalized_name, "signal_payload": payload or {}},
        )
        await self.db.commit()
        return self._durable_workflow_payload(run)
