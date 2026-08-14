"""Task lifecycle helpers: SLA, blockers, merge resolution, execution memory, reopen records."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from difflib import unified_diff
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import attributes as orm_attributes

from backend.modules.identity_access.models import User
from backend.modules.orchestration.models import TaskRun
from backend.modules.projects.orchestration_models import OrchestratorTask


class TaskLifecycleMixin:
    def _task_effective_sla_deadline(self, task: OrchestratorTask) -> datetime | None:
        deadlines: list[datetime] = []
        if task.due_date:
            deadlines.append(task.due_date)
        if task.response_sla_hours and task.created_at:
            deadlines.append(task.created_at + timedelta(hours=int(task.response_sla_hours)))
        if not deadlines:
            return None
        return min(deadlines)

    async def get_task_blockers(self, user: User, project_id: str, task_id: str) -> dict[str, Any]:
        task = await self.get_task(user, project_id, task_id)
        project = await self.get_project(user, project_id)
        blockers: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        terminal = {"approved", "completed", "synced_to_github", "archived"}

        for dependency in await self.repo.list_task_dependencies_for_task(task.id):
            dependency_task = await self.repo.get_task_by_id(dependency.depends_on_task_id)
            if dependency_task is not None and dependency_task.status not in terminal:
                blockers.append(
                    {
                        "kind": "dependency",
                        "task_id": dependency_task.id,
                        "title": dependency_task.title,
                        "status": dependency_task.status,
                        "message": f"Dependency '{dependency_task.title}' is not complete.",
                    }
                )

        memberships = await self.repo.list_project_memberships(project.id)
        member_ids = {item.agent_id for item in memberships}
        if task.assigned_agent_id:
            owner = await self.get_agent(user, task.assigned_agent_id)
            if task.assigned_agent_id not in member_ids:
                blockers.append(
                    {"kind": "owner", "message": "The assigned owner is not a project member."}
                )
            elif not owner.is_active:
                blockers.append({"kind": "owner", "message": "The assigned owner is inactive."})
            missing_tools = sorted(
                set(
                    self._normalized_required_tools(
                        (task.metadata_json or {}).get("required_tools")
                    )
                )
                - set(owner.allowed_tools_json or [])
            )
            if missing_tools:
                blockers.append(
                    {
                        "kind": "required_tools",
                        "missing_tools": missing_tools,
                        "message": f"Owner lacks required tools: {', '.join(missing_tools)}.",
                    }
                )
        elif task.status in {"planned", "in_progress"}:
            warnings.append(
                {
                    "kind": "owner",
                    "message": "Task has no pinned owner; runtime routing will select one.",
                }
            )

        if task.status == "needs_review" and not task.reviewer_agent_id:
            blockers.append(
                {"kind": "reviewer", "message": "Task needs review but has no reviewer assigned."}
            )
        elif task.reviewer_agent_id:
            reviewer = await self.get_agent(user, task.reviewer_agent_id)
            if task.reviewer_agent_id not in member_ids or not reviewer.is_active:
                blockers.append(
                    {"kind": "reviewer", "message": "The assigned reviewer is unavailable."}
                )

        deadline = self._task_effective_sla_deadline(task)
        if deadline is not None:
            now = datetime.now(UTC)
            if now > deadline and task.status not in terminal:
                blockers.append(
                    {
                        "kind": "sla",
                        "deadline": deadline.isoformat(),
                        "message": "Task SLA is overdue.",
                    }
                )
            elif deadline - now <= timedelta(hours=24) and task.status not in terminal:
                warnings.append(
                    {
                        "kind": "sla",
                        "deadline": deadline.isoformat(),
                        "message": "Task SLA is due within 24 hours.",
                    }
                )

        latest_run = await self.repo.get_latest_run_for_task(project.id, task.id)
        if latest_run is not None and latest_run.status in {"failed", "blocked"}:
            warnings.append(
                {
                    "kind": "run",
                    "run_id": latest_run.id,
                    "status": latest_run.status,
                    "message": latest_run.error_message or f"Latest run is {latest_run.status}.",
                }
            )
        if task.status == "blocked":
            metadata = task.metadata_json or {}
            blockers.append(
                {
                    "kind": "task_status",
                    "message": str(
                        metadata.get("handoff_blocked_reason") or "Task is marked blocked."
                    ),
                    "suggested_handoff_agent_id": metadata.get("suggested_handoff_agent_id"),
                }
            )

        return {
            "task_id": task.id,
            "can_start": not blockers,
            "blockers": blockers,
            "warnings": warnings,
        }

    async def merge_resolution_preview(
        self, user: User, project_id: str, parent_task_id: str
    ) -> dict[str, Any]:
        parent = await self.get_task(user, project_id, parent_task_id)
        children = await self.repo.list_subtasks(parent_task_id)
        branches: list[dict[str, Any]] = []
        for child in children:
            branches.append(
                {
                    "id": child.id,
                    "title": child.title,
                    "status": child.status,
                    "assigned_agent_id": child.assigned_agent_id,
                    "result_summary": child.result_summary,
                }
            )
        completed = [child for child in children if child.status in {"completed", "approved"}]
        agents = {child.assigned_agent_id for child in completed if child.assigned_agent_id}
        return {
            "parent": {"id": parent.id, "title": parent.title, "task_type": parent.task_type},
            "branches": branches,
            "completed_branch_count": len(completed),
            "distinct_agents_on_completed": len(agents),
            "needs_merge_agent": len(agents) > 1 and len(completed) >= 2,
        }

    async def start_merge_resolution_run(
        self,
        user: User,
        project_id: str,
        parent_task_id: str,
        payload: dict[str, Any],
    ) -> TaskRun:
        children = await self.repo.list_subtasks(parent_task_id)
        completed = [child for child in children if child.status in {"completed", "approved"}]
        if len(completed) < 2:
            raise HTTPException(
                status_code=400,
                detail="Merge resolution requires at least two completed subtasks under this parent.",
            )
        sources: list[dict[str, Any]] = []
        for child in completed:
            sources.append(
                {
                    "task_id": child.id,
                    "title": child.title,
                    "assigned_agent_id": child.assigned_agent_id,
                    "result_summary": child.result_summary,
                    "result_payload": child.result_payload_json,
                }
            )
        merge_ctx = {
            "parent_task_id": parent_task_id,
            "sources": sources,
            "notes": (payload.get("notes") or "")[:8000],
        }
        inp = dict(payload.get("input_payload") or {})
        inp["orchestration_merge_resolve"] = merge_ctx
        run, _warnings = await self.start_task_run(
            user,
            project_id,
            parent_task_id,
            {
                "run_mode": str(payload.get("run_mode") or "single_agent"),
                "input_payload": inp,
                "model_name": payload.get("model_name"),
            },
        )
        return run

    async def run_global_sla_escalation_scan(self) -> dict[str, Any]:
        projects = await self.repo.list_all_orchestrator_projects()
        checked = 0
        escalated = 0
        warned = 0
        now = datetime.now(UTC)
        for project in projects:
            exe = self._project_execution_settings(project)
            sla = exe.get("sla") or {}
            if not sla.get("enabled", True):
                continue
            after_h = float(sla.get("escalate_hours_after_due", 0) or 0)
            warn_h = float(sla.get("warn_hours_before_due", 24) or 24)
            tasks = await self.repo.list_tasks(project.id, limit=0)
            for task in tasks:
                if task.status in {"completed", "approved", "archived", "synced_to_github"}:
                    continue
                deadline = self._task_effective_sla_deadline(task)
                if deadline is None:
                    continue
                checked += 1
                meta = dict(task.metadata_json or {})
                warn_at = deadline - timedelta(hours=warn_h)
                if now >= warn_at and now < deadline and not meta.get("sla_warn_sent"):
                    meta["sla_warn_sent"] = True
                    meta["sla_warn_at"] = now.isoformat()
                    task.metadata_json = meta
                    orm_attributes.flag_modified(task, "metadata_json")
                    warned += 1
                    meta = dict(task.metadata_json or {})
                breach_at = deadline + timedelta(hours=after_h)
                if now <= breach_at:
                    continue
                if meta.get("sla_escalated_at"):
                    continue
                if (
                    await self.repo.count_pending_approvals_for_task(
                        project.id, task.id, "sla_escalation"
                    )
                    > 0
                ):
                    continue
                latest_run = await self.repo.get_latest_run_for_task(project.id, task.id)
                await self.repo.create_approval(
                    project_id=project.id,
                    task_id=task.id,
                    run_id=latest_run.id if latest_run else None,
                    requested_by_user_id=project.owner_id,
                    approval_type="sla_escalation",
                    status="pending",
                    payload_json={
                        "deadline": deadline.isoformat(),
                        "breach_at": breach_at.isoformat(),
                        "escalate_hours_after_due": after_h,
                    },
                )
                meta["sla_escalated_at"] = now.isoformat()
                task.metadata_json = meta
                orm_attributes.flag_modified(task, "metadata_json")
                escalated += 1
        await self.db.commit()
        return {
            "projects_scanned": len(projects),
            "tasks_considered": checked,
            "warnings_flagged": warned,
            "escalations_created": escalated,
        }

    def _update_task_execution_memory(self, task: OrchestratorTask, run: TaskRun) -> None:
        """Persist a compact execution-memory snapshot and a diff vs the previous completed run."""
        meta = dict(task.metadata_json or {})
        prev_block = meta.get("execution_memory") or {}
        latest = str(
            run.output_payload_json.get("summary")
            or run.output_payload_json.get("final_output")
            or task.result_summary
            or ""
        )
        prev_excerpt = str(prev_block.get("latest_summary_excerpt") or "")[:4000]
        new_excerpt = latest[:4000]
        diff_text = ""
        if prev_excerpt and new_excerpt and prev_excerpt != new_excerpt:
            diff_lines = list(
                unified_diff(
                    prev_excerpt.splitlines(),
                    new_excerpt.splitlines(),
                    fromfile="previous_run",
                    tofile="this_run",
                    lineterm="",
                )
            )[:160]
            diff_text = "\n".join(diff_lines)[:12000]
        meta["execution_memory"] = {
            "last_run_id": run.id,
            "last_run_mode": run.run_mode,
            "last_completed_at": datetime.now(UTC).isoformat(),
            "previous_summary_excerpt": prev_excerpt[:2000],
            "latest_summary_excerpt": new_excerpt[:2000],
            "since_last_run_unified_diff": diff_text,
        }
        task.metadata_json = meta
        orm_attributes.flag_modified(task, "metadata_json")

    def _append_structured_reopen_record(
        self,
        task: OrchestratorTask,
        review_payload: dict[str, Any],
        *,
        run: TaskRun | None,
    ) -> None:
        meta = dict(task.metadata_json or {})
        hist = list(meta.get("reopen_history") or [])
        reasons = review_payload.get("reasons")
        if isinstance(reasons, str):
            reasons = [reasons]
        elif isinstance(reasons, list):
            reasons = [str(x) for x in reasons]
        else:
            reasons = [str(review_payload.get("summary") or "rework requested")]
        checklist = review_payload.get("checklist")
        if not isinstance(checklist, list):
            checklist = []
        checklist = [str(x) for x in checklist]
        rec: dict[str, Any] = {
            "at": datetime.now(UTC).isoformat(),
            "run_id": run.id if run else None,
            "decision": str(review_payload.get("decision") or "rework"),
            "summary": str(review_payload.get("summary") or "")[:4000],
            "reasons": [str(x)[:2000] for x in reasons[:50]],
            "checklist": [str(x)[:2000] for x in checklist[:50]],
        }
        hist.append(rec)
        meta["reopen_history"] = hist[-40:]
        meta["latest_reopen"] = rec
        task.metadata_json = meta
        orm_attributes.flag_modified(task, "metadata_json")
