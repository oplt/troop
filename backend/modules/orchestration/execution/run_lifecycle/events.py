"""Run event emission and task status transitions."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException

from backend.modules.orchestration.execution.policies import is_valid_task_transition
from backend.modules.orchestration.models import TaskRun
from backend.modules.projects.orchestration_models import OrchestratorTask


class ExecutionRunEventsMixin:
    async def _emit_run_event(
        self,
        run: TaskRun,
        *,
        event_type: str,
        message: str,
        level: str = "info",
        payload: dict[str, Any] | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd_micros: int = 0,
        commit: bool = True,
    ) -> None:
        from backend.modules.observability.tracing import enrich_with_trace_context

        await self.repo.create_run_event(
            run_id=run.id,
            task_id=run.task_id,
            event_type=event_type,
            level=level,
            message=message,
            payload_json=enrich_with_trace_context(payload),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd_micros=cost_usd_micros,
        )
        await self._refresh_run_scratchpad(run)
        if commit:
            await self.db.commit()
        else:
            await self.db.flush()

    async def _transition_task_status(
        self,
        task: OrchestratorTask,
        next_status: str,
        *,
        run: TaskRun | None = None,
        reason: str | None = None,
    ) -> None:
        current = task.status
        if current == next_status:
            return
        if not is_valid_task_transition(current, next_status):
            raise HTTPException(
                status_code=409,
                detail=f"Invalid task transition from {current} to {next_status}",
            )
        task.status = next_status
        task.updated_at = datetime.now(UTC)
        if next_status == "blocked":
            await self._apply_blocked_handoff_suggestion(task, run, reason)
        payload_json: dict[str, Any] = {"from": current, "to": next_status, "reason": reason}
        if next_status == "blocked":
            hid = (task.metadata_json or {}).get("suggested_handoff_agent_id")
            if hid:
                payload_json["suggested_handoff_agent_id"] = hid
                payload_json["handoff_suggested_via"] = (task.metadata_json or {}).get(
                    "handoff_suggested_via"
                )
        target_run_id: str | None = run.id if run is not None else None
        if target_run_id is None:
            latest = await self.repo.get_latest_run_for_task(task.project_id, task.id)
            if latest is not None:
                target_run_id = latest.id
        if target_run_id is not None:
            await self.repo.create_run_event(
                run_id=target_run_id,
                task_id=task.id,
                event_type="task_status_changed",
                message=f"Task transitioned from {current} to {next_status}.",
                payload_json=payload_json,
            )
            await self.db.commit()
