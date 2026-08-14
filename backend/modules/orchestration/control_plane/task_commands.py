"""Task, run, and brainstorm commands."""

from __future__ import annotations

from typing import Any

from backend.modules.identity_access.models import User
from backend.modules.orchestration.control_plane.pubsub import (
    ControlPlaneEvent,
    _now,
    control_plane_pubsub,
)
from backend.modules.orchestration.models import OrchestratorTask, TaskArtifact, TaskRun


class ControlPlaneTasksMixin:
    async def create_task(self, user: User, payload: dict[str, Any]) -> OrchestratorTask:
        task = await self.service.create_task(
            user,
            payload["project_id"],
            {
                "title": payload["title"],
                "description": payload.get("description"),
                "assigned_agent_id": payload.get("assigned_member_id"),
                "reviewer_agent_id": payload.get("reviewer_member_id"),
                "acceptance_criteria": payload.get("acceptance_criteria"),
                "priority": payload.get("priority") or "normal",
                "task_type": payload.get("task_type") or "general",
                "labels": payload.get("labels") or [],
                "metadata": payload.get("metadata") or {},
            },
        )
        await control_plane_pubsub.publish(
            ControlPlaneEvent(
                event_type="task.created",
                project_id=payload["project_id"],
                member_id=task.assigned_agent_id,
                task_id=task.id,
                run_id=None,
                status=task.status,
                payload={"title": task.title},
                emitted_at=_now(),
            )
        )
        return task

    async def assign_task(
        self, user: User, project_id: str, task_id: str, member_id: str
    ) -> OrchestratorTask:
        task = await self.service.update_task(
            user,
            project_id,
            task_id,
            {"assigned_agent_id": member_id, "status": "planned"},
        )
        await control_plane_pubsub.publish(
            ControlPlaneEvent(
                event_type="task.assigned",
                project_id=project_id,
                member_id=member_id,
                task_id=task.id,
                run_id=None,
                status=task.status,
                payload={"title": task.title},
                emitted_at=_now(),
            )
        )
        return task

    async def update_task_status(
        self, user: User, project_id: str, task_id: str, status: str
    ) -> OrchestratorTask:
        task = await self.service.update_task(user, project_id, task_id, {"status": status})
        await control_plane_pubsub.publish(
            ControlPlaneEvent(
                event_type="task.status",
                project_id=project_id,
                member_id=task.assigned_agent_id,
                task_id=task.id,
                run_id=None,
                status=task.status,
                payload={"title": task.title},
                emitted_at=_now(),
            )
        )
        return task

    async def request_task_revision(
        self,
        user: User,
        project_id: str,
        task_id: str,
        notes: str,
    ) -> OrchestratorTask:
        await self.service.add_task_comment(user, project_id, task_id, notes)
        task = await self.service.update_task(user, project_id, task_id, {"status": "planned"})
        await control_plane_pubsub.publish(
            ControlPlaneEvent(
                event_type="task.revision_requested",
                project_id=project_id,
                member_id=task.assigned_agent_id,
                task_id=task.id,
                run_id=None,
                status=task.status,
                payload={"notes": notes},
                emitted_at=_now(),
            )
        )
        return task

    async def approve_task_output(
        self,
        user: User,
        project_id: str,
        task_id: str,
        summary: str | None,
    ) -> OrchestratorTask:
        updates: dict[str, Any] = {"status": "approved"}
        if summary:
            updates["result_summary"] = summary
        task = await self.service.update_task(user, project_id, task_id, updates)
        await control_plane_pubsub.publish(
            ControlPlaneEvent(
                event_type="task.approved",
                project_id=project_id,
                member_id=task.assigned_agent_id,
                task_id=task.id,
                run_id=None,
                status=task.status,
                payload={"summary": summary or ""},
                emitted_at=_now(),
            )
        )
        return task

    async def launch_task_run(
        self,
        user: User,
        project_id: str,
        task_id: str,
        member_id: str | None,
    ) -> TaskRun:
        run, _startup_warnings = await self.service.start_task_run(
            user,
            project_id,
            task_id,
            {
                "run_mode": "single_agent",
                "worker_agent_id": member_id,
            },
        )
        await control_plane_pubsub.publish(
            ControlPlaneEvent(
                event_type="run.started",
                project_id=project_id,
                member_id=member_id,
                task_id=task_id,
                run_id=run.id,
                status=run.status,
                payload={"run_mode": run.run_mode},
                emitted_at=_now(),
            )
        )
        return run

    async def start_brainstorm(
        self,
        user: User,
        project_id: str,
        topic: str,
        participant_ids: list[str],
        task_id: str | None = None,
    ) -> dict[str, Any]:
        brainstorm = await self.service.create_brainstorm(
            user,
            {
                "project_id": project_id,
                "task_id": task_id,
                "topic": topic,
                "participant_agent_ids": participant_ids,
            },
        )
        run = await self.service.start_brainstorm(user, brainstorm.id)
        await control_plane_pubsub.publish(
            ControlPlaneEvent(
                event_type="brainstorm.started",
                project_id=project_id,
                member_id=None,
                task_id=task_id,
                run_id=run.id,
                status=run.status,
                payload={"brainstorm_id": brainstorm.id, "topic": topic},
                emitted_at=_now(),
            )
        )
        return {"brainstorm": brainstorm, "run": run}

    async def list_task_artifacts(
        self, user: User, project_id: str, task_id: str
    ) -> list[TaskArtifact]:
        await self.service.get_task(user, project_id, task_id)
        return await self.repo.list_task_artifacts(task_id)
