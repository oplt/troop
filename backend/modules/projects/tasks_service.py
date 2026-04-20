from __future__ import annotations

import json
import math
import re
import uuid
from datetime import UTC, datetime, timedelta
from difflib import unified_diff
from types import SimpleNamespace
from typing import Any, Sequence

from fastapi import HTTPException
from sqlalchemy.orm import attributes as orm_attributes

from backend.modules.github.models import GithubIssueLink, GithubRepository
from backend.modules.identity_access.models import User
from backend.modules.orchestration._helpers import _normalize_task_priority
from backend.modules.orchestration.models import TaskRun
from backend.modules.projects.orchestration_models import (
    OrchestratorProject,
    OrchestratorTask,
    TaskArtifact,
)


EXTERNAL_LINK_KINDS: frozenset[str] = frozenset(
    {"spec", "doc", "figma", "pr", "commit", "incident", "runbook", "issue", "other"}
)


class OrchestrationTasksServiceMixin:
    """Task, acceptance, and subtask methods extracted from orchestration.

    The host service is expected to provide ``self.db`` and ``self.repo``, plus
    execution/github/memory helpers used by task lifecycle transitions.
    """

    async def list_tasks(self, user: User, project_id: str):
        await self.get_project(user, project_id)
        return await self.repo.list_tasks(project_id)

    async def get_task(self, user: User, project_id: str, task_id: str):
        await self.get_project(user, project_id)
        task = await self.repo.get_task(project_id, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return task

    async def create_task(self, user: User, project_id: str, payload: dict[str, Any]):
        project = await self.get_project(user, project_id)
        if payload.get("assigned_agent_id"):
            await self.get_agent(user, payload["assigned_agent_id"])
        if payload.get("reviewer_agent_id"):
            await self.get_agent(user, payload["reviewer_agent_id"])
        metadata = self._normalized_task_metadata(payload.get("metadata"))
        position = await self.repo.get_next_task_position(project.id)
        task = await self.repo.create_task(
            project_id=project.id,
            created_by_user_id=user.id,
            assigned_agent_id=payload.get("assigned_agent_id"),
            reviewer_agent_id=payload.get("reviewer_agent_id"),
            title=payload["title"],
            description=payload.get("description"),
            source=payload.get("source", "manual"),
            task_type=payload.get("task_type", "general"),
            priority=_normalize_task_priority(payload.get("priority")),
            status=payload.get("status", "queued"),
            acceptance_criteria=payload.get("acceptance_criteria"),
            due_date=payload.get("due_date"),
            response_sla_hours=payload.get("response_sla_hours"),
            labels_json=payload.get("labels", []),
            result_summary=payload.get("result_summary"),
            result_payload_json=payload.get("result_payload", {}),
            metadata_json=metadata,
            position=position,
        )
        dependency_ids = list(payload.get("dependency_ids", []) or [])
        await self._validate_task_dependencies(project.id, task.id, dependency_ids)
        await self.repo.replace_task_dependencies(task.id, dependency_ids)
        await self._sync_knowledge_graph_for_task(project, task)
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def update_task(self, user: User, project_id: str, task_id: str, updates: dict[str, Any]):
        task = await self.get_task(user, project_id, task_id)
        project = await self.db.get(OrchestratorProject, project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        if "assigned_agent_id" in updates and updates.get("assigned_agent_id") != task.assigned_agent_id:
            if self.action_requires_approval(project, "change_task_ownership"):
                approval = await self.repo.create_approval(
                    project_id=project.id,
                    task_id=task.id,
                    run_id=None,
                    issue_link_id=task.github_issue_link_id,
                    requested_by_user_id=user.id,
                    approval_type="task_assignment_change",
                    status="pending",
                    payload_json={
                        "task_id": task.id,
                        "from_assigned_agent_id": task.assigned_agent_id,
                        "to_assigned_agent_id": updates.get("assigned_agent_id"),
                    },
                )
                await self.db.commit()
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": "Changing task ownership requires approval.",
                        "approval_id": approval.id,
                    },
                )
        if "status" in updates and updates.get("status") in {"completed", "approved"}:
            if self.action_requires_approval(project, "mark_complete"):
                approval = await self.repo.create_approval(
                    project_id=project.id,
                    task_id=task.id,
                    run_id=None,
                    issue_link_id=task.github_issue_link_id,
                    requested_by_user_id=user.id,
                    approval_type="task_mark_complete",
                    status="pending",
                    payload_json={
                        "task_id": task.id,
                        "from_status": task.status,
                        "to_status": updates.get("status"),
                    },
                )
                await self.db.commit()
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": "Marking tasks complete requires approval.",
                        "approval_id": approval.id,
                    },
                )
        prev_snapshot = {
            "status": task.status,
            "assigned_agent_id": getattr(task, "assigned_agent_id", None),
            "labels": list(getattr(task, "labels_json", None) or []),
            "metadata": dict(getattr(task, "metadata_json", None) or {}),
        }
        prev_status = task.status
        if "assigned_agent_id" in updates and updates["assigned_agent_id"]:
            await self.get_agent(user, updates["assigned_agent_id"])
        if "reviewer_agent_id" in updates and updates["reviewer_agent_id"]:
            await self.get_agent(user, updates["reviewer_agent_id"])

        if "assigned_agent_id" in updates:
            next_meta = dict(task.metadata_json or {})
            assigned_agent_id = updates.get("assigned_agent_id")
            if assigned_agent_id:
                agent = await self.get_agent(user, assigned_agent_id)
                next_meta["routing_explainability"] = {
                    "agent_selection_reason": f"Task assigned manually to {agent.name}.",
                    "model_selection_reason": "",
                    "routing_inputs": {
                        "assignment_source": "manual_update",
                        "assigned_agent_id": assigned_agent_id,
                    },
                    "routing_policy_snapshot": {},
                    "agent_source": "manual_update",
                    "model_source": None,
                }
            else:
                next_meta.pop("routing_explainability", None)
            task.metadata_json = next_meta
            orm_attributes.flag_modified(task, "metadata_json")

        for field, value in updates.items():
            if field == "labels":
                task.labels_json = value
            elif field == "result_payload":
                task.result_payload_json = value
            elif field == "metadata":
                task.metadata_json = self._normalized_task_metadata(value)
            elif field == "dependency_ids":
                dependency_ids = list(value or [])
                await self._validate_task_dependencies(project_id, task.id, dependency_ids)
                await self.repo.replace_task_dependencies(task.id, dependency_ids)
            elif field == "github_secondary_repository_ids":
                sec_ids = [str(x).strip() for x in (value or []) if str(x).strip()]
                await self._validate_github_secondary_repository_ids(user, project_id, sec_ids)
                m = dict(task.metadata_json or {})
                m["github_secondary_repository_ids"] = sec_ids
                task.metadata_json = m
                orm_attributes.flag_modified(task, "metadata_json")
            elif field == "status":
                if value in {"completed", "approved"}:
                    acceptance = await self._check_task_acceptance_payload(task)
                    if not acceptance["passed"]:
                        raise HTTPException(
                            status_code=409,
                            detail={
                                "message": "Acceptance checks must pass before the task can be marked done.",
                                "checks": acceptance["checks"],
                            },
                        )
                if value in {"synced_to_github", "archived"}:
                    evidence = await self._check_task_evidence_bundle_payload(task, target_status=value)
                    if not evidence["passed"]:
                        raise HTTPException(
                            status_code=409,
                            detail={
                                "message": f"Evidence bundle must be complete before moving to {value}.",
                                "checks": evidence["checks"],
                            },
                        )
                terminal = {"completed", "archived", "synced_to_github"}
                if prev_status in terminal and value not in terminal:
                    m = dict(task.metadata_json or {})
                    m.pop("memory_checkpoint_compacted", None)
                    m.pop("memory_low_value_archived", None)
                    task.metadata_json = m
                    orm_attributes.flag_modified(task, "metadata_json")
                await self._transition_task_status(task, value, reason="manual update")
            elif field == "priority":
                setattr(task, field, _normalize_task_priority(str(value) if value is not None else None))
            else:
                setattr(task, field, value)
        await self.db.commit()
        await self.db.refresh(task)
        await self._queue_task_github_sync_from_internal_changes(user, task, prev_snapshot)
        await self._sync_knowledge_graph_for_task(project, task)
        if prev_status != task.status and task.status in {"completed", "archived", "synced_to_github"}:
            await self._maybe_promote_task_close_working_memory(user, project, task)
            await self.db.refresh(task)
            await self._run_task_close_memory_lifecycle(user, project, task)
            await self._enqueue_classifier_job_for_task(project, task)
        await self.db.commit()
        return task

    async def _validate_task_dependencies(
        self,
        project_id: str,
        task_id: str,
        dependency_ids: Sequence[str],
    ) -> None:
        normalized = [str(item) for item in dependency_ids if str(item).strip()]
        if len(set(normalized)) != len(normalized):
            raise HTTPException(status_code=409, detail="Duplicate task dependencies are not allowed.")
        if task_id in normalized:
            raise HTTPException(status_code=409, detail="A task cannot depend on itself.")

        tasks = await self.repo.list_tasks(project_id)
        task_ids = {item.id for item in tasks}
        missing = [dep_id for dep_id in normalized if dep_id not in task_ids]
        if missing:
            raise HTTPException(
                status_code=404,
                detail=f"Dependency tasks not found in this project: {', '.join(missing[:5])}",
            )

        dependencies = await self.repo.list_task_dependencies(project_id)
        adjacency: dict[str, list[str]] = {item.id: [] for item in tasks}
        for dep in dependencies:
            adjacency.setdefault(dep.task_id, []).append(str(dep.depends_on_task_id))
        adjacency[task_id] = normalized
        for dep_id in normalized:
            if self._task_dependency_path_exists(adjacency, dep_id, task_id):
                raise HTTPException(
                    status_code=409,
                    detail="Dependency update would create a cycle in the task DAG.",
                )

    def _task_dependency_path_exists(
        self,
        adjacency: dict[str, Sequence[str]],
        start_id: str,
        target_id: str,
    ) -> bool:
        stack = [start_id]
        seen: set[str] = set()
        while stack:
            current = stack.pop()
            if current == target_id:
                return True
            if current in seen:
                continue
            seen.add(current)
            stack.extend(str(item) for item in adjacency.get(current, []))
        return False

    async def delete_task(self, user: User, project_id: str, task_id: str):
        task = await self.get_task(user, project_id, task_id)
        await self.db.delete(task)
        await self.db.commit()

    def _task_effective_sla_deadline(self, task: OrchestratorTask) -> datetime | None:
        deadlines: list[datetime] = []
        if task.due_date:
            deadlines.append(task.due_date)
        if task.response_sla_hours and task.created_at:
            deadlines.append(task.created_at + timedelta(hours=int(task.response_sla_hours)))
        if not deadlines:
            return None
        return min(deadlines)

    async def _task_dependencies_met_for_run(self, task_id: str) -> bool:
        for dep in await self.repo.list_task_dependencies_for_task(task_id):
            dep_task = await self.repo.get_task_by_id(dep.depends_on_task_id)
            if dep_task and dep_task.status not in {"completed", "approved"}:
                return False
        return True

    async def list_dag_ready_tasks(self, user: User, project_id: str) -> list[dict[str, Any]]:
        await self.get_project(user, project_id)
        tasks = await self.repo.list_tasks(project_id)
        deps_all = await self.repo.list_task_dependencies(project_id)
        dep_count: dict[str, int] = {}
        for dep in deps_all:
            dep_count[dep.task_id] = dep_count.get(dep.task_id, 0) + 1
        ready: list[dict[str, Any]] = []
        ready_statuses = {"backlog", "planned"}
        for t in tasks:
            if t.status not in ready_statuses:
                continue
            if await self.repo.task_has_active_run(project_id, t.id):
                continue
            if not await self._task_dependencies_met_for_run(t.id):
                continue
            ready.append(
                {
                    "id": t.id,
                    "title": t.title,
                    "status": t.status,
                    "dependency_count": dep_count.get(t.id, 0),
                }
            )
        return ready

    async def start_parallel_dag_ready_runs(
        self,
        user: User,
        project_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        run_mode = str(payload.get("run_mode") or "single_agent")
        limit = min(max(int(payload.get("limit") or 8), 1), 24)
        filter_ids = payload.get("task_ids")
        base_input = dict(payload.get("input_payload") or {})
        ready = await self.list_dag_ready_tasks(user, project_id)
        if filter_ids:
            fid = {str(x) for x in filter_ids}
            ready = [r for r in ready if r["id"] in fid]
        started: list[str] = []
        skipped: list[str] = []
        messages: list[str] = []
        for row in ready[:limit]:
            try:
                run, _warnings = await self.start_task_run(
                    user,
                    project_id,
                    row["id"],
                    {"run_mode": run_mode, "input_payload": {**base_input, "dag_parallel_wave": True}},
                )
                started.append(run.id)
            except HTTPException as exc:
                skipped.append(row["id"])
                detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
                messages.append(f"{row['title']}: {detail}")
        return {"started_run_ids": started, "skipped_task_ids": skipped, "messages": messages}

    async def merge_resolution_preview(self, user: User, project_id: str, parent_task_id: str) -> dict[str, Any]:
        parent = await self.get_task(user, project_id, parent_task_id)
        children = await self.repo.list_subtasks(parent_task_id)
        branches: list[dict[str, Any]] = []
        for c in children:
            branches.append(
                {
                    "id": c.id,
                    "title": c.title,
                    "status": c.status,
                    "assigned_agent_id": c.assigned_agent_id,
                    "result_summary": c.result_summary,
                }
            )
        completed = [c for c in children if c.status in {"completed", "approved"}]
        agents = {c.assigned_agent_id for c in completed if c.assigned_agent_id}
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
        completed = [c for c in children if c.status in {"completed", "approved"}]
        if len(completed) < 2:
            raise HTTPException(
                status_code=400,
                detail="Merge resolution requires at least two completed subtasks under this parent.",
            )
        sources: list[dict[str, Any]] = []
        for c in completed:
            sources.append(
                {
                    "task_id": c.id,
                    "title": c.title,
                    "assigned_agent_id": c.assigned_agent_id,
                    "result_summary": c.result_summary,
                    "result_payload": c.result_payload_json,
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
            tasks = await self.repo.list_tasks(project.id)
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
                if await self.repo.count_pending_approvals_for_task(project.id, task.id, "sla_escalation") > 0:
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

    async def list_task_comments(self, user: User, project_id: str, task_id: str):
        await self.get_task(user, project_id, task_id)
        return await self.repo.list_task_comments(task_id)

    async def add_task_comment(self, user: User, project_id: str, task_id: str, body: str):
        await self.get_task(user, project_id, task_id)
        comment = await self.repo.create_task_comment(task_id=task_id, author_user_id=user.id, body=body)
        await self.db.commit()
        await self.db.refresh(comment)
        return comment

    async def list_task_timeline(self, user: User, project_id: str, task_id: str) -> list[dict[str, Any]]:
        await self.get_task(user, project_id, task_id)
        comments = await self.repo.list_task_comments(task_id)
        sync_events = await self.repo.list_sync_events_for_task(task_id)
        approvals = await self.repo.list_approvals_for_task(user.id, project_id, task_id)
        merged: list[dict[str, Any]] = []
        for c in comments:
            merged.append(
                {
                    "kind": "comment",
                    "id": c.id,
                    "created_at": c.created_at,
                    "title": "Task comment",
                    "body": c.body,
                    "detail": None,
                    "payload": {"author_user_id": c.author_user_id, "author_agent_id": c.author_agent_id},
                }
            )
        for approval in approvals:
            payload = dict(approval.payload_json or {})
            merged.append(
                {
                    "kind": "approval",
                    "id": approval.id,
                    "created_at": approval.created_at,
                    "title": approval.approval_type,
                    "body": payload.get("body") or payload.get("draft_comment"),
                    "detail": f"{approval.status} approval",
                    "payload": {
                        **payload,
                        "approval_status": approval.status,
                        "approval_type": approval.approval_type,
                    },
                }
            )
        for e in sync_events:
            merged.append(
                {
                    "kind": "github_sync",
                    "id": e.id,
                    "created_at": e.created_at,
                    "title": e.action,
                    "body": None,
                    "detail": e.detail,
                    "payload": e.payload_json or {},
                }
            )
        merged.sort(key=lambda row: row["created_at"])
        return merged

    async def _queue_task_github_sync_from_internal_changes(
        self,
        user: User,
        task: OrchestratorTask,
        prev_snapshot: dict[str, Any],
    ) -> None:
        if not task.github_issue_link_id:
            return
        issue_link = await self.db.get(GithubIssueLink, task.github_issue_link_id)
        if issue_link is None:
            return
        repository = await self.db.get(GithubRepository, issue_link.repository_id)
        project = await self.db.get(OrchestratorProject, task.project_id)
        if repository is None or project is None:
            return
        github = self._project_github_settings(project)
        issue_update: dict[str, Any] = {}
        if github.get("sync_state_to_github", True):
            next_state = self._task_state_to_github_issue_state(task)
            prev_state = (
                "closed"
                if prev_snapshot.get("status") in {"approved", "completed", "synced_to_github", "archived"}
                else "open"
            )
            if next_state != prev_state:
                issue_update["state"] = next_state
        if github.get("sync_labels_to_github", True):
            next_labels = [str(item) for item in (task.labels_json or [])]
            prev_labels = [str(item) for item in (prev_snapshot.get("labels") or [])]
            if next_labels != prev_labels:
                issue_update["labels"] = next_labels
        if github.get("sync_assignees_to_github", True):
            next_assignee = await self._task_assignee_login_for_github(task, project)
            prev_assignee = None
            prev_assignee_id = prev_snapshot.get("assigned_agent_id")
            if prev_assignee_id:
                shadow = SimpleNamespace(
                    assigned_agent_id=prev_assignee_id,
                    github_issue_link_id=task.github_issue_link_id,
                    project_id=task.project_id,
                )
                prev_assignee = await self._task_assignee_login_for_github(shadow, project)
            if next_assignee != prev_assignee:
                issue_update["assignees"] = [next_assignee] if next_assignee else []
        if github.get("sync_milestone_to_github", True):
            next_milestone = (task.metadata_json or {}).get("github_milestone_number")
            prev_milestone = (prev_snapshot.get("metadata") or {}).get("github_milestone_number")
            if next_milestone != prev_milestone:
                issue_update["milestone"] = next_milestone
        if not issue_update:
            return
        await self._create_github_write_approval(
            user_id=user.id,
            project_id=task.project_id,
            task_id=task.id,
            run_id=None,
            issue_link_id=issue_link.id,
            approval_type="github_issue_sync",
            payload_json={
                "repository_id": repository.id,
                "issue_number": issue_link.issue_number,
                "issue_update": issue_update,
            },
        )
        await self.repo.create_sync_event(
            repository_id=repository.id,
            issue_link_id=issue_link.id,
            action="sync_issue_fields_pending",
            status="pending",
            detail="Internal task changes queued for GitHub sync approval.",
            payload_json={"issue_update": issue_update, "task_id": task.id},
        )
        await self.db.commit()

    async def list_task_artifacts(self, user: User, project_id: str, task_id: str):
        await self.get_task(user, project_id, task_id)
        return await self.repo.list_task_artifacts(task_id)

    async def create_task_artifact(
        self,
        user: User,
        project_id: str,
        task_id: str,
        kind: str,
        title: str,
        content: str | None,
        metadata: dict,
    ) -> TaskArtifact:
        await self.get_task(user, project_id, task_id)
        artifact = await self.repo.create_task_artifact(
            task_id=task_id,
            kind=kind,
            title=title,
            content=content,
            metadata_json=metadata,
        )
        await self.db.commit()
        await self.db.refresh(artifact)
        return artifact

    async def list_subtasks(self, user: User, project_id: str, task_id: str) -> list[OrchestratorTask]:
        await self.get_task(user, project_id, task_id)
        return await self.repo.list_subtasks(task_id)

    async def decompose_task(
        self,
        user: User,
        project_id: str,
        task_id: str,
        max_subtasks: int = 5,
        context: str | None = None,
    ) -> list[OrchestratorTask]:
        parent = await self.get_task(user, project_id, task_id)
        project = await self.get_project(user, project_id)
        existing = await self.repo.list_subtasks(task_id)
        if existing:
            raise HTTPException(
                status_code=409,
                detail="Task already has subtasks. Update or archive the existing branch plan before decomposing again.",
            )
        blueprint = self._generate_subtask_blueprint(parent, max_subtasks=max_subtasks, context=context)
        subtasks = []
        for i, item in enumerate(blueprint):
            position = await self.repo.get_next_task_position(project_id)
            task = await self.repo.create_task(
                project_id=project_id,
                created_by_user_id=user.id,
                title=str(item["title"]),
                description=str(item["description"]),
                source="decompose",
                task_type=parent.task_type,
                priority=parent.priority,
                status="backlog",
                parent_task_id=task_id,
                position=position,
                labels_json=list(item.get("labels") or []),
                result_payload_json={},
                metadata_json={
                    "parallelizable": bool(item.get("parallelizable", False)),
                    "required_tools": list(item.get("required_tools") or []),
                    "blueprint_kind": item.get("kind"),
                },
                acceptance_criteria=item.get("acceptance_criteria"),
            )
            subtasks.append(task)
        for index, task in enumerate(subtasks):
            dependency_indexes = list(blueprint[index].get("dependency_indexes") or [])
            dependency_ids = [
                subtasks[dep_index].id
                for dep_index in dependency_indexes
                if 0 <= dep_index < len(subtasks)
            ]
            await self.repo.replace_task_dependencies(task.id, dependency_ids)
        await self.db.commit()
        for t in subtasks:
            await self.db.refresh(t)
            await self._sync_knowledge_graph_for_task(project, t)
        await self.db.commit()
        return subtasks

    async def check_task_acceptance(self, user: User, project_id: str, task_id: str) -> dict:
        task = await self.get_task(user, project_id, task_id)
        return await self._check_task_acceptance_payload(task)

    def _task_acceptance_checker_config(self, task: OrchestratorTask | Any) -> dict[str, Any]:
        meta = dict(getattr(task, "metadata_json", None) or {})
        raw = meta.get("acceptance_checker")
        config = raw if isinstance(raw, dict) else {}
        required_artifact_kinds = config.get("required_artifact_kinds")
        return {
            "required_artifact_kinds": [
                str(item).strip()
                for item in (required_artifact_kinds if isinstance(required_artifact_kinds, list) else [])
                if str(item).strip()
            ],
            "require_github_comment": bool(config.get("require_github_comment", False)),
            "require_github_pr": bool(config.get("require_github_pr", False)),
            "require_reviewer_approval": bool(config.get("require_reviewer_approval", False)),
        }

    async def _check_task_acceptance_payload(self, task: OrchestratorTask) -> dict:
        checks: list[dict] = []
        config = self._task_acceptance_checker_config(task)

        output_text = self._task_output_text(task)
        has_output = bool(output_text.strip())
        checks.append(
            {
                "name": "has_output",
                "passed": has_output,
                "detail": "Task has output summary or payload" if has_output else "No task output yet",
            }
        )

        valid_statuses = {"completed", "needs_review"}
        in_valid_status = task.status in valid_statuses
        checks.append(
            {
                "name": "valid_status",
                "passed": in_valid_status,
                "detail": f"Status is '{task.status}'"
                if in_valid_status
                else f"Status '{task.status}' is not a terminal state",
            }
        )

        dep_rows = await self.repo.list_task_dependencies_for_task(task.id)
        if dep_rows:
            incomplete_count = 0
            for dep in dep_rows:
                dep_task = await self.repo.get_task_by_id(dep.depends_on_task_id)
                if dep_task and dep_task.status not in {"completed", "approved"}:
                    incomplete_count += 1
            deps_done = incomplete_count == 0
            checks.append(
                {
                    "name": "dependencies_complete",
                    "passed": deps_done,
                    "detail": "All dependencies completed"
                    if deps_done
                    else f"{incomplete_count} dependencies not yet complete",
                }
            )
        else:
            checks.append({"name": "dependencies_complete", "passed": True, "detail": "No dependencies"})

        criteria_items = self._acceptance_criteria_items(task.acceptance_criteria or "")
        if criteria_items:
            item_checks = [self._acceptance_item_check(item, output_text) for item in criteria_items]
            missing = [item["item"] for item in item_checks if not item["passed"]]
            checks.append(
                {
                    "name": "acceptance_criteria",
                    "passed": len(missing) == 0,
                    "detail": "All acceptance criteria matched output."
                    if not missing
                    else f"Missing acceptance evidence for {len(missing)} item(s): {', '.join(missing[:3])}",
                    "items": item_checks,
                }
            )
        else:
            checks.append(
                {
                    "name": "acceptance_criteria",
                    "passed": False,
                    "detail": "No acceptance criteria defined.",
                    "items": [],
                }
            )

        if (getattr(task, "metadata_json", None) or {}).get("latest_reopen"):
            checks.append(
                {
                    "name": "reopen_items_resolved",
                    "passed": False,
                    "detail": "Latest review requested rework; rerun after addressing checklist items.",
                }
            )
        else:
            checks.append(
                {
                    "name": "reopen_items_resolved",
                    "passed": True,
                    "detail": "No outstanding rework checklist.",
                }
            )

        list_task_artifacts = getattr(self.repo, "list_task_artifacts", None)
        artifacts = await list_task_artifacts(task.id) if callable(list_task_artifacts) else []
        present_artifact_kinds = sorted(
            {
                str(getattr(item, "kind", "") or "").strip()
                for item in artifacts
                if str(getattr(item, "kind", "") or "").strip()
            }
        )
        if config["required_artifact_kinds"]:
            missing = [kind for kind in config["required_artifact_kinds"] if kind not in present_artifact_kinds]
            checks.append(
                {
                    "name": "required_artifacts",
                    "passed": len(missing) == 0,
                    "detail": "All required artifact kinds are present."
                    if not missing
                    else f"Missing required artifact kinds: {', '.join(missing)}",
                    "required_artifact_kinds": config["required_artifact_kinds"],
                    "present_artifact_kinds": present_artifact_kinds,
                }
            )

        list_sync_events_for_task = getattr(self.repo, "list_sync_events_for_task", None)
        sync_events = await list_sync_events_for_task(task.id) if callable(list_sync_events_for_task) else []
        if config["require_github_comment"]:
            has_comment = any(
                "comment" in str(getattr(event, "action", "") or "").lower()
                and str(getattr(event, "status", "") or "").lower()
                in {"completed", "sent", "success", "approved"}
                for event in sync_events
            )
            checks.append(
                {
                    "name": "github_comment",
                    "passed": has_comment,
                    "detail": "GitHub comment evidence found."
                    if has_comment
                    else "Required GitHub comment evidence was not found.",
                }
            )

        if config["require_github_pr"]:
            has_pr = any(
                (
                    "pull_request" in str(getattr(event, "action", "") or "").lower()
                    or "create_pr" in str(getattr(event, "action", "") or "").lower()
                )
                and str(getattr(event, "status", "") or "").lower()
                in {"completed", "sent", "success", "approved"}
                for event in sync_events
            )
            checks.append(
                {
                    "name": "github_pr",
                    "passed": has_pr,
                    "detail": "GitHub PR evidence found."
                    if has_pr
                    else "Required GitHub PR evidence was not found.",
                }
            )

        if config["require_reviewer_approval"]:
            reviewer_ok = task.status in {"approved", "completed", "synced_to_github"} or bool(
                getattr(task, "approved_by_user_id", None)
            )
            checks.append(
                {
                    "name": "reviewer_approval",
                    "passed": reviewer_ok,
                    "detail": "Reviewer approval recorded."
                    if reviewer_ok
                    else "Reviewer approval is required before completion.",
                }
            )

        return {
            "task_id": task.id,
            "passed": all(c["passed"] for c in checks),
            "config": config,
            "checks": checks,
        }

    def _routing_explainability_from_payload(self, payload: dict[str, Any] | None) -> dict[str, Any]:
        raw = ((payload or {}).get("orchestration_meta") if isinstance(payload, dict) else None) or {}
        if not isinstance(raw, dict):
            return {}
        return {
            "agent_selection_reason": str(
                raw.get("agent_selection_reason") or raw.get("worker_agent_rationale") or ""
            ),
            "model_selection_reason": str(raw.get("model_selection_reason") or raw.get("model_rationale") or ""),
            "routing_inputs": raw.get("routing_inputs")
            if isinstance(raw.get("routing_inputs"), dict)
            else {},
            "routing_policy_snapshot": raw.get("routing_policy_snapshot")
            if isinstance(raw.get("routing_policy_snapshot"), dict)
            else {},
            "agent_source": raw.get("worker_agent_id_source"),
            "model_source": raw.get("model_source"),
        }

    def _routing_explainability_from_task_metadata(self, task: OrchestratorTask | Any) -> dict[str, Any]:
        meta = dict(getattr(task, "metadata_json", None) or {})
        raw = meta.get("routing_explainability")
        return raw if isinstance(raw, dict) else {}

    async def _changed_artifacts_payload(
        self,
        task_id: str,
        *,
        run_id: str | None = None,
        limit: int = 6,
    ) -> list[dict[str, Any]]:
        list_task_artifacts = getattr(self.repo, "list_task_artifacts", None)
        if not callable(list_task_artifacts):
            return []
        rows = await list_task_artifacts(task_id)
        filtered = [row for row in rows if run_id is None or getattr(row, "run_id", None) == run_id]
        return [
            {
                "id": row.id,
                "run_id": row.run_id,
                "kind": row.kind,
                "title": row.title,
                "created_at": row.created_at,
            }
            for row in filtered[:limit]
        ]

    def _task_output_text(self, task: OrchestratorTask | Any) -> str:
        payload = getattr(task, "result_payload_json", None) or {}
        summary = getattr(task, "result_summary", None) or ""
        if not summary and isinstance(payload, dict):
            summary = str(payload.get("summary") or payload.get("final_output") or "")
        return "\n".join(
            chunk
            for chunk in [
                str(summary).strip(),
                json.dumps(payload, default=str) if payload else "",
            ]
            if chunk
        )

    def _acceptance_criteria_items(self, text: str) -> list[str]:
        items: list[str] = []
        for raw_line in str(text or "").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            normalized = re.sub(r"^[-*]\s+", "", line)
            normalized = re.sub(r"^\d+\.\s+", "", normalized)
            if normalized:
                items.append(normalized)
        if not items and str(text or "").strip():
            items.append(str(text).strip())
        return items

    def _acceptance_item_matches_output(self, item: str, output_text: str) -> bool:
        return self._acceptance_item_check(item, output_text)["passed"]

    def _acceptance_item_check(self, item: str, output_text: str) -> dict[str, Any]:
        required_tokens = [token for token in re.findall(r"[a-z0-9]+", item.lower()) if len(token) > 2]
        if not required_tokens:
            return {"item": item, "passed": True, "evidence_excerpt": ""}
        output_tokens = set(re.findall(r"[a-z0-9]+", output_text.lower()))
        overlap = sum(1 for token in required_tokens if token in output_tokens)
        passed = overlap >= max(1, math.ceil(len(required_tokens) * 0.5))
        return {
            "item": item,
            "passed": passed,
            "evidence_excerpt": self._acceptance_evidence_excerpt(item, output_text) if passed else "",
        }

    def _acceptance_evidence_excerpt(self, item: str, output_text: str) -> str:
        lowered = output_text.lower()
        for token in re.findall(r"[a-z0-9]+", item.lower()):
            if len(token) <= 2:
                continue
            index = lowered.find(token)
            if index >= 0:
                start = max(0, index - 40)
                end = min(len(output_text), index + 120)
                return output_text[start:end].strip()
        return output_text[:160].strip()

    def _normalized_external_links(self, raw: Any) -> list[dict[str, str]]:
        if not isinstance(raw, list):
            return []
        rows: list[dict[str, str]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "").strip()
            label = str(item.get("label") or "").strip()
            if not url or not label:
                continue
            kind = str(item.get("kind") or "other").strip().lower()
            if kind not in EXTERNAL_LINK_KINDS:
                kind = "other"
            row_id = str(item.get("id") or uuid.uuid4()).strip()
            rows.append(
                {
                    "id": row_id,
                    "kind": kind,
                    "label": label[:255],
                    "url": url[:2000],
                    "notes": str(item.get("notes") or "").strip()[:500],
                }
            )
        return rows

    def _normalized_task_metadata(self, raw: Any) -> dict[str, Any]:
        meta = dict(raw or {}) if isinstance(raw, dict) else {}
        meta["external_links"] = self._normalized_external_links(meta.get("external_links"))
        bundle_raw = meta.get("evidence_bundle")
        bundle = dict(bundle_raw) if isinstance(bundle_raw, dict) else {}
        bundle["accepted_artifact_ids"] = [
            str(item).strip()
            for item in (bundle.get("accepted_artifact_ids") or [])
            if str(item).strip()
        ]
        bundle["accepted_external_link_ids"] = [
            str(item).strip()
            for item in (bundle.get("accepted_external_link_ids") or [])
            if str(item).strip()
        ]
        reviewer_decision = bundle.get("reviewer_decision")
        bundle["reviewer_decision"] = (
            dict(reviewer_decision) if isinstance(reviewer_decision, dict) else {}
        )
        bundle["sync_summary"] = str(bundle.get("sync_summary") or "").strip()
        meta["evidence_bundle"] = bundle
        return meta

    async def _check_task_evidence_bundle_payload(
        self,
        task: OrchestratorTask | Any,
        *,
        target_status: str,
    ) -> dict[str, Any]:
        metadata = dict(getattr(task, "metadata_json", None) or {})
        links = self._normalized_external_links(metadata.get("external_links"))
        bundle = metadata.get("evidence_bundle")
        if not isinstance(bundle, dict):
            bundle = {}
        accepted_artifact_ids = {
            str(item).strip()
            for item in (bundle.get("accepted_artifact_ids") or [])
            if str(item).strip()
        }
        accepted_external_link_ids = {
            str(item).strip()
            for item in (bundle.get("accepted_external_link_ids") or [])
            if str(item).strip()
        }
        reviewer_decision = (
            dict(bundle.get("reviewer_decision"))
            if isinstance(bundle.get("reviewer_decision"), dict)
            else {}
        )
        sync_summary = str(bundle.get("sync_summary") or "").strip()
        artifacts = await self.repo.list_task_artifacts(task.id)
        artifact_ids = {
            str(getattr(item, "id", "")).strip()
            for item in artifacts
            if str(getattr(item, "id", "")).strip()
        }
        link_ids = {str(item.get("id") or "").strip() for item in links if str(item.get("id") or "").strip()}
        checks = [
            {
                "name": "accepted_artifacts",
                "passed": bool(accepted_artifact_ids & artifact_ids),
                "detail": "Accepted artifacts selected."
                if accepted_artifact_ids & artifact_ids
                else "Select at least one accepted artifact for final evidence.",
            },
            {
                "name": "accepted_external_links",
                "passed": bool(accepted_external_link_ids & link_ids),
                "detail": "Accepted external links selected."
                if accepted_external_link_ids & link_ids
                else "Select at least one accepted external link for final evidence.",
            },
            {
                "name": "reviewer_decision",
                "passed": bool(str(reviewer_decision.get("status") or "").strip()),
                "detail": "Reviewer decision recorded."
                if str(reviewer_decision.get("status") or "").strip()
                else "Record reviewer decision before final sync/archive.",
            },
        ]
        if target_status == "synced_to_github":
            checks.append(
                {
                    "name": "sync_summary",
                    "passed": bool(sync_summary),
                    "detail": "Sync summary recorded."
                    if sync_summary
                    else "Add sync summary before moving to synced_to_github.",
                }
            )
        if target_status == "archived":
            checks.append(
                {
                    "name": "archive_summary",
                    "passed": bool(sync_summary) or getattr(task, "status", "") == "synced_to_github",
                    "detail": "Archive summary or prior GitHub sync recorded."
                    if bool(sync_summary) or getattr(task, "status", "") == "synced_to_github"
                    else "Archive needs sync summary or prior synced_to_github state.",
                }
            )
        return {
            "task_id": task.id,
            "passed": all(item["passed"] for item in checks),
            "checks": checks,
        }

    def _generate_subtask_blueprint(
        self,
        parent: OrchestratorTask | Any,
        *,
        max_subtasks: int,
        context: str | None = None,
    ) -> list[dict[str, Any]]:
        criteria = self._acceptance_criteria_items(getattr(parent, "acceptance_criteria", "") or "")
        task_title = str(getattr(parent, "title", "Task")).strip()
        task_type = str(getattr(parent, "task_type", "general")).strip()
        shared_context = f"Context: {context}\n\n" if context else ""
        criteria_text = " ".join(criteria).lower()
        wants_docs = any(token in criteria_text for token in ["document", "docs", "adr", "summary"])
        wants_tests = any(token in criteria_text for token in ["test", "verify", "validation", "qa"])
        plan: list[dict[str, Any]] = [
            {
                "kind": "plan",
                "title": f"Plan scope for {task_title}",
                "description": f"{shared_context}Define the execution plan, assumptions, and dependency/risk map for this {task_type} task.",
                "dependency_indexes": [],
                "parallelizable": False,
                "required_tools": ["fs_read"],
                "labels": ["planning"],
                "acceptance_criteria": "Document execution plan, assumptions, and risks.",
            }
        ]
        if criteria:
            plan.append(
                {
                    "kind": "implement",
                    "title": f"Implement core work for {task_title}",
                    "description": f"{shared_context}Deliver the main implementation required by the task and cover these criteria:\n- "
                    + "\n- ".join(criteria[:4]),
                    "dependency_indexes": [0],
                    "parallelizable": False,
                    "required_tools": ["code_execute"],
                    "labels": ["implementation"],
                    "acceptance_criteria": "\n".join(criteria[: min(3, len(criteria))]),
                }
            )
        else:
            plan.append(
                {
                    "kind": "implement",
                    "title": f"Implement {task_title}",
                    "description": f"{shared_context}Ship the main implementation for this task.",
                    "dependency_indexes": [0],
                    "parallelizable": False,
                    "required_tools": ["code_execute"],
                    "labels": ["implementation"],
                    "acceptance_criteria": "Primary implementation completed.",
                }
            )
        if wants_tests or max_subtasks >= 3:
            plan.append(
                {
                    "kind": "verify",
                    "title": f"Verify and test {task_title}",
                    "description": f"{shared_context}Run tests, validate acceptance criteria, and record any follow-up issues.",
                    "dependency_indexes": [1],
                    "parallelizable": False,
                    "required_tools": ["code_execute"],
                    "labels": ["testing"],
                    "acceptance_criteria": "Tests pass and acceptance criteria are validated.",
                }
            )
        if wants_docs or max_subtasks >= 4:
            plan.append(
                {
                    "kind": "document",
                    "title": f"Document rollout for {task_title}",
                    "description": f"{shared_context}Capture the final summary, operator notes, and any rollout caveats.",
                    "dependency_indexes": [1],
                    "parallelizable": True,
                    "required_tools": ["fs_write"],
                    "labels": ["documentation"],
                    "acceptance_criteria": "Documentation and rollout notes are updated.",
                }
            )
        return plan[:max_subtasks]

    async def ingest_incident_alert(self, user: User, payload: dict[str, Any]) -> OrchestratorTask:
        project_id = str(payload.get("project_id") or "")
        project = await self.get_project(user, project_id)
        source = str(payload.get("source") or "webhook")
        title = str(payload.get("title") or "Incident alert")
        body = str(payload.get("body") or "")
        severity = str(payload.get("severity") or "high")
        task = await self.create_task(
            user,
            project.id,
            {
                "title": f"[Incident:{severity}] {title}",
                "description": body,
                "priority": "urgent" if severity in {"critical", "sev1"} else "high",
                "task_type": "incident",
                "status": "planned",
                "metadata": {"incident_source": source, "alert_payload": payload},
            },
        )
        return task
