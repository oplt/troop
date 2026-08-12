"""Canonical TaskRun creation + enqueue path shared by API, workflows, and workers."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from backend.modules.identity_access.models import User
from backend.modules.orchestration.models import RunEvent, TaskRun
from backend.modules.orchestration.skill_snapshot import freeze_skill_version_snapshot


class SkillSnapshotError(RuntimeError):
    """Raised when SkillVersion freeze fails for a workforce run."""


async def _emit_snapshot_event(
    db: AsyncSession,
    run: TaskRun,
    *,
    message: str,
    level: str = "error",
    payload: dict[str, Any] | None = None,
) -> None:
    db.add(
        RunEvent(
            run_id=run.id,
            task_id=run.task_id,
            level=level,
            event_type="skill_snapshot_failed",
            message=message,
            payload_json=payload or {},
        )
    )
    await db.flush()


async def freeze_or_degrade_snapshot(
    db: AsyncSession,
    run: TaskRun,
    *,
    agent_id: str | None,
    allow_degraded: bool = False,
) -> dict[str, Any]:
    """Freeze SkillVersions onto the run. Fail closed unless allow_degraded=True."""
    try:
        snapshot = await freeze_skill_version_snapshot(db, run, agent_id=agent_id)
        checkpoint = dict(run.checkpoint_json or {})
        checkpoint["snapshot_status"] = "frozen"
        checkpoint["execution_mode"] = checkpoint.get("execution_mode") or "workforce"
        run.checkpoint_json = checkpoint
        flag_modified(run, "checkpoint_json")
        return snapshot
    except Exception as exc:  # noqa: BLE001
        checkpoint = dict(run.checkpoint_json or {})
        checkpoint["snapshot_status"] = "failed"
        checkpoint["execution_mode"] = "legacy/degraded"
        checkpoint["skill_version_snapshot"] = {
            "agent_id": agent_id,
            "skill_version_ids": [],
            "skills": [],
            "required_tools": [],
            "capabilities": [],
            "error": str(exc),
        }
        run.checkpoint_json = checkpoint
        flag_modified(run, "checkpoint_json")
        await _emit_snapshot_event(
            db,
            run,
            message=f"SkillVersion snapshot failed: {exc}",
            payload={"error": str(exc), "agent_id": agent_id},
        )
        if allow_degraded:
            return checkpoint["skill_version_snapshot"]
        raise SkillSnapshotError(str(exc)) from exc


class TaskRunStarter:
    """Single entry point to create, freeze, and enqueue a durable TaskRun."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def start(
        self,
        user: User,
        *,
        project_id: str,
        task_id: str,
        worker_agent_id: str | None = None,
        orchestrator_agent_id: str | None = None,
        run_mode: str = "single_agent",
        input_payload: dict[str, Any] | None = None,
        allow_degraded_snapshot: bool = False,
    ) -> tuple[TaskRun, list[str]]:
        """Delegate to ExecutionService.start_task_run (canonical lifecycle)."""
        from backend.modules.orchestration.execution.execution_service import ExecutionService

        payload: dict[str, Any] = dict(input_payload or {})
        if worker_agent_id is not None:
            payload["worker_agent_id"] = worker_agent_id
        if orchestrator_agent_id is not None:
            payload["orchestrator_agent_id"] = orchestrator_agent_id
        payload["run_mode"] = run_mode
        payload["allow_degraded_snapshot"] = allow_degraded_snapshot

        service = ExecutionService(self.db)
        run, warnings = await service.start_task_run(
            user,
            project_id,
            task_id,
            payload,
        )
        status = (run.checkpoint_json or {}).get("snapshot_status")
        if status == "failed" and not allow_degraded_snapshot:
            raise SkillSnapshotError("SkillVersion snapshot failed during run start")
        return run, warnings
