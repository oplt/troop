from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import attributes as orm_attributes

from backend.core.cache import redis_client
from backend.core.config import settings
from backend.core.logging import get_logger
from backend.modules.identity_access.models import User
from backend.modules.memory.working_memory import EXECUTION_THREAD_ID_KEY
from backend.modules.orchestration._helpers import BlockedExecution
from backend.modules.orchestration.constants import TASK_TRANSITIONS
from backend.modules.orchestration.execution.durable_execution import (
    is_run_execution_claimable,
)
from backend.modules.orchestration.execution.execution_state import (
    EXECUTION_SNAPSHOT_SCHEMA_VERSION,
    EXECUTION_TRUTH_DESCRIPTION,
    SNAPSHOT_SOURCES_RUN,
    SNAPSHOT_SOURCES_TASK,
    checkpoint_excerpt,
    extract_execution_memory_details,
    extract_execution_metadata_views,
)
from backend.modules.orchestration.execution.execution_workflow import (
    consume_signal_queue,
    current_step,
    durable_handle,
    enqueue_signal,
    ensure_workflow_state,
    get_workflow_artifact,
    increment_resume_count,
    mark_step,
    set_workflow_artifact,
    summarize_trace,
    update_query_snapshot,
    workflow_state,
)
from backend.modules.orchestration.execution.policies import (
    is_valid_task_transition,
    next_retry_numbers,
)
from backend.modules.orchestration.models import ProviderConfig, TaskRun
from backend.modules.orchestration.tools import OrchestrationToolbox, ToolExecutionError
from backend.modules.projects.orchestration_models import (
    OrchestratorProject,
    OrchestratorTask,
)
from backend.modules.team.models import AgentProfile

logger = get_logger(__name__)


class OrchestrationExecutionServiceMixin:
    async def list_task_runs(self, user: User, project_id: str | None = None):
        return await self.repo.list_runs(user.id, project_id)

    async def get_run(self, user: User, run_id: str):
        run = await self.repo.get_run(user.id, run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        return run

    async def _consume_hitl_grant(
        self,
        run: TaskRun,
        approval_type: str,
        expected_payload: dict[str, Any] | None = None,
    ) -> bool:
        """Consume one approved action grant while resuming a blocked run.

        Approval decisions are durable records, not an in-memory bypass. A grant is
        matched to the exact run/action and marked consumed before the protected
        operation proceeds, preventing a later retry from reusing it accidentally.
        """
        expected = dict(expected_payload or {})
        approvals = await self.repo.list_approvals_for_run(run.id, status="approved")
        for approval in approvals:
            if approval.approval_type != approval_type:
                continue
            payload = dict(approval.payload_json or {})
            if payload.get("_consumed_at"):
                continue
            if any(payload.get(key) != value for key, value in expected.items()):
                continue
            payload["_consumed_at"] = datetime.now(UTC).isoformat()
            approval.payload_json = payload
            await self._emit_run_event(
                run,
                event_type="approval_grant_consumed",
                message=f"Consumed approved HITL action: {approval_type}.",
                payload={"approval_id": approval.id, "approval_type": approval_type},
            )
            return True
        return False

    def _run_event_tail_payloads(
        self, events: list[Any], *, limit: int = 12
    ) -> list[dict[str, Any]]:
        tail = events[-limit:] if len(events) > limit else events
        out: list[dict[str, Any]] = []
        for e in tail:
            msg = e.message or ""
            if len(msg) > 400:
                msg = msg[:400] + "…"
            out.append(
                {
                    "event_type": e.event_type,
                    "level": e.level,
                    "message": msg,
                    "created_at": e.created_at,
                }
            )
        return out

    def _workflow_steps_for_run(self, run: TaskRun) -> list[dict[str, Any]]:
        if run.run_mode == "manager_worker":
            return [
                {"id": "planning", "title": "Planning", "actor": "supervisor"},
                {"id": "subtask_dispatch", "title": "Subtask dispatch", "actor": "supervisor"},
                {"id": "worker_execution", "title": "Worker execution", "actor": "worker_pool"},
                {"id": "blocker_resolution", "title": "Blocker resolution", "actor": "supervisor"},
                {"id": "review", "title": "Review", "actor": "reviewer"},
                {"id": "artifact_publish", "title": "Artifact publish", "actor": "system"},
                {"id": "github_sync", "title": "GitHub sync", "actor": "system"},
            ]
        if run.run_mode == "review":
            return [
                {"id": "review", "title": "Review", "actor": "reviewer"},
                {"id": "artifact_publish", "title": "Artifact publish", "actor": "system"},
                {"id": "github_sync", "title": "GitHub sync", "actor": "system"},
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

    def _stage_state_payload(self, run: TaskRun) -> dict[str, Any]:
        return {
            "manager_plan": self._workflow_checkpoint_artifact(run, "manager_worker.plan", {}),
            "routed_sub_tasks": self._workflow_checkpoint_artifact(
                run, "manager_worker.routed_sub_tasks", []
            ),
            "branch_results": self._workflow_checkpoint_artifact(
                run, "manager_worker.branch_results", []
            ),
            "review": self._workflow_checkpoint_artifact(run, "manager_worker.review_state", {}),
            "github_sync": self._workflow_checkpoint_artifact(
                run, "manager_worker.github_action_state", {}
            ),
        }

    async def _create_child_run(
        self,
        parent_run: TaskRun,
        *,
        sub_task: dict[str, Any],
        assigned_agent_id: str | None,
    ) -> TaskRun:
        child = await self.repo.create_run(
            parent_run_id=parent_run.id,
            project_id=parent_run.project_id,
            task_id=parent_run.task_id,
            triggered_by_user_id=parent_run.triggered_by_user_id,
            orchestrator_agent_id=parent_run.orchestrator_agent_id,
            worker_agent_id=assigned_agent_id,
            reviewer_agent_id=parent_run.reviewer_agent_id,
            provider_config_id=parent_run.provider_config_id,
            brainstorm_id=parent_run.brainstorm_id,
            run_mode="single_agent",
            status="queued",
            model_name=parent_run.model_name,
            input_payload_json={
                "subtask": sub_task,
                "parent_run_id": parent_run.id,
                "orchestration_meta": {
                    "branch_id": sub_task.get("branch_id"),
                    "branch_title": sub_task.get("title"),
                    "parent_run_id": parent_run.id,
                    "routing_reason": sub_task.get("routing_reason"),
                    "dependency_ids": sub_task.get("dependency_ids") or [],
                },
            },
        )
        child.checkpoint_json = ensure_workflow_state(
            child.checkpoint_json,
            run_mode=child.run_mode,
            steps=self._workflow_steps_for_run(child),
            run_id=child.id,
        )
        return child

    def _normalize_subtask_graph(
        self,
        sub_tasks: list[dict[str, Any]],
        *,
        parent_task: OrchestratorTask | None,
    ) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for index, item in enumerate(sub_tasks):
            branch_id = str(
                item.get("branch_id") or item.get("id") or f"branch-{index + 1}"
            ).strip()
            dep_indexes = (
                item.get("dependency_indexes")
                if isinstance(item.get("dependency_indexes"), list)
                else []
            )
            dep_ids = [
                str(item_id).strip()
                for item_id in (item.get("dependency_ids") or [])
                if str(item_id).strip()
            ]
            for dep_index in dep_indexes:
                if isinstance(dep_index, int) and 0 <= dep_index < len(sub_tasks):
                    dep_branch_id = str(
                        sub_tasks[dep_index].get("branch_id")
                        or sub_tasks[dep_index].get("id")
                        or f"branch-{dep_index + 1}"
                    ).strip()
                    if dep_branch_id and dep_branch_id not in dep_ids:
                        dep_ids.append(dep_branch_id)
            normalized.append(
                {
                    "branch_id": branch_id,
                    "title": str(item.get("title") or f"Subtask {index + 1}"),
                    "description": str(item.get("description") or ""),
                    "acceptance_criteria": str(
                        item.get("acceptance_criteria")
                        or (parent_task.acceptance_criteria if parent_task else "")
                        or ""
                    ),
                    "required_tools": [
                        str(x) for x in (item.get("required_tools") or []) if str(x).strip()
                    ],
                    "required_capabilities": [
                        str(x) for x in (item.get("required_capabilities") or []) if str(x).strip()
                    ],
                    "parallelizable": bool(item.get("parallelizable", False)),
                    "manager_notes": str(item.get("manager_notes") or ""),
                    "dependency_ids": dep_ids,
                    "tool_calls": list(item.get("tool_calls") or []),
                    "rework_scope": list(item.get("rework_scope") or []),
                }
            )
        return normalized

    def _worker_result_contract(
        self,
        sub_task: dict[str, Any],
        output_text: str,
        output_json: dict[str, Any] | None,
    ) -> dict[str, Any]:
        payload = dict(output_json or {})
        status = str(payload.get("status") or "completed").strip().lower()
        if status not in {"completed", "blocked", "failed"}:
            status = "completed"
        changed_files = payload.get("changed_files")
        if not isinstance(changed_files, list):
            changed_files = []
        risks = payload.get("risks")
        if not isinstance(risks, list):
            risks = []
        evidence_refs = payload.get("evidence_refs")
        if not isinstance(evidence_refs, list):
            evidence_refs = []
        return {
            "status": status,
            "summary": str(payload.get("summary") or output_text[:1200]),
            "completion_status": status,
            "changed_files": [str(x) for x in changed_files if str(x).strip()],
            "risks": [str(x) for x in risks if str(x).strip()],
            "evidence_refs": [str(x) for x in evidence_refs if str(x).strip()],
            "blocker_reason": str(payload.get("blocker_reason") or ""),
            "rework_scope": [
                str(x)
                for x in (payload.get("rework_scope") or sub_task.get("rework_scope") or [])
                if str(x).strip()
            ],
            "raw_output": output_text,
        }

    def _review_state_from_payload(
        self, review_payload: dict[str, Any], *, round_number: int
    ) -> dict[str, Any]:
        return {
            "round": round_number,
            "decision": str(review_payload.get("decision") or "rework"),
            "summary": str(review_payload.get("summary") or "")[:1200],
            "reasons": [str(x) for x in (review_payload.get("reasons") or []) if str(x).strip()],
            "checklist": [
                str(x) for x in (review_payload.get("checklist") or []) if str(x).strip()
            ],
            "rework_scope": [
                str(x) for x in (review_payload.get("rework_scope") or []) if str(x).strip()
            ],
            "last_reviewed_at": datetime.now(UTC).isoformat(),
        }

    async def _publish_final_artifacts(
        self,
        run: TaskRun,
        *,
        branch_results: list[dict[str, Any]],
        review_state: dict[str, Any],
    ) -> list[dict[str, Any]]:
        created: list[dict[str, Any]] = []
        final_output = str(
            run.output_payload_json.get("final_output")
            or run.output_payload_json.get("summary")
            or ""
        )
        review_text = json.dumps(review_state, indent=2, default=str)
        evidence_payload = {
            "branches": [
                {
                    "branch_id": item.get("branch_id"),
                    "title": item.get("title"),
                    "status": item.get("status"),
                    "changed_files": item.get("changed_files") or [],
                    "risks": item.get("risks") or [],
                    "evidence_refs": item.get("evidence_refs") or [],
                    "child_run_id": item.get("child_run_id"),
                }
                for item in branch_results
            ],
            "review": review_state,
        }
        for kind, title, content in [
            (
                "summary",
                "Manager summary",
                str(run.output_payload_json.get("summary") or final_output)[:5000],
            ),
            ("implementation", "Implementation bundle", final_output[:12000]),
            (
                "evidence",
                "Evidence bundle",
                json.dumps(evidence_payload, indent=2, default=str)[:12000],
            ),
            ("review", "Reviewer verdict", review_text[:12000]),
        ]:
            await self._write_artifact(
                run,
                kind=kind,
                title=title,
                content=content,
                metadata={"parent_run_id": run.id},
            )
            created.append({"kind": kind, "title": title})
        return created

    def _run_is_resumable(self, run: TaskRun) -> bool:
        if run.status not in {"failed", "blocked"}:
            return False
        step = current_step(run.checkpoint_json)
        return bool(step and step.get("resumable", True))

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
        state = self._ensure_run_workflow(run)
        migration = dict(state.get("migration") or {})
        return {
            "workflow_id": state.get("workflow_id"),
            "backend": state.get("backend"),
            "schema_version": state.get("schema_version"),
            "status": state.get("status"),
            "execution_handle": durable_handle(run.checkpoint_json),
            "current_step_id": state.get("current_step_id"),
            "last_completed_step_id": state.get("last_completed_step_id"),
            "resume_count": int(state.get("resume_count") or 0),
            "recovery_count": int(state.get("recovery_count") or 0),
            "last_failure": dict(state.get("last_failure") or {}),
            "signal_queue": list(state.get("signal_queue") or []),
            "signal_history": list(state.get("signal_history") or [])[-20:],
            "query_snapshot": dict(state.get("query_snapshot") or {}),
            "migration": {
                "strategy": str(migration.get("strategy") or "checkpoint-first coexistence"),
                "current_schema_version": str(
                    migration.get("current_schema_version") or state.get("schema_version") or "2.0"
                ),
                "source_checkpoint_versions": list(
                    migration.get("source_checkpoint_versions")
                    or [state.get("schema_version") or "2.0"]
                ),
                "external_backend_ready": bool(migration.get("external_backend_ready")),
            },
            "resumable": self._run_is_resumable(run),
        }

    async def get_task_execution_snapshot(
        self, user: User, project_id: str, task_id: str
    ) -> dict[str, Any]:
        """Compose Layer-1 execution snapshot from Postgres only (no embedding search)."""
        task = await self.get_task(user, project_id, task_id)
        active_runs = await self.repo.list_active_runs_for_task(project_id, task_id)
        pending_approvals = await self.repo.list_pending_approvals_for_task(
            user.id, project_id, task_id
        )
        sync_all = await self.repo.list_sync_events_for_task(task_id)
        pending_sync = [e for e in sync_all if e.status in ("queued", "pending")]
        pending_sync = pending_sync[-10:]

        latest = await self.repo.get_latest_run_for_task(project_id, task_id)
        focal = active_runs[0] if active_runs else latest
        child_runs = await self._child_runs_for_parent(focal.id) if focal else []
        events_tail: list[dict[str, Any]] = []
        cp_excerpt: dict[str, Any] = {}
        if focal:
            raw_events = await self.repo.list_run_events(focal.id)
            events_tail = self._run_event_tail_payloads(raw_events, limit=8)
            cp_excerpt = checkpoint_excerpt(focal.checkpoint_json)

        meta = {
            "schema_version": EXECUTION_SNAPSHOT_SCHEMA_VERSION,
            "execution_truth": EXECUTION_TRUTH_DESCRIPTION,
            "sources_read": list(SNAPSHOT_SOURCES_TASK),
        }
        acceptance_summary = await self._check_task_acceptance_payload(task)
        execution_memory = extract_execution_memory_details(task.metadata_json)
        changed_artifacts = await self._changed_artifacts_payload(
            task.id,
            run_id=latest.id if latest else None,
        )
        stage_state = self._stage_state_payload(focal) if focal else {}
        return {
            "meta": meta,
            "project_id": project_id,
            "task_id": task_id,
            "task_status": task.status,
            "task_title": task.title,
            "has_active_run": bool(active_runs),
            "active_runs": [
                {
                    "id": r.id,
                    "status": r.status,
                    "run_mode": r.run_mode,
                    "attempt_number": r.attempt_number,
                    "retry_count": r.retry_count,
                    "started_at": r.started_at,
                    "created_at": r.created_at,
                    "error_message": r.error_message,
                }
                for r in active_runs
            ],
            "pending_approvals": [
                {
                    "id": a.id,
                    "approval_type": a.approval_type,
                    "run_id": a.run_id,
                    "task_id": a.task_id,
                    "reason": a.reason,
                    "created_at": a.created_at,
                }
                for a in pending_approvals
            ],
            "pending_github_sync": [
                {
                    "id": e.id,
                    "action": e.action,
                    "status": e.status,
                    "detail": e.detail,
                    "created_at": e.created_at,
                }
                for e in pending_sync
            ],
            "metadata_views": extract_execution_metadata_views(task.metadata_json),
            "routing_explainability": self._routing_explainability_from_task_metadata(task),
            "acceptance_summary": acceptance_summary,
            "execution_memory": execution_memory,
            "changed_artifacts": changed_artifacts,
            "last_run_id": latest.id if latest else None,
            "focal_run_id": focal.id if focal else None,
            "checkpoint_excerpt": cp_excerpt,
            "recent_events_tail": events_tail,
            "trace": self._workflow_trace_payload(focal) if focal else [],
            "durable_workflow": self._durable_workflow_payload(focal) if focal else {},
            "child_runs": child_runs,
            "blocker_queue": [
                item
                for item in (stage_state.get("branch_results") or [])
                if item.get("status") == "blocked"
            ],
            "review_state": stage_state.get("review") or {},
            "github_action_state": stage_state.get("github_sync") or {},
        }

    async def get_run_execution_snapshot(self, user: User, run_id: str) -> dict[str, Any]:
        """Run-scoped execution snapshot (relational reads only)."""
        run = await self.get_run(user, run_id)
        child_runs = await self._child_runs_for_parent(run.id)
        pending_approvals = await self.repo.list_pending_approvals_for_run(user.id, run_id)
        raw_events = await self.repo.list_run_events(run.id)
        events_tail = self._run_event_tail_payloads(raw_events, limit=12)
        pending_sync: list = []
        if run.task_id:
            sync_all = await self.repo.list_sync_events_for_task(run.task_id)
            pending_sync = [e for e in sync_all if e.status in ("queued", "pending")]
            pending_sync = pending_sync[-10:]
        meta = {
            "schema_version": EXECUTION_SNAPSHOT_SCHEMA_VERSION,
            "execution_truth": EXECUTION_TRUTH_DESCRIPTION,
            "sources_read": list(SNAPSHOT_SOURCES_RUN),
        }
        task = await self.db.get(OrchestratorTask, run.task_id) if run.task_id else None
        execution_memory = extract_execution_memory_details(getattr(task, "metadata_json", None))
        changed_artifacts = (
            await self._changed_artifacts_payload(run.task_id, run_id=run.id) if run.task_id else []
        )
        stage_state = self._stage_state_payload(run)
        return {
            "meta": meta,
            "project_id": run.project_id,
            "run": run,
            "task_id": run.task_id,
            "pending_approvals": [
                {
                    "id": a.id,
                    "approval_type": a.approval_type,
                    "run_id": a.run_id,
                    "task_id": a.task_id,
                    "reason": a.reason,
                    "created_at": a.created_at,
                }
                for a in pending_approvals
            ],
            "pending_github_sync": [
                {
                    "id": e.id,
                    "action": e.action,
                    "status": e.status,
                    "detail": e.detail,
                    "created_at": e.created_at,
                }
                for e in pending_sync
            ],
            "routing_explainability": self._routing_explainability_from_payload(
                run.input_payload_json
            ),
            "execution_memory": execution_memory,
            "changed_artifacts": changed_artifacts,
            "checkpoint_excerpt": checkpoint_excerpt(run.checkpoint_json),
            "recent_events_tail": events_tail,
            "trace": self._workflow_trace_payload(run),
            "durable_workflow": self._durable_workflow_payload(run),
            "child_runs": child_runs,
            "blocker_queue": [
                item
                for item in (stage_state.get("branch_results") or [])
                if item.get("status") == "blocked"
            ],
            "review_state": stage_state.get("review") or {},
            "github_action_state": stage_state.get("github_sync") or {},
            "resumable": self._run_is_resumable(run),
        }

    async def get_run_durable_workflow(self, user: User, run_id: str) -> dict[str, Any]:
        run = await self.get_run(user, run_id)
        return self._durable_workflow_payload(run)

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

    async def _enforce_orchestration_run_rate_limit(self, user_id: str) -> None:
        limit = settings.ORCHESTRATION_RUN_RATE_LIMIT_PER_MINUTE
        if limit <= 0:
            return
        # Local dev: SPA + parallel starts + retries exhaust a per-minute cap quickly; prod/staging still enforce.
        if settings.APP_ENV == "dev":
            return
        key = f"rate_limit:orch_run:{user_id}"
        count = await redis_client.incr(key)
        if count == 1:
            await redis_client.expire(key, 60)
        if count > limit:
            # Reject without consuming a slot — otherwise every 429 response still bumped the counter (bad UX / lockout).
            await redis_client.decr(key)
            ttl = await redis_client.ttl(key)
            retry_after = max(1, int(ttl)) if ttl is not None and int(ttl) > 0 else 60
            raise HTTPException(
                status_code=429,
                detail=f"Orchestration run rate limit exceeded ({limit} starts per rolling minute). Retry in ~{retry_after}s.",
                headers={"Retry-After": str(retry_after)},
            )

    async def _enforce_agent_token_budget(
        self,
        *,
        owner_id: str,
        agent_id: str | None,
    ) -> None:
        if not agent_id:
            return
        agent = await self.db.get(AgentProfile, agent_id)
        if agent is None:
            return
        # Local providers are non-billable in this stack; do not block run starts on token budgets.
        if await self._is_local_agent_budget_exempt(agent):
            return
        budget = (agent.budget_json or {}).get("token_budget")
        if not budget:
            return
        try:
            cap = int(budget)
        except (TypeError, ValueError):
            return
        since = datetime.now(UTC) - timedelta(days=max(1, settings.AGENT_TOKEN_BUDGET_WINDOW_DAYS))
        used = await self.repo.sum_token_usage_for_agent(owner_id, agent_id, since)
        if used >= cap:
            raise HTTPException(
                status_code=429,
                detail="Agent token budget for the configured window is exhausted.",
            )

    async def _enforce_agent_cost_budget(
        self,
        *,
        owner_id: str,
        agent_id: str | None,
    ) -> None:
        if not agent_id:
            return
        agent = await self.db.get(AgentProfile, agent_id)
        if agent is None:
            return
        if await self._is_local_agent_budget_exempt(agent):
            return
        raw_cap = (agent.budget_json or {}).get("cost_cap_usd")
        if raw_cap is None:
            return
        try:
            cap_usd = float(raw_cap)
        except (TypeError, ValueError):
            return
        if cap_usd <= 0:
            return
        since = datetime.now(UTC) - timedelta(days=max(1, settings.AGENT_TOKEN_BUDGET_WINDOW_DAYS))
        used_micros = await self.repo.sum_estimated_cost_micros_for_agent(owner_id, agent_id, since)
        if used_micros / 1_000_000 >= cap_usd:
            raise HTTPException(
                status_code=429,
                detail="Agent cost budget (cost_cap_usd) for the configured window is exhausted.",
            )

    async def _is_local_agent_budget_exempt(self, agent: AgentProfile) -> bool:
        if agent.provider_config_id:
            provider = await self.db.get(ProviderConfig, agent.provider_config_id)
            if provider is not None and provider.provider_type in {"local", "ollama"}:
                return True
        if agent.project_id:
            providers = await self.repo.list_providers(agent.owner_id, agent.project_id)
            default_provider = next(
                (item for item in providers if item.is_default and item.is_enabled), None
            )
            if default_provider is not None and default_provider.provider_type in {
                "local",
                "ollama",
            }:
                return True
        # When no explicit provider is pinned, orchestration falls back to runtime default.
        return settings.AI_DEFAULT_PROVIDER == "local"

    async def get_run_cost_summary(self, user: User, run_id: str) -> dict[str, Any]:
        run = await self.get_run(user, run_id)
        event_micros = await self.repo.sum_run_event_cost_micros_for_run(run.id)
        return {
            "run_id": run.id,
            "project_id": run.project_id,
            "status": run.status,
            "estimated_cost_usd": run.estimated_cost_micros / 1_000_000,
            "event_cost_sum_usd": event_micros / 1_000_000,
            "token_input": run.token_input,
            "token_output": run.token_output,
            "token_total": run.token_total,
            "model_name": run.model_name,
        }

    async def get_runtime_info(self, user: User) -> dict[str, Any]:
        """Non-secret orchestration flags for admin UI (air-gapped / failover toggles)."""
        _ = user
        from backend.modules.orchestration.execution.durable_execution import durable_backend_status

        return {
            "orchestration_provider_failover": settings.ORCHESTRATION_PROVIDER_FAILOVER,
            "orchestration_use_langgraph": settings.ORCHESTRATION_USE_LANGGRAPH,
            "orchestration_durable_queue_backend": settings.ORCHESTRATION_DURABLE_QUEUE_BACKEND,
            "durable_signal_model": "checkpoint_signal_queue",
            "durable_query_model": "checkpoint_query_snapshot",
            "durable_backend": durable_backend_status(),
            "execution_topology": {
                "api_gateway": "FastAPI",
                "orchestration_service": "modular_monolith",
                "agent_execution_workers": "Celery workers",
                "github_integration": "github queue",
                "model_gateway": "model_gateway queue",
                "observability": "observability queue",
                "cpu_jobs": "cpu queue",
                "system_state": "Postgres",
                "transient_transport": "Redis",
            },
            "realtime_transport": {
                "protocol": "SSE",
                "project_stream": "/orchestration/projects/{project_id}/stream",
                "run_stream": "/orchestration/runs/{run_id}/stream",
                "delivery": "database-polled event cursor",
            },
            "celery_queues": {
                "orchestration": settings.CELERY_TASK_DEFAULT_QUEUE,
                "email": settings.CELERY_EMAIL_QUEUE,
                "github": settings.CELERY_QUEUE_GITHUB,
                "model_gateway": settings.CELERY_QUEUE_MODEL_GATEWAY,
                "observability": settings.CELERY_QUEUE_OBSERVABILITY,
                "cpu": settings.CELERY_QUEUE_CPU,
            },
        }

    async def _run_selection_meta(
        self,
        *,
        project_id: str,
        task: OrchestratorTask,
        payload: dict[str, Any],
        execution_settings: dict[str, Any],
        run_mode: str,
        worker_agent_id: str | None,
        orchestrator_agent_id: str | None,
        worker_source: str | None,
        model_name: str | None,
        model_source: str,
    ) -> dict[str, Any]:
        worker_rationale = ""
        if worker_source == "payload":
            worker_rationale = "The worker agent was set explicitly in the run request payload."
        elif worker_source == "pinned":
            agent = await self.db.get(AgentProfile, worker_agent_id) if worker_agent_id else None
            nm = agent.name if agent else "the pinned agent"
            worker_rationale = (
                f"This run uses a pinned worker ({nm}) from task or project execution settings "
                "(or the run payload), after membership and task_filter checks."
            )
        elif worker_source == "task":
            agent = await self.db.get(AgentProfile, worker_agent_id) if worker_agent_id else None
            nm = agent.name if agent else "the assigned agent"
            worker_rationale = f"This run uses the task's assigned worker agent ({nm})."
        elif worker_source == "auto" and worker_agent_id:
            agent = await self.db.get(AgentProfile, worker_agent_id)
            required = set(self._extract_required_tools(task))
            tools = set(agent.allowed_tools_json or []) if agent else set()
            overlap = required & tools
            depths = await self.repo.count_active_runs_by_worker(project_id, [worker_agent_id])
            qd = depths.get(worker_agent_id, 0)
            nm = agent.name if agent else "An agent"
            parts = [
                f"{nm} was auto-selected from this project's eligible agents.",
            ]
            if required:
                parts.append(f"The task lists these required_tools: {', '.join(sorted(required))}.")
                if overlap:
                    parts.append(
                        f"This agent's allowed_tools cover {len(overlap)} of them ({', '.join(sorted(overlap))})."
                    )
                else:
                    parts.append(
                        "No agent covered all required_tools; the lowest queue-depth eligible agent was used."
                    )
            else:
                parts.append(
                    "No required_tools filter; chose lowest active-run load, then name order."
                )
            parts.append(f"Queued depth for this agent was {qd} other in-flight runs.")
            rm = execution_settings.get("routing_mode") or "capability_based"
            sb = execution_settings.get("sibling_load_balance") or "queue_depth"
            su = bool(execution_settings.get("skip_unhealthy_worker_providers", True))
            parts.append(
                f"Project routing_mode={rm}, sibling_load_balance={sb}, "
                f"skip_unhealthy_worker_providers={su}."
            )
            worker_rationale = " ".join(parts)
        elif worker_source == "debate_pair" and worker_agent_id:
            agent = await self.db.get(AgentProfile, worker_agent_id)
            nm = agent.name if agent else "Agent A"
            worker_rationale = (
                f"{nm} leads the debate side as the first seat in the auto-ranked debate pair "
                "(capability overlap, queue depth, then name)."
            )
        elif not worker_agent_id:
            worker_rationale = (
                "No worker agent is attached to this run (orchestration-only / planner mode)."
            )
        else:
            worker_rationale = "Worker routing metadata is unavailable for this run."

        if model_source == "payload":
            model_rationale = "The model name was set explicitly on the run API request."
        elif model_source == "project_execution":
            model_rationale = "Uses execution.model_name from the orchestration project settings (org-wide default for this project)."
        else:
            model_rationale = (
                "No explicit model on the run or project; the worker uses provider defaults or policy routing "
                "when the first LLM call is made."
            )

        return {
            "agent_selection_reason": worker_rationale,
            "model_selection_reason": model_rationale,
            "routing_inputs": {
                "run_mode": run_mode,
                "worker_agent_id": worker_agent_id,
                "orchestrator_agent_id": orchestrator_agent_id,
                "model_name": model_name,
                "worker_source": worker_source,
                "model_source": model_source,
                "required_tools": self._extract_required_tools(task),
                "task_priority": getattr(task, "priority", None),
                "task_due_date": getattr(task, "due_date", None),
            },
            "routing_policy_snapshot": {
                "routing_mode": execution_settings.get("routing_mode") or "capability_based",
                "sibling_load_balance": execution_settings.get("sibling_load_balance")
                or "queue_depth",
                "skip_unhealthy_worker_providers": bool(
                    execution_settings.get("skip_unhealthy_worker_providers", True)
                ),
                "project_model_name": execution_settings.get("model_name"),
            },
            "worker_agent_id_source": worker_source,
            "model_source": model_source,
            "worker_agent_rationale": worker_rationale,
            "model_rationale": model_rationale,
            "run_mode": run_mode,
            "orchestrator_agent_id": orchestrator_agent_id,
            "worker_agent_id": worker_agent_id,
            "model_name": model_name,
            "routing_mode": execution_settings.get("routing_mode") or "capability_based",
            "sibling_load_balance": execution_settings.get("sibling_load_balance") or "queue_depth",
            "skip_unhealthy_worker_providers": bool(
                execution_settings.get("skip_unhealthy_worker_providers", True)
            ),
        }

    async def start_task_run(
        self,
        user: User,
        project_id: str,
        task_id: str,
        payload: dict[str, Any],
    ) -> tuple[TaskRun, list[str]]:
        project = await self.get_project(user, project_id)
        task = await self.get_task(user, project_id, task_id)
        deps = await self.repo.list_task_dependencies_for_task(task.id)
        if deps:
            blocking = []
            for dep in deps:
                dep_task = await self.db.get(OrchestratorTask, dep.depends_on_task_id)
                if dep_task and dep_task.status not in {"completed", "approved"}:
                    blocking.append(dep_task.title)
            if blocking:
                raise HTTPException(400, f"Task has incomplete dependencies: {blocking}")
        execution_settings = self._project_execution_settings(project)
        run_mode = payload.get("run_mode", "single_agent")
        orchestrator_agent_id = payload.get("orchestrator_agent_id") or execution_settings.get(
            "manager_agent_id"
        )
        reviewer_agent_id = payload.get("reviewer_agent_id") or task.reviewer_agent_id
        if reviewer_agent_id is None:
            reviewer_ids = execution_settings.get("reviewer_agent_ids", [])
            reviewer_agent_id = reviewer_ids[0] if reviewer_ids else None
        if reviewer_agent_id and task.reviewer_agent_id != reviewer_agent_id:
            task.reviewer_agent_id = reviewer_agent_id
            chain = [
                str(item).strip()
                for item in execution_settings.get("reviewer_agent_ids", [])
                if str(item).strip()
            ]
            if chain and reviewer_agent_id in chain:
                meta = dict(task.metadata_json or {})
                meta["review_chain"] = {
                    "reviewer_agent_ids": chain,
                    "current_index": chain.index(reviewer_agent_id),
                }
                task.metadata_json = meta
                orm_attributes.flag_modified(task, "metadata_json")

        worker_explicit = (
            "worker_agent_id" in payload and payload.get("worker_agent_id") is not None
        )
        if worker_explicit:
            worker_agent_id = payload.get("worker_agent_id")
            worker_source = "payload"
        else:
            pinned_raw = (
                payload.get("pinned_worker_agent_id")
                or (task.metadata_json or {}).get("pinned_worker_agent_id")
                or execution_settings.get("pinned_worker_agent_id")
            )
            if pinned_raw:
                worker_agent_id = str(pinned_raw)
                worker_source = "pinned"
            elif task.assigned_agent_id:
                worker_agent_id = task.assigned_agent_id
                worker_source = "task"
            else:
                worker_agent_id = None
                worker_source = None

        if run_mode in {"single_agent", "manager_worker", "debate"} and worker_agent_id is None:
            selected_worker = await self._select_best_agent_for_task(
                project.id,
                task=task,
                exclude_agent_ids=[orchestrator_agent_id] if orchestrator_agent_id else [],
            )
            worker_agent_id = selected_worker.id if selected_worker else None
            worker_source = "auto" if worker_agent_id else worker_source

        if run_mode == "manager_worker" and orchestrator_agent_id is None:
            manager = await self._project_default_manager(project.id)
            orchestrator_agent_id = manager.id if manager else None

        if run_mode == "debate":
            pair = await self._select_debate_pair(
                project.id,
                task,
                exclude_agent_ids=[orchestrator_agent_id] if orchestrator_agent_id else [],
            )
            if pair:
                worker_agent_id = pair[0].id
                if len(pair) > 1:
                    reviewer_agent_id = pair[1].id
                worker_source = "debate_pair"

        if worker_agent_id and worker_source == "pinned":
            member_ids = {m.agent_id for m in await self.repo.list_project_memberships(project.id)}
            if worker_agent_id not in member_ids:
                raise HTTPException(
                    status_code=400,
                    detail="pinned_worker_agent_id is not a member of this project.",
                )
            p_agent = await self._load_agent_for_run(worker_agent_id)
            if p_agent is None or not p_agent.is_active:
                raise HTTPException(
                    status_code=400, detail="Pinned worker agent is missing or inactive."
                )
            if not self._agent_eligible_for_task_by_filters(p_agent, task):
                raise HTTPException(
                    status_code=400,
                    detail="Pinned worker agent task_filters do not match this task.",
                )

        if run_mode in {"single_agent", "manager_worker", "debate"} and worker_agent_id:
            worker = await self._load_agent_for_run(worker_agent_id)
            req_tools = self._extract_required_tools(task)
            if req_tools and not self._required_tools_satisfied(worker, req_tools):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Worker agent allowed_tools must include every task required_tools entry: "
                        + ", ".join(req_tools)
                    ),
                )

        payload_model = payload.get("model_name")
        if payload_model not in (None, ""):
            model_source = "payload"
        elif execution_settings.get("model_name"):
            model_source = "project_execution"
        else:
            model_source = "runtime_default"
        model_name = payload_model or execution_settings.get("model_name")

        await self._enforce_agent_token_budget(owner_id=project.owner_id, agent_id=worker_agent_id)
        await self._enforce_agent_token_budget(
            owner_id=project.owner_id, agent_id=orchestrator_agent_id
        )
        await self._enforce_agent_cost_budget(owner_id=project.owner_id, agent_id=worker_agent_id)
        await self._enforce_agent_cost_budget(
            owner_id=project.owner_id, agent_id=orchestrator_agent_id
        )
        await self._enforce_orchestration_run_rate_limit(user.id)

        selection_meta = await self._run_selection_meta(
            project_id=project.id,
            task=task,
            payload=payload,
            execution_settings=execution_settings,
            run_mode=run_mode,
            worker_agent_id=worker_agent_id,
            orchestrator_agent_id=orchestrator_agent_id,
            worker_source=worker_source,
            model_name=model_name,
            model_source=model_source,
        )
        input_payload = dict(payload.get("input_payload") or {})
        prev_meta = input_payload.get("orchestration_meta")
        if isinstance(prev_meta, dict):
            input_payload["orchestration_meta"] = {**prev_meta, **selection_meta}
        else:
            input_payload["orchestration_meta"] = selection_meta

        task_meta = dict(task.metadata_json or {})
        task_meta["routing_explainability"] = self._routing_explainability_from_payload(
            {"orchestration_meta": input_payload.get("orchestration_meta")}
        )
        task.metadata_json = task_meta
        orm_attributes.flag_modified(task, "metadata_json")

        run = await self.repo.create_run(
            project_id=project_id,
            task_id=task.id,
            triggered_by_user_id=user.id,
            orchestrator_agent_id=orchestrator_agent_id,
            worker_agent_id=worker_agent_id,
            reviewer_agent_id=reviewer_agent_id,
            provider_config_id=payload.get("provider_config_id")
            or execution_settings.get("provider_config_id"),
            run_mode=run_mode,
            status="queued",
            model_name=model_name,
            input_payload_json=input_payload,
        )
        run.checkpoint_json = ensure_workflow_state(
            run.checkpoint_json,
            run_mode=run.run_mode,
            steps=self._workflow_steps_for_run(run),
            run_id=run.id,
        )
        run.checkpoint_json = update_query_snapshot(
            run.checkpoint_json,
            data={
                "latest_status": "queued",
                "run_id": run.id,
                "task_id": task.id,
                "project_id": project_id,
                "worker_agent_id": worker_agent_id,
                "orchestrator_agent_id": orchestrator_agent_id,
            },
        )
        startup_warnings: list[str] = []
        resolution_agent = await self._load_agent_for_run(worker_agent_id or orchestrator_agent_id)
        resolved_provider = await self._resolve_provider_for_run(run, resolution_agent)
        if resolved_provider is None:
            startup_warnings.append(
                "No LLM provider is configured for this run: the worker agent has no provider, and no project or "
                "run-level default provider was found. The run will use stub/heuristic output until you add a provider "
                "(Admin → Settings → Providers) and assign it to the agent or project."
            )
        # Only move the task when the state machine allows it. in_progress → queued is invalid (409); follow-up runs
        # while a task is already active leave the task status unchanged. Re-runs after completion use planned.
        allowed_next = TASK_TRANSITIONS.get(task.status, set())
        if task.status == "queued":
            pass
        elif "queued" in allowed_next:
            await self._transition_task_status(task, "queued", run=run, reason="run queued")
        elif task.status == "completed" and "planned" in allowed_next:
            await self._transition_task_status(
                task, "planned", run=run, reason="run queued after completion"
            )
        await self._emit_run_event(
            run,
            event_type="queued",
            message="Run queued for execution.",
            payload={"run_mode": run.run_mode},
        )
        if startup_warnings:
            await self._emit_run_event(
                run,
                event_type="startup_notice",
                level="warning",
                message=startup_warnings[0],
                payload={"warnings": startup_warnings},
            )
        await self.db.commit()
        from backend.modules.orchestration.execution.durable_execution import (
            submit_orchestration_run,
        )

        submit_orchestration_run(run.id)
        await self.db.refresh(run)
        return run, startup_warnings

    async def cancel_run(self, user: User, run_id: str):
        run = await self.get_run(user, run_id)
        child_runs = await self._child_runs_for_parent(run.id)
        run.status = "cancelled"
        run.cancelled_at = datetime.now(UTC)
        run.checkpoint_json = update_query_snapshot(
            run.checkpoint_json,
            data={
                "latest_status": "cancelled",
                "cancelled_at": run.cancelled_at.isoformat(),
                "run_id": run.id,
            },
        )
        for child in child_runs:
            if child.status in {"queued", "in_progress", "blocked"}:
                child.status = "cancelled"
                child.cancelled_at = run.cancelled_at
                child.checkpoint_json = update_query_snapshot(
                    child.checkpoint_json,
                    data={"latest_status": "cancelled", "parent_run_id": run.id},
                )
                await self._emit_run_event(
                    child,
                    event_type="cancelled",
                    level="warning",
                    message="Child run cancelled with parent.",
                    payload={"parent_run_id": run.id},
                )
        task = await self.db.get(OrchestratorTask, run.task_id) if run.task_id else None
        if task and task.status in {"queued", "planned", "in_progress"}:
            await self._transition_task_status(task, "planned", run=run, reason="run cancelled")
        await self._emit_run_event(
            run,
            event_type="cancelled",
            level="warning",
            message="Run cancelled by user.",
        )
        await self.db.commit()
        await self.db.refresh(run)
        return run

    async def resume_run(self, user: User, run_id: str):
        run = await self.get_run(user, run_id)
        if not self._run_is_resumable(run):
            raise HTTPException(
                status_code=409, detail="Run is not resumable from its current checkpoint."
            )
        run.status = "queued"
        run.error_message = None
        run.completed_at = None
        run.cancelled_at = None
        run.checkpoint_json = increment_resume_count(run.checkpoint_json)
        run.checkpoint_json = update_query_snapshot(
            run.checkpoint_json,
            data={"latest_status": "queued", "resume_requested_by": user.id, "run_id": run.id},
        )
        await self._emit_run_event(
            run,
            event_type="workflow_resumed",
            message="Run resumed from durable checkpoint.",
            payload={"trace": self._workflow_trace_payload(run)},
        )
        for child in await self._child_runs_for_parent(run.id):
            if child.status in {"blocked", "failed"}:
                child.status = "queued"
                child.error_message = None
                child.completed_at = None
                child.cancelled_at = None
                child.checkpoint_json = increment_resume_count(child.checkpoint_json)
                await self._emit_run_event(
                    child,
                    event_type="workflow_resumed",
                    message="Child run re-queued from parent resume.",
                    payload={"parent_run_id": run.id},
                )
        await self.db.commit()
        from backend.modules.orchestration.execution.durable_execution import (
            submit_orchestration_run,
        )

        submit_orchestration_run(run.id)
        await self.db.refresh(run)
        return run

    async def replay_run(
        self,
        user: User,
        run_id: str,
        from_event_index: int = 0,
        *,
        model_name: str | None = None,
    ):
        """Queue a new run that carries forward transcript context from a parent run."""
        old = await self.get_run(user, run_id)
        old_project = await self.db.get(OrchestratorProject, old.project_id)
        if old_project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        await self._enforce_agent_token_budget(
            owner_id=old_project.owner_id, agent_id=old.worker_agent_id
        )
        await self._enforce_agent_token_budget(
            owner_id=old_project.owner_id, agent_id=old.orchestrator_agent_id
        )
        await self._enforce_agent_cost_budget(
            owner_id=old_project.owner_id, agent_id=old.worker_agent_id
        )
        await self._enforce_agent_cost_budget(
            owner_id=old_project.owner_id, agent_id=old.orchestrator_agent_id
        )
        events = await self.repo.list_run_events(old.id)
        if from_event_index < 0 or from_event_index > len(events):
            raise HTTPException(
                status_code=400, detail="from_event_index is out of range for this run"
            )
        await self._enforce_orchestration_run_rate_limit(user.id)
        prior = events[:from_event_index]
        transcript = "\n".join(f"[{e.event_type}] {e.message}" for e in prior)
        base_input = dict(old.input_payload_json or {})
        base_input.pop("orchestration_replay", None)
        base_input["orchestration_replay"] = {
            "parent_run_id": old.id,
            "from_event_index": from_event_index,
            "prior_transcript": transcript[:12000],
        }
        old_orch = base_input.get("orchestration_meta")
        if isinstance(old_orch, dict):
            base_input["orchestration_meta"] = {**old_orch, "replayed_from_run_id": old.id}
        else:
            base_input["orchestration_meta"] = {"replayed_from_run_id": old.id}
        new_run = await self.repo.create_run(
            parent_run_id=getattr(old, "parent_run_id", None),
            project_id=old.project_id,
            task_id=old.task_id,
            triggered_by_user_id=user.id,
            orchestrator_agent_id=old.orchestrator_agent_id,
            worker_agent_id=old.worker_agent_id,
            reviewer_agent_id=old.reviewer_agent_id,
            provider_config_id=old.provider_config_id,
            brainstorm_id=old.brainstorm_id,
            run_mode=old.run_mode,
            status="queued",
            model_name=(str(model_name).strip() or old.model_name)
            if model_name is not None
            else old.model_name,
            attempt_number=old.attempt_number + 1,
            retry_count=old.retry_count,
            checkpoint_json=dict(old.checkpoint_json or {}),
            input_payload_json=base_input,
        )
        new_run.checkpoint_json = ensure_workflow_state(
            new_run.checkpoint_json,
            run_mode=new_run.run_mode,
            steps=self._workflow_steps_for_run(new_run),
            run_id=new_run.id,
        )
        new_run.checkpoint_json = update_query_snapshot(
            new_run.checkpoint_json,
            data={"latest_status": "queued", "replayed_from_run_id": old.id, "run_id": new_run.id},
        )
        task = await self.db.get(OrchestratorTask, new_run.task_id) if new_run.task_id else None
        if task:
            await self._transition_task_status(task, "queued", run=new_run, reason="replay queued")
        await self._emit_run_event(
            new_run,
            event_type="replay_queued",
            message=f"Replay from run {old.id} starting after event index {from_event_index}.",
            payload={"parent_run_id": old.id, "from_event_index": from_event_index},
        )
        await self.db.commit()
        from backend.modules.orchestration.execution.durable_execution import (
            submit_orchestration_run,
        )

        submit_orchestration_run(new_run.id)
        await self.db.refresh(new_run)
        return new_run

    async def aggregate_cost_analytics(self, user: User, days: int = 30) -> dict[str, Any]:
        since = datetime.now(UTC) - timedelta(days=max(1, min(days, 365)))
        raw = await self.repo.aggregate_run_costs(user.id, since=since)
        by_agent = []
        for row in raw["by_agent"]:
            aid = row["agent_id"]
            agent = await self.db.get(AgentProfile, aid) if aid else None
            by_agent.append(
                {
                    "name": agent.name if agent else str(aid)[:8],
                    "cost_usd": row["cost_usd"],
                    "tokens": row["tokens"],
                    "runs": row["runs"],
                }
            )
        by_agent.sort(key=lambda item: item["cost_usd"], reverse=True)
        by_project = sorted(raw["by_project"], key=lambda item: item["cost_usd"], reverse=True)
        by_provider = sorted(raw["by_provider"], key=lambda item: item["cost_usd"], reverse=True)
        total_cost = raw["total_cost_micros"] / 1_000_000
        return {
            "period": f"last_{days}_days",
            "by_project": by_project,
            "by_agent": by_agent,
            "by_task": raw.get("by_task", []),
            "by_provider": by_provider,
            "most_expensive_runs": raw["most_expensive_runs"],
            "total_cost_usd": total_cost,
            "total_tokens": raw["total_tokens"],
        }

    async def run_agent_simulation(
        self,
        user: User,
        agent_id: str,
        *,
        scenarios: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        agent = await self.get_agent(user, agent_id)
        cases = scenarios or [
            {
                "title": "Bug triage",
                "description": "Identify likely root cause and first fix.",
                "acceptance_criteria": "Clear diagnosis + first patch.",
            },
            {
                "title": "Spec drafting",
                "description": "Write a concise API spec with risks.",
                "acceptance_criteria": "Endpoints + risks + rollout plan.",
            },
            {
                "title": "Review response",
                "description": "Review a patch proposal for correctness.",
                "acceptance_criteria": "Find at least one risk and test gap.",
            },
        ]
        results: list[dict[str, Any]] = []
        pass_count = 0
        for idx, case in enumerate(cases, start=1):
            probe = await self.test_run_agent(
                user,
                agent_id,
                {
                    "prompt": str(
                        case.get("description") or case.get("title") or "Simulation task"
                    ),
                    "max_output_tokens": 400,
                    "temperature": 0.2,
                    "simulate_tools": True,
                },
            )
            output = str(probe.get("output_text") or "")
            passed = len(output.strip()) >= 40
            if passed:
                pass_count += 1
            results.append(
                {
                    "scenario_index": idx,
                    "title": str(case.get("title") or f"Scenario {idx}"),
                    "passed": passed,
                    "latency_ms": int(probe.get("latency_ms") or 0),
                    "token_total": int(probe.get("token_total") or 0),
                    "estimated_cost_usd": float(probe.get("estimated_cost_usd") or 0),
                    "output_preview": output[:280],
                }
            )
        avg_cost = sum(float(item["estimated_cost_usd"]) for item in results) / max(len(results), 1)
        avg_latency = sum(int(item["latency_ms"]) for item in results) / max(len(results), 1)
        readiness = (
            "ready"
            if pass_count >= max(1, int(len(results) * 0.67)) and avg_cost < 0.5
            else "needs_tuning"
        )
        return {
            "agent_id": agent.id,
            "agent_name": agent.name,
            "readiness": readiness,
            "pass_rate": round(pass_count / max(len(results), 1), 3),
            "avg_cost_usd": round(avg_cost, 6),
            "avg_latency_ms": round(avg_latency, 1),
            "results": results,
        }

    async def agent_performance_scorecard(self, user: User, days: int = 30) -> list[dict[str, Any]]:
        since = datetime.now(UTC) - timedelta(days=max(1, min(days, 365)))
        runs = await self.repo.list_runs(user.id, None)
        by_agent: dict[str, dict[str, Any]] = {}
        for run in runs:
            if run.created_at < since:
                continue
            agent_id = run.worker_agent_id or run.orchestrator_agent_id
            if not agent_id:
                continue
            row = by_agent.setdefault(
                agent_id,
                {
                    "agent_id": agent_id,
                    "runs": 0,
                    "accepted": 0,
                    "latency": 0,
                    "cost": 0,
                    "escalations": 0,
                    "review_pass": 0,
                    "review_total": 0,
                },
            )
            row["runs"] += 1
            row["latency"] += int(run.latency_ms or 0)
            row["cost"] += float(run.estimated_cost_micros or 0) / 1_000_000
            if run.status == "completed":
                row["accepted"] += 1
            if run.run_mode == "review":
                row["review_total"] += 1
                if run.status == "completed":
                    row["review_pass"] += 1
            evs = await self.repo.list_run_events(run.id)
            row["escalations"] += sum(
                1 for e in evs if e.event_type in {"rule_escalation", "task_escalation"}
            )
        output: list[dict[str, Any]] = []
        for aid, row in by_agent.items():
            agent = await self.db.get(AgentProfile, aid)
            runs_n = max(int(row["runs"]), 1)
            acc_rate = float(row["accepted"]) / runs_n
            avg_cost = float(row["cost"]) / runs_n
            avg_lat = float(row["latency"]) / runs_n
            review_pass_rate = (
                float(row["review_pass"]) / max(int(row["review_total"]), 1)
                if row["review_total"]
                else 1.0
            )
            under = acc_rate < 0.6 or review_pass_rate < 0.6 or avg_cost > 2.0
            output.append(
                {
                    "agent_id": aid,
                    "agent_name": agent.name if agent else aid[:8],
                    "acceptance_rate": round(acc_rate, 3),
                    "avg_cost_usd": round(avg_cost, 6),
                    "avg_latency_ms": round(avg_lat, 2),
                    "review_pass_rate": round(review_pass_rate, 3),
                    "escalation_frequency": round(float(row["escalations"]) / runs_n, 3),
                    "underperforming": under,
                    "suggestion": "Tune prompts/skills and lower-risk routing."
                    if under
                    else "Performance within target.",
                }
            )
        output.sort(
            key=lambda item: (item["underperforming"], -item["acceptance_rate"]), reverse=True
        )
        return output

    async def explain_run(self, user: User, run_id: str) -> dict[str, Any]:
        run = await self.get_run(user, run_id)
        events = await self.repo.list_run_events(run.id)
        approvals = await self.repo.list_pending_approvals_for_run(user.id, run.id)
        tools = [
            str(e.payload_json.get("tool") or "")
            for e in events
            if e.event_type.startswith("tool_call_")
        ]
        tools = [t for t in tools if t]

        # Extract selection metadata from input payload
        payload = run.input_payload_json or {}
        selection = payload.get("orchestration_meta", {})

        # Provide defaults if metadata is missing
        worker_agent_rationale = selection.get(
            "worker_agent_rationale", "Worker agent selection metadata unavailable."
        )
        model_rationale = selection.get("model_rationale", "Model selection metadata unavailable.")

        return {
            "run_id": run.id,
            "summary": (
                f"Run used agent {run.worker_agent_id or run.orchestrator_agent_id}, "
                f"model {run.model_name or 'default'}, executed {len(tools)} tool calls, "
                f"and finished with status {run.status}."
            ),
            "agent_rationale": worker_agent_rationale,
            "model_rationale": model_rationale,
            "tools_called": tools[:50],
            "approvals_pending": len(approvals),
            "approvals_pending_types": [a.approval_type for a in approvals],
        }

    async def _compress_run_context_if_needed(self, run: TaskRun) -> None:
        payload = dict(run.input_payload_json or {})
        replay = payload.get("orchestration_replay")
        if not isinstance(replay, dict):
            return
        transcript = str(replay.get("prior_transcript") or "")
        if len(transcript) < 4000:
            return
        compressed = transcript[:1800] + "\n...\n" + transcript[-1200:]
        replay["prior_transcript"] = compressed
        payload["orchestration_replay"] = replay
        run.input_payload_json = payload
        saved_chars = max(len(transcript) - len(compressed), 0)
        run.checkpoint_json = set_workflow_artifact(
            run.checkpoint_json,
            key="context_compression",
            value={
                "saved_chars": saved_chars,
                "saved_tokens_estimate": int(saved_chars / 4),
            },
        )
        await self._emit_run_event(
            run,
            event_type="context_compressed",
            message="Replay context compressed to reduce token usage.",
            payload={"saved_chars": saved_chars, "saved_tokens_estimate": int(saved_chars / 4)},
        )

    async def _enforce_run_output_schema(self, run: TaskRun) -> None:
        agent = await self._load_agent_for_run(run.worker_agent_id or run.orchestrator_agent_id)
        schema = (agent.output_schema_json or {}) if agent else {}
        fmt = str(schema.get("format") or "").strip()
        final_output = str(
            (run.output_payload_json or {}).get("final_output")
            or (run.output_payload_json or {}).get("summary")
            or ""
        )
        if not fmt or not final_output:
            return
        valid = True
        if fmt == "json":
            structured = (run.output_payload_json or {}).get("structured_output_json")
            if isinstance(structured, (dict, list)):
                valid = True
            else:
                try:
                    json.loads(final_output)
                except Exception:
                    valid = False
        elif fmt == "checklist":
            valid = "- " in final_output or "1." in final_output
        elif fmt == "adr":
            low = final_output.lower()
            valid = "decision" in low and "context" in low
        elif fmt == "patch_proposal":
            low = final_output.lower()
            valid = "file" in low and "test" in low
        elif fmt == "issue_reply":
            low = final_output.lower()
            valid = "finding" in low or "review" in low
        else:
            valid = False
        if not valid:
            raise BlockedExecution(f"Output validation failed for schema format '{fmt}'.")

    async def _detect_and_log_task_output_conflict(
        self, task: OrchestratorTask, run: TaskRun
    ) -> None:
        if not task.id:
            return
        all_runs = await self.repo.list_runs(task.created_by_user_id, task.project_id)
        related = [
            r
            for r in all_runs
            if r.task_id == task.id and r.id != run.id and r.status == "completed"
        ]
        if not related:
            return
        current = str(
            (run.output_payload_json or {}).get("final_output")
            or (run.output_payload_json or {}).get("summary")
            or ""
        ).strip()
        if not current:
            return
        previous = str(
            (related[-1].output_payload_json or {}).get("final_output")
            or (related[-1].output_payload_json or {}).get("summary")
            or ""
        ).strip()
        if not previous:
            return
        contradict = ("approve" in current.lower() and "reject" in previous.lower()) or (
            "reject" in current.lower() and "approve" in previous.lower()
        )
        if not contradict:
            return
        await self.repo.create_approval(
            project_id=task.project_id,
            task_id=task.id,
            run_id=run.id,
            issue_link_id=task.github_issue_link_id,
            requested_by_user_id=run.triggered_by_user_id,
            approval_type="output_conflict_resolution",
            status="pending",
            payload_json={
                "current_run_id": run.id,
                "previous_run_id": related[-1].id,
                "current_summary": current[:500],
                "previous_summary": previous[:500],
            },
        )
        await self._transition_task_status(
            task, "blocked", run=run, reason="conflicting agent outputs require resolution"
        )

    async def retry_run(self, user: User, run_id: str):
        run = await self.get_run(user, run_id)
        project = await self.db.get(OrchestratorProject, run.project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        await self._enforce_agent_token_budget(
            owner_id=project.owner_id, agent_id=run.worker_agent_id
        )
        await self._enforce_agent_token_budget(
            owner_id=project.owner_id, agent_id=run.orchestrator_agent_id
        )
        await self._enforce_agent_cost_budget(
            owner_id=project.owner_id, agent_id=run.worker_agent_id
        )
        await self._enforce_agent_cost_budget(
            owner_id=project.owner_id, agent_id=run.orchestrator_agent_id
        )
        new_run = await self.repo.create_run(
            parent_run_id=run.parent_run_id,
            project_id=run.project_id,
            task_id=run.task_id,
            triggered_by_user_id=user.id,
            orchestrator_agent_id=run.orchestrator_agent_id,
            worker_agent_id=run.worker_agent_id,
            reviewer_agent_id=run.reviewer_agent_id,
            provider_config_id=run.provider_config_id,
            brainstorm_id=run.brainstorm_id,
            run_mode=run.run_mode,
            status="queued",
            model_name=run.model_name,
            attempt_number=next_retry_numbers(run.retry_count, run.attempt_number)[1],
            retry_count=next_retry_numbers(run.retry_count, run.attempt_number)[0],
            input_payload_json=run.input_payload_json,
        )
        task = await self.db.get(OrchestratorTask, new_run.task_id) if new_run.task_id else None
        if task:
            await self._transition_task_status(task, "queued", run=new_run, reason="retry queued")
        await self._emit_run_event(
            new_run,
            event_type="retry_queued",
            message=f"Retry created from run {run.id}.",
            payload={"previous_run_id": run.id},
        )
        await self.db.commit()
        from backend.modules.orchestration.execution.durable_execution import (
            submit_orchestration_run,
        )

        submit_orchestration_run(new_run.id)
        await self.db.refresh(new_run)
        return new_run

    async def list_run_events(
        self,
        user: User,
        run_id: str,
        *,
        limit: int | None = None,
        offset: int = 0,
    ):
        run = await self.get_run(user, run_id)
        return await self.repo.list_run_events(run.id, limit=limit, offset=offset)

    async def execute_run(self, run_id: str) -> TaskRun:
        logger.info("execute_run_start run_id=%s", run_id)
        run = await self.repo.get_run_for_worker(run_id)
        if run is None:
            raise RuntimeError(f"Run {run_id} not found")
        if run.status == "cancelled":
            logger.info("execute_run_cancelled run_id=%s", run_id)
            return run
        if not is_run_execution_claimable(run.status):
            logger.info(
                "execute_run_duplicate_delivery_ignored run_id=%s status=%s", run_id, run.status
            )
            return run
        logger.info(
            "execute_run_active run_id=%s status=%s run_mode=%s", run_id, run.status, run.run_mode
        )
        prior_status = run.status
        workflow = self._ensure_run_workflow(run)
        run.status = "in_progress"
        run.started_at = datetime.now(UTC)
        run.checkpoint_json = {
            **(run.checkpoint_json or {}),
            EXECUTION_THREAD_ID_KEY: run.id,
        }
        run.checkpoint_json, consumed_signals = consume_signal_queue(run.checkpoint_json)
        run.checkpoint_json = update_query_snapshot(
            run.checkpoint_json,
            data={
                "run_id": run.id,
                "project_id": run.project_id,
                "run_mode": run.run_mode,
                "worker_agent_id": run.worker_agent_id,
                "orchestrator_agent_id": run.orchestrator_agent_id,
                "latest_status": "in_progress",
                "signal_count": len(consumed_signals),
            },
        )
        task = await self.db.get(OrchestratorTask, run.task_id) if run.task_id else None
        project = await self.db.get(OrchestratorProject, run.project_id)
        if project is None:
            raise RuntimeError(f"Project {run.project_id} not found")
        await self._enforce_agent_token_budget(
            owner_id=project.owner_id, agent_id=run.worker_agent_id
        )
        await self._enforce_agent_token_budget(
            owner_id=project.owner_id, agent_id=run.orchestrator_agent_id
        )
        await self._enforce_agent_cost_budget(
            owner_id=project.owner_id, agent_id=run.worker_agent_id
        )
        await self._enforce_agent_cost_budget(
            owner_id=project.owner_id, agent_id=run.orchestrator_agent_id
        )
        # Task "planned" = accepted for execution but workflow not started yet. We keep it until after
        # run setup so the UI can show planned instead of jumping queued → in_progress in one tick.
        if task is not None and task.status == "queued":
            await self._transition_task_status(
                task, "planned", run=run, reason="execution planning"
            )
        await self._emit_run_event(
            run,
            event_type="started",
            message="Run execution started.",
            payload={
                "run_mode": run.run_mode,
                "durable_backend": workflow.get("backend"),
                "trace": self._workflow_trace_payload(run),
            },
        )
        if prior_status in {"failed", "blocked"}:
            await self._emit_run_event(
                run,
                event_type="workflow_recovery",
                message="Worker resumed execution from checkpoint after a recoverable interruption.",
                payload={"prior_status": prior_status, "trace": self._workflow_trace_payload(run)},
            )
        if consumed_signals:
            await self._emit_run_event(
                run,
                event_type="workflow_signal_applied",
                message=f"Applied {len(consumed_signals)} queued workflow signal(s).",
                payload={"signals": consumed_signals},
            )

        try:
            await self._compress_run_context_if_needed(run)
            if task is not None and task.status in {"planned", "blocked"}:
                await self._transition_task_status(
                    task, "in_progress", run=run, reason="execution started"
                )
            if settings.ORCHESTRATION_USE_LANGGRAPH:
                from backend.modules.orchestration.execution.langgraph_runner import (
                    run_via_langgraph,
                )

                await run_via_langgraph(self, run)
            elif run.run_mode == "brainstorm":
                await self._execute_brainstorm_run(run)
            elif run.run_mode == "review":
                await self._execute_review_run(run)
            elif run.run_mode == "debate":
                await self._execute_debate_run(run)
            elif run.run_mode == "manager_worker":
                await self._execute_manager_worker_run(run)
            else:
                await self._execute_single_agent_run(run)

            await self._enforce_run_output_schema(run)
            run.status = "completed"
            run.completed_at = datetime.now(UTC)
            run.checkpoint_json = set_workflow_artifact(
                mark_step(
                    run.checkpoint_json,
                    step_id=self._workflow_steps_for_run(run)[-1]["id"],
                    status="completed",
                ),
                key="final_status",
                value="completed",
            )
            run.checkpoint_json = update_query_snapshot(
                run.checkpoint_json,
                data={
                    "latest_status": "completed",
                    "completed_at": run.completed_at.isoformat(),
                    "task_id": run.task_id,
                },
            )
            if task and run.run_mode != "brainstorm":
                task.result_summary = (
                    str(
                        run.output_payload_json.get("summary")
                        or run.output_payload_json.get("final_output")
                        or ""
                    )[:2000]
                    or task.result_summary
                )
                if task.status not in {"blocked", "approved", "completed", "needs_review"}:
                    next_status = "needs_review" if task.reviewer_agent_id else "completed"
                    await self._transition_task_status(
                        task, next_status, run=run, reason="run completed"
                    )
                elif run.run_mode == "manager_worker" and task.status == "approved":
                    await self._transition_task_status(
                        task, "completed", run=run, reason="manager-worker flow fully completed"
                    )
                self._update_task_execution_memory(task, run)
                await self._detect_and_log_task_output_conflict(task, run)
            await self._emit_run_event(
                run,
                event_type="completed",
                message="Run completed successfully.",
                payload=run.output_payload_json,
            )
            await self._persist_agent_memory_from_run(
                run,
                await self._load_agent_for_run(run.worker_agent_id or run.orchestrator_agent_id),
                task,
            )
            if task and not (
                isinstance(run.output_payload_json.get("github_action_state"), dict)
                and run.output_payload_json["github_action_state"].get("completed")
            ):
                await self._sync_run_completion_to_github(run, task)
            if task and task.github_issue_link_id and run.run_mode != "brainstorm":
                await self.repo.create_approval(
                    project_id=run.project_id,
                    task_id=task.id,
                    run_id=run.id,
                    issue_link_id=task.github_issue_link_id,
                    requested_by_user_id=run.triggered_by_user_id,
                    approval_type="github_comment",
                    status="pending",
                    payload_json={
                        "draft_comment": task.result_summary or "Task completed.",
                        "close_issue": False,
                    },
                )
            await self.db.commit()
            if task and task.status in {"completed", "archived", "synced_to_github"}:
                await self.db.refresh(task)
                hook_user = None
                if run.triggered_by_user_id:
                    hook_user = await self.db.get(User, run.triggered_by_user_id)
                if hook_user:
                    await self._maybe_promote_task_close_working_memory(hook_user, project, task)
                await self._run_task_close_memory_lifecycle(hook_user, project, task)
                await self._enqueue_classifier_job_for_task(project, task)
            if task:
                await self._apply_project_escalation_rules(
                    project, run=run, task=task, trigger="run_completed"
                )
            return run
        except BlockedExecution as exc:
            run.status = "blocked"
            run.error_message = str(exc)
            step = current_step(run.checkpoint_json)
            if step:
                await self._mark_run_step(
                    run,
                    step_id=str(step.get("id")),
                    status="blocked",
                    level="warning",
                    message=f"Checkpoint captured at blocked step '{step.get('title')}'.",
                    error=str(exc),
                )
            if task:
                await self._transition_task_status(task, "blocked", run=run, reason=str(exc))
            await self._emit_run_event(
                run,
                event_type="blocked",
                level="warning",
                message=str(exc),
            )
            run.checkpoint_json = update_query_snapshot(
                run.checkpoint_json,
                data={"latest_status": "blocked", "last_error": str(exc), "task_id": run.task_id},
            )
            await self.db.commit()
            if task:
                await self._apply_project_escalation_rules(
                    project, run=run, task=task, trigger="task_blocked"
                )
            return run
        except Exception as exc:
            run.status = "failed"
            run.error_message = str(exc)
            step = current_step(run.checkpoint_json)
            if step:
                await self._mark_run_step(
                    run,
                    step_id=str(step.get("id")),
                    status="failed",
                    level="error",
                    message=f"Failure captured for step '{step.get('title')}'.",
                    error=str(exc),
                )
            if task and task.status != "blocked":
                await self._transition_task_status(task, "failed", run=run, reason=str(exc))
            await self._emit_run_event(
                run,
                event_type="failed",
                level="error",
                message=str(exc),
            )
            run.checkpoint_json = update_query_snapshot(
                run.checkpoint_json,
                data={"latest_status": "failed", "last_error": str(exc), "task_id": run.task_id},
            )
            await self.db.commit()
            if task:
                await self._apply_project_escalation_rules(
                    project, run=run, task=task, trigger="run_failed"
                )
            return run

    async def _execute_single_agent_run(self, run: TaskRun) -> None:
        agent = await self._load_agent_for_run(run.worker_agent_id or run.orchestrator_agent_id)
        provider = await self._resolve_provider_for_run(run, agent)
        task = await self.db.get(OrchestratorTask, run.task_id) if run.task_id else None
        project = await self.db.get(OrchestratorProject, run.project_id)
        if project is None:
            raise RuntimeError("Run project not found")
        prompt = self._workflow_checkpoint_artifact(run, "single_agent.prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            await self._mark_run_step(
                run,
                step_id="build_prompt",
                status="in_progress",
                message="Building task prompt.",
            )
            await self._emit_run_event(
                run, event_type="prompt_building", message="Building task prompt..."
            )
            prompt = await self._build_task_prompt(run, agent)
            self._set_workflow_checkpoint_artifact(run, key="single_agent.prompt", value=prompt)
            await self._mark_run_step(
                run,
                step_id="build_prompt",
                status="completed",
                message="Task prompt checkpoint saved.",
            )

        execution_plan = self._workflow_checkpoint_artifact(run, "single_agent.plan")
        if not isinstance(execution_plan, dict) or not execution_plan:
            await self._mark_run_step(
                run,
                step_id="plan_execution",
                status="in_progress",
                message="Planning single-agent execution.",
            )
            execution_plan = await self._plan_agent_execution(
                run,
                provider=provider,
                agent=agent,
                prompt=prompt,
                purpose="single-agent task execution",
            )
            self._set_workflow_checkpoint_artifact(
                run, key="single_agent.plan", value=execution_plan
            )
            await self._mark_run_step(
                run,
                step_id="plan_execution",
                status="completed",
                message="Execution plan checkpoint saved.",
                metadata={"tool_call_count": len(execution_plan.get("tool_calls", []))},
            )

        tool_results = self._workflow_checkpoint_artifact(run, "single_agent.tool_results")
        if not isinstance(tool_results, list):
            await self._mark_run_step(
                run,
                step_id="run_tools",
                status="in_progress",
                message="Executing planned tools.",
            )
            tool_results = await self._execute_tool_calls(
                run,
                project=project,
                task=task,
                tool_calls=execution_plan.get("tool_calls", []),
                allowed_tools=(agent.allowed_tools_json if agent else []),
                agent=agent,
            )
            self._set_workflow_checkpoint_artifact(
                run, key="single_agent.tool_results", value=tool_results
            )
            await self._mark_run_step(
                run,
                step_id="run_tools",
                status="completed",
                message="Tool results checkpoint saved.",
                metadata={"completed_tools": len(tool_results)},
            )

        final_prompt = self._build_final_prompt(
            base_prompt=prompt,
            execution_plan=execution_plan,
            tool_results=tool_results,
        )
        model_name = run.model_name or (provider.default_model if provider else None)
        await self._mark_run_step(
            run,
            step_id="model_response",
            status="in_progress",
            message=f"Requesting model response ({model_name or 'default'}).",
        )
        await self._emit_run_event(
            run,
            event_type="llm_request",
            message=f"Sending request to model ({model_name or 'default'})...",
            payload={"prompt_chars": len(final_prompt), "tool_calls": len(tool_results)},
        )
        provider, result = await self._execute_with_routing(
            run,
            provider=provider,
            agent=agent,
            system_prompt=agent.system_prompt if agent else "You are a helpful software agent.",
            user_prompt=final_prompt,
            purpose="single-agent execution",
            response_format=self._structured_output_response_format(agent),
        )
        run.output_payload_json = {
            "plan": execution_plan,
            "tool_results": tool_results,
            "summary": result.output_text[:1200],
            "final_output": result.output_text,
            "structured_output_json": result.output_json,
        }
        self._set_workflow_checkpoint_artifact(
            run,
            key="single_agent.output_payload",
            value=run.output_payload_json,
        )
        await self._mark_run_step(
            run,
            step_id="model_response",
            status="completed",
            message="Model response checkpoint saved.",
            metadata={"output_chars": len(result.output_text)},
        )
        await self._mark_run_step(
            run,
            step_id="persist_output",
            status="in_progress",
            message="Persisting execution artifacts.",
        )
        await self._write_artifact(
            run,
            kind="run_output",
            title="Execution output",
            content=result.output_text,
            metadata={"tool_calls": len(tool_results)},
        )
        await self._mark_run_step(
            run,
            step_id="persist_output",
            status="completed",
            message="Execution artifacts persisted.",
        )

    async def _execute_manager_worker_run(self, run: TaskRun) -> None:
        manager = await self._load_agent_for_run(run.orchestrator_agent_id)
        explicit_worker = await self._load_agent_for_run(run.worker_agent_id)
        provider = await self._resolve_provider_for_run(run, explicit_worker or manager)
        task = await self.db.get(OrchestratorTask, run.task_id) if run.task_id else None
        project = await self.db.get(OrchestratorProject, run.project_id)
        if project is None:
            raise RuntimeError("Run project not found")
        if (
            manager
            and explicit_worker
            and not self._delegation_edge_allowed(manager, explicit_worker, project=project)
        ):
            raise RuntimeError(
                "Manager cannot delegate to the selected worker (hierarchy or delegation_rules allowlist)."
            )
        await self._emit_run_event(
            run,
            event_type="manager_planning",
            message="Manager agent building execution graph...",
        )
        manager_plan = self._workflow_checkpoint_artifact(run, "manager_worker.plan")
        routed_sub_tasks = self._workflow_checkpoint_artifact(
            run, "manager_worker.routed_sub_tasks"
        )
        branch_results = self._workflow_checkpoint_artifact(run, "manager_worker.branch_results")

        if not isinstance(manager_plan, dict) or not manager_plan:
            await self._mark_run_step(
                run,
                step_id="planning",
                status="in_progress",
                message="Supervisor is planning delegated work.",
            )
            planning_prompt = await self._build_task_prompt(
                run,
                manager,
                prefix=(
                    "Produce a JSON execution graph with sub_tasks, required_tools, required_capabilities, "
                    "and whether each branch can run in parallel."
                ),
            )
            manager_plan = await self._plan_agent_execution(
                run,
                provider=provider,
                agent=manager,
                prompt=planning_prompt,
                purpose="manager delegation graph",
                default_tool_calls=[],
            )
            self._set_workflow_checkpoint_artifact(
                run, key="manager_worker.plan", value=manager_plan
            )
            await self._mark_run_step(
                run,
                step_id="planning",
                status="completed",
                message="Supervisor plan checkpoint saved.",
                metadata={"sub_task_count": len(manager_plan.get("sub_tasks") or [])},
            )

        sub_tasks = manager_plan.get("sub_tasks") or [
            {
                "title": task.title if task else "Primary task",
                "description": task.description if task else "",
                "required_tools": self._extract_required_tools(task),
                "required_capabilities": self._extract_required_tools(task),
                "parallelizable": False,
            }
        ]

        if not isinstance(routed_sub_tasks, list) or not routed_sub_tasks:
            await self._mark_run_step(
                run,
                step_id="subtask_dispatch",
                status="in_progress",
                message="Supervisor is routing subtasks to workers.",
            )
            candidate_workers = await self._candidate_workers(
                project.id, manager=manager, explicit_worker=explicit_worker, task=task
            )
            routed_sub_tasks = await self._route_sub_tasks_to_agents(
                project.id,
                sub_tasks,
                candidate_workers,
                manager=manager,
                parent_task=task,
            )
            self._set_workflow_checkpoint_artifact(
                run,
                key="manager_worker.routed_sub_tasks",
                value=routed_sub_tasks,
            )
            await self._emit_run_event(
                run,
                event_type="manager_plan",
                message="Manager created an execution graph.",
                payload={"sub_tasks": routed_sub_tasks},
            )
            await self._mark_run_step(
                run,
                step_id="subtask_dispatch",
                status="completed",
                message="Worker routing checkpoint saved.",
            )

        if not isinstance(branch_results, list):
            await self._mark_run_step(
                run,
                step_id="worker_execution",
                status="in_progress",
                message="Executing delegated branches.",
            )
            branch_results = []
            pending_by_id = {str(item.get("branch_id")): item for item in routed_sub_tasks}
            completed_ids: set[str] = set()
            while pending_by_id:
                ready = [
                    item
                    for item in pending_by_id.values()
                    if set(item.get("dependency_ids") or []).issubset(completed_ids)
                ]
                if not ready:
                    branch_results.extend(
                        [
                            {
                                **item,
                                "status": "blocked",
                                "reason": "dependency_cycle_or_missing_dependency",
                                "blocker_reason": "Dependency cycle or missing dependency prevented execution.",
                            }
                            for item in pending_by_id.values()
                        ]
                    )
                    break
                parallel = [item for item in ready if item.get("parallelizable")]
                sequential = [item for item in ready if not item.get("parallelizable")]
                if parallel:
                    scheduled: list[tuple[dict[str, Any], TaskRun]] = []
                    for item in parallel:
                        scheduled.append(
                            (
                                item,
                                await self._create_child_run(
                                    run,
                                    sub_task=item,
                                    assigned_agent_id=item.get("assigned_agent_id"),
                                ),
                            )
                        )
                    branch_results.extend(
                        await asyncio.gather(
                            *[
                                self._execute_subtask_branch(
                                    run,
                                    child_run,
                                    provider,
                                    item,
                                    project=project,
                                    manager=manager,
                                )
                                for item, child_run in scheduled
                            ]
                        )
                    )
                for item in sequential:
                    child_run = await self._create_child_run(
                        run,
                        sub_task=item,
                        assigned_agent_id=item.get("assigned_agent_id"),
                    )
                    branch_results.append(
                        await self._execute_subtask_branch(
                            run,
                            child_run,
                            provider,
                            item,
                            project=project,
                            manager=manager,
                        )
                    )
                completed_ids.update(
                    {
                        str(item.get("branch_id"))
                        for item in branch_results
                        if item.get("status") == "completed"
                    }
                )
                for item in ready:
                    pending_by_id.pop(str(item.get("branch_id")), None)
            self._set_workflow_checkpoint_artifact(
                run,
                key="manager_worker.branch_results",
                value=branch_results,
            )
            await self._mark_run_step(
                run,
                step_id="worker_execution",
                status="completed",
                message="Branch execution checkpoint saved.",
                metadata={"branch_count": len(branch_results)},
            )

        blocked = [item for item in branch_results if item.get("status") == "blocked"]
        self._set_workflow_checkpoint_artifact(
            run, key="manager_worker.blocker_queue", value=blocked
        )
        if blocked:
            await self._mark_run_step(
                run,
                step_id="blocker_resolution",
                status="in_progress",
                message="Supervisor is resolving blockers.",
            )
            if manager:
                _, handoff_result = await self._execute_with_routing(
                    run,
                    provider=provider,
                    agent=manager,
                    system_prompt=manager.system_prompt or "You are an escalation manager.",
                    user_prompt=(
                        "One or more delegated branches are blocked. Resolve the blockers or escalate.\n\n"
                        f"{json.dumps(blocked, indent=2)}"
                    ),
                    purpose="manager escalation",
                )
                await self._emit_run_event(
                    run,
                    event_type="manager_handoff",
                    message="Manager reviewed blocked branches.",
                    payload={
                        "blocked_count": len(blocked),
                        "resolution": handoff_result.output_text[:1000],
                    },
                )
            for item in blocked:
                await self._escalate_blocker(
                    run,
                    task=task,
                    reason=str(
                        item.get("blocker_reason")
                        or item.get("reason")
                        or "Delegated branch blocked"
                    ),
                    metadata={"branch": item},
                )
            raise BlockedExecution(
                "Delegated sub-task execution is blocked and requires escalation"
            )
        await self._mark_run_step(
            run,
            step_id="blocker_resolution",
            status="completed",
            message="No unresolved blockers remain.",
        )
        synthesis_input = json.dumps(branch_results, indent=2)
        synth_agent = explicit_worker or manager
        _, synthesis_result = await self._execute_with_routing(
            run,
            provider=provider,
            agent=synth_agent,
            system_prompt=(
                manager.system_prompt if manager else "You are an orchestration manager."
            ),
            user_prompt=(
                "Synthesize the delegated worker outputs into a final deliverable with decisions, "
                "tradeoffs, and next steps.\n\n"
                f"{synthesis_input}"
            ),
            purpose="manager synthesis",
            response_format=self._structured_output_response_format(synth_agent),
        )
        run.output_payload_json = {
            "manager_plan": manager_plan,
            "branches": branch_results,
            "summary": synthesis_result.output_text[:1200],
            "final_output": synthesis_result.output_text,
        }
        self._set_workflow_checkpoint_artifact(
            run,
            key="manager_worker.output_payload",
            value=run.output_payload_json,
        )
        review_round = (
            int(self._workflow_checkpoint_artifact(run, "manager_worker.review_round", 0) or 0) + 1
        )
        self._set_workflow_checkpoint_artifact(
            run, key="manager_worker.review_round", value=review_round
        )
        await self._mark_run_step(
            run,
            step_id="review",
            status="in_progress",
            message="Reviewer is validating the consolidated result.",
        )
        if run.reviewer_agent_id:
            reviewer = await self._load_agent_for_run(run.reviewer_agent_id)
            _, review_result = await self._execute_with_routing(
                run,
                provider=provider,
                agent=reviewer,
                system_prompt=(
                    reviewer.system_prompt if reviewer else "You are a careful reviewer."
                ),
                user_prompt=(
                    "Review this manager-worker delivery. Return JSON with decision, summary, reasons, checklist, rework_scope.\n\n"
                    f"Task title: {task.title if task else 'Unknown'}\n"
                    f"Acceptance criteria: {task.acceptance_criteria if task else ''}\n"
                    f"Branch results: {json.dumps(branch_results, indent=2, default=str)}\n"
                    f"Final output: {synthesis_result.output_text}"
                ),
                response_format="json",
                purpose="manager-worker review",
            )
            review_payload = (
                review_result.output_json
                if isinstance(review_result.output_json, dict)
                and review_result.output_json.get("decision")
                else self._coerce_review_payload(review_result.output_text)
            )
        else:
            review_payload = {
                "decision": "approved",
                "summary": "No reviewer configured; manager-worker flow auto-approved.",
                "reasons": [],
                "checklist": [],
                "rework_scope": [],
            }
        review_state = self._review_state_from_payload(review_payload, round_number=review_round)
        self._set_workflow_checkpoint_artifact(
            run, key="manager_worker.review_state", value=review_state
        )
        run.output_payload_json["review_state"] = review_state
        if review_state["decision"] != "approved":
            if task:
                self._append_structured_reopen_record(task, review_payload, run=run)
                await self._transition_task_status(
                    task, "planned", run=run, reason="review requested rework"
                )
            affected_scope = set(review_state.get("rework_scope") or [])
            for child in await self._child_runs_for_parent(run.id):
                branch_title = str(
                    ((child.input_payload_json or {}).get("subtask") or {}).get("title") or ""
                )
                if not affected_scope or branch_title in affected_scope:
                    child.status = "planned"
            raise BlockedExecution("Reviewer requested rework on one or more delegated branches")
        await self._mark_run_step(
            run,
            step_id="review",
            status="completed",
            message="Reviewer approved the consolidated result.",
        )
        if task:
            await self._transition_task_status(task, "approved", run=run, reason="review approved")
        await self._mark_run_step(
            run,
            step_id="artifact_publish",
            status="in_progress",
            message="Publishing final artifacts.",
        )
        await self._publish_final_artifacts(
            run,
            branch_results=branch_results,
            review_state=review_state,
        )
        await self._write_artifact(
            run,
            kind="execution_graph",
            title="Manager execution graph",
            content=json.dumps(manager_plan, indent=2),
            metadata={"sub_task_count": len(routed_sub_tasks)},
        )
        await self._mark_run_step(
            run,
            step_id="artifact_publish",
            status="completed",
            message="Final artifacts published.",
        )
        await self._mark_run_step(
            run,
            step_id="github_sync",
            status="in_progress",
            message="Syncing approved result to GitHub policy layer.",
        )
        if task:
            github_state = await self._sync_manager_run_to_github(run, task)
            run.output_payload_json["github_action_state"] = github_state
        await self._mark_run_step(
            run,
            step_id="github_sync",
            status="completed",
            message="GitHub sync stage completed.",
        )

    async def _execute_review_run(self, run: TaskRun) -> None:
        reviewer = await self._load_agent_for_run(run.reviewer_agent_id or run.worker_agent_id)
        provider = await self._resolve_provider_for_run(run, reviewer)
        task = await self.db.get(OrchestratorTask, run.task_id) if run.task_id else None
        await self._mark_run_step(
            run,
            step_id="review",
            status="in_progress",
            message="Reviewer is evaluating the task result.",
        )
        gh_review = (run.input_payload_json or {}).get("github_pr_review")
        extra_ctx = ""
        if isinstance(gh_review, dict):
            extra_ctx = (
                "\n\nExternal GitHub PR review context:\n"
                f"State: {gh_review.get('state')}\n"
                f"Author: {gh_review.get('author_login')}\n"
                f"Body:\n{gh_review.get('body') or ''}\n"
            )
        _, result = await self._execute_with_routing(
            run,
            provider=provider,
            agent=reviewer,
            system_prompt=(reviewer.system_prompt if reviewer else "You are a careful reviewer."),
            user_prompt=(
                "Review this task result and return a single JSON object with:\n"
                '- decision: "approved" or "rework"\n'
                "- summary: short string\n"
                "- reasons: array of strings (each a concrete issue or gap)\n"
                "- checklist: array of actionable strings the worker must verify before resubmitting\n\n"
                f"Task title: {task.title if task else 'Unknown'}\n"
                f"Task summary: {task.result_summary if task else ''}\n"
                f"Acceptance criteria: {task.acceptance_criteria if task else ''}\n"
                f"Latest structured reopen (if any): {json.dumps((task.metadata_json or {}).get('latest_reopen'), default=str) if task else {}}"
                f"{extra_ctx}"
            ),
            response_format="json",
            purpose="review",
        )
        review_payload = (
            result.output_json
            if isinstance(result.output_json, dict) and result.output_json.get("decision")
            else self._coerce_review_payload(result.output_text)
        )
        run.output_payload_json = {
            "summary": str(review_payload.get("summary") or result.output_text)[:1200],
            "review": result.output_text,
            "decision": review_payload.get("decision"),
        }
        await self._mark_run_step(
            run,
            step_id="review",
            status="completed",
            message="Reviewer produced a structured verdict.",
        )
        if task:
            if review_payload.get("decision") == "approved":
                project = await self.db.get(OrchestratorProject, task.project_id)
                advanced = await self._advance_task_reviewer_chain(
                    task, project, run.reviewer_agent_id
                )
                if advanced:
                    run.output_payload_json["next_reviewer_agent_id"] = task.reviewer_agent_id
                    await self._emit_run_event(
                        run,
                        event_type="review_handoff",
                        message="Review approved and handed off to the next reviewer in chain.",
                        payload={"next_reviewer_agent_id": task.reviewer_agent_id},
                    )
                else:
                    await self._transition_task_status(
                        task, "approved", run=run, reason="review approved"
                    )
            else:
                self._append_structured_reopen_record(task, review_payload, run=run)
                await self._transition_task_status(
                    task, "planned", run=run, reason="review requested rework"
                )
                await self._emit_run_event(
                    run,
                    event_type="reopened",
                    level="warning",
                    message="Task reopened for rework after review (structured checklist recorded).",
                    payload=review_payload,
                )
            await self._post_reviewer_pr_comment(
                run,
                task,
                str(review_payload.get("summary") or result.output_text),
            )
            await self._mark_run_step(
                run,
                step_id="artifact_publish",
                status="in_progress",
                message="Publishing review artifacts.",
            )
            await self._write_artifact(
                run,
                kind="review",
                title="Review verdict",
                content=json.dumps(review_payload, indent=2, default=str),
                metadata={"task_id": task.id},
            )
            await self._mark_run_step(
                run,
                step_id="artifact_publish",
                status="completed",
                message="Review artifacts published.",
            )
            await self._mark_run_step(
                run,
                step_id="github_sync",
                status="in_progress",
                message="Applying GitHub review automation.",
            )
            await self._sync_run_completion_to_github(run, task)
            run.output_payload_json["github_action_state"] = {
                "completed": True,
                "last_synced_at": datetime.now(UTC).isoformat(),
                "mode": "review",
            }
            await self._mark_run_step(
                run,
                step_id="github_sync",
                status="completed",
                message="GitHub review automation completed.",
            )

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
    ) -> None:
        await self.repo.create_run_event(
            run_id=run.id,
            task_id=run.task_id,
            event_type=event_type,
            level=level,
            message=message,
            payload_json=payload or {},
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd_micros=cost_usd_micros,
        )
        await self._refresh_run_scratchpad(run)
        await self.db.commit()

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

    async def _plan_agent_execution(
        self,
        run: TaskRun,
        *,
        provider: ProviderConfig | None,
        agent,
        prompt: str,
        purpose: str,
        default_tool_calls: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        explicit = run.input_payload_json.get("tool_calls")
        explicit_subtasks = run.input_payload_json.get("sub_tasks")
        if explicit or explicit_subtasks:
            return {
                "summary": "Using explicit input payload plan.",
                "tool_calls": explicit or default_tool_calls or [],
                "sub_tasks": explicit_subtasks or [],
            }
        _, planning_result = await self._execute_with_routing(
            run,
            provider=provider,
            agent=agent,
            system_prompt=(agent.system_prompt if agent else "You are a planning agent."),
            user_prompt=(
                f"{prompt}\n\nReturn JSON for {purpose} with keys: summary, blocked_reason, tool_calls, "
                "and sub_tasks. Each tool call must contain tool and arguments."
            ),
            response_format="json",
            purpose=purpose,
        )
        payload = planning_result.output_json or {}
        if not isinstance(payload, dict):
            payload = {}
        tool_calls = payload.get("tool_calls")
        if not isinstance(tool_calls, list):
            tool_calls = default_tool_calls or []
        sub_tasks = payload.get("sub_tasks")
        if not isinstance(sub_tasks, list):
            sub_tasks = []
        blocked_reason = payload.get("blocked_reason")
        if blocked_reason:
            raise BlockedExecution(str(blocked_reason))
        return {
            "summary": str(payload.get("summary") or planning_result.output_text[:500]),
            "tool_calls": tool_calls,
            "sub_tasks": sub_tasks,
        }

    async def _execute_tool_calls(
        self,
        run: TaskRun,
        *,
        project: OrchestratorProject,
        task: OrchestratorTask | None,
        tool_calls: list[dict[str, Any]],
        allowed_tools: list[str] | None,
        agent: AgentProfile | None = None,
    ) -> list[dict[str, Any]]:
        if not tool_calls:
            return []
        if agent and not self._tool_calling_allowed(agent):
            await self._emit_run_event(
                run,
                event_type="tool_calls_skipped",
                level="warning",
                message="Tool calls were skipped because tool_calling_enabled is false for this agent.",
                payload={"requested": [str(c.get("tool") or "") for c in tool_calls]},
            )
            return [
                {
                    "tool": str(call.get("tool") or ""),
                    "status": "skipped",
                    "error": "Tool calling disabled by agent model policy.",
                }
                for call in tool_calls
            ]
        toolbox = OrchestrationToolbox(
            db=self.db, repo=self.repo, project=project, task=task, run=run
        )
        results: list[dict[str, Any]] = []
        failures = 0
        effective_allowed = set(allowed_tools or [])
        dangerous_tools = {
            "code_execute",
            "db_query",
            "fs_write",
            "github_create_pr",
            "github_label_issue",
        }
        hitl_settings = (project.settings_json or {}).get("hitl") or {}
        secret_scope = str(hitl_settings.get("secret_scope") or "project_default")
        for index, call in enumerate(tool_calls, start=1):
            tool_name = str(call.get("tool") or "").strip()
            self._tool_allowed_for_agent_permissions(tool_name, agent)
            if self.action_requires_approval(project, "run_tool") and tool_name in dangerous_tools:
                grant_consumed = await self._consume_hitl_grant(
                    run,
                    "dangerous_tool_call",
                    {"tool": tool_name, "tool_call_index": index},
                )
                if not grant_consumed:
                    approval = await self.repo.create_approval(
                        project_id=project.id,
                        task_id=task.id if task else None,
                        run_id=run.id,
                        issue_link_id=task.github_issue_link_id if task else None,
                        requested_by_user_id=run.triggered_by_user_id,
                        approval_type="dangerous_tool_call",
                        status="pending",
                        payload_json={
                            "tool": tool_name,
                            "tool_call_index": index,
                            "arguments": call.get("arguments") or {},
                        },
                    )
                    await self.db.commit()
                    raise BlockedExecution(
                        f"Dangerous tool '{tool_name}' requires approval (approval_id={approval.id})."
                    )
            if secret_scope == "deny_external" and tool_name in {
                "github_comment",
                "github_label_issue",
                "github_create_pr",
                "web_fetch",
                "web_search",
            }:
                raise BlockedExecution(
                    f"Tool '{tool_name}' blocked by secret scope policy ({secret_scope})."
                )
            if effective_allowed and tool_name not in effective_allowed:
                raise BlockedExecution(f"Tool '{tool_name}' is not allowed for this agent")
            await self._emit_run_event(
                run,
                event_type="tool_call_started",
                message=f"Executing tool {tool_name}.",
                payload={"index": index, "tool": tool_name},
            )
            try:
                result = await toolbox.execute(call)
            except ToolExecutionError as exc:
                failures += 1
                await self._emit_run_event(
                    run,
                    event_type="tool_call_failed",
                    level="warning",
                    message=str(exc),
                    payload={"tool": tool_name, "index": index},
                )
                results.append({"tool": tool_name, "status": "failed", "error": str(exc)})
                if failures >= 2:
                    await self._escalate_blocker(
                        run,
                        task=task,
                        reason="Multiple tool failures detected during execution.",
                        metadata={"tool_failures": failures},
                    )
                    raise BlockedExecution(
                        "Task blocked after repeated tool-call failures"
                    ) from exc
                continue
            results.append({"tool": tool_name, "status": "completed", "result": result})
            await self._emit_run_event(
                run,
                event_type="tool_call_completed",
                message=f"Tool {tool_name} completed.",
                payload={
                    "index": index,
                    "tool": tool_name,
                    "result_preview": json.dumps(result, default=str)[:500],
                },
            )
            await self._write_artifact(
                run,
                kind="tool_result",
                title=f"Tool result: {tool_name}",
                content=json.dumps(result, default=str, indent=2)[:12000],
                metadata={"tool": tool_name},
            )
        return results

    def _build_final_prompt(
        self,
        *,
        base_prompt: str,
        execution_plan: dict[str, Any],
        tool_results: list[dict[str, Any]],
    ) -> str:
        sections = [base_prompt]
        if execution_plan.get("summary"):
            sections.append(f"Execution plan summary:\n{execution_plan['summary']}")
        if tool_results:
            sections.append(f"Tool results:\n{json.dumps(tool_results, indent=2, default=str)}")
        sections.append(
            "Produce the final task output. Include concrete next steps, note blockers if any remain, "
            "and keep the response usable as a task artifact."
        )
        return "\n\n".join(section for section in sections if section)

    async def _write_artifact(
        self,
        run: TaskRun,
        *,
        kind: str,
        title: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if run.task_id is None:
            return
        await self.repo.create_task_artifact(
            task_id=run.task_id,
            run_id=run.id,
            kind=kind,
            title=title,
            content=content,
            metadata_json=metadata or {},
        )
        await self.db.commit()

    async def _apply_result_metrics(
        self,
        run: TaskRun,
        provider: ProviderConfig | None,
        results: list,
        *,
        agent=None,
        append: bool = False,
    ) -> None:
        total_in = sum(item.input_tokens for item in results)
        total_out = sum(item.output_tokens for item in results)
        total_latency = sum(item.latency_ms for item in results)
        if append:
            run.token_input += total_in
            run.token_output += total_out
            run.latency_ms = (run.latency_ms or 0) + total_latency
        else:
            run.token_input = total_in
            run.token_output = total_out
            run.latency_ms = total_latency
        run.token_total = run.token_input + run.token_output
        model_name = results[-1].model_name if results else run.model_name
        run.estimated_cost_micros = self._estimate_cost_micros(
            provider,
            run.token_input,
            run.token_output,
            model_name=model_name,
        )
        token_budget = (agent.budget_json or {}).get("token_budget") if agent else None
        if token_budget and run.token_total > int(token_budget):
            await self._emit_run_event(
                run,
                event_type="budget_exceeded",
                level="warning",
                message=f"Token budget {token_budget} exceeded ({run.token_total} used).",
            )

    async def _advance_task_reviewer_chain(
        self,
        task: OrchestratorTask,
        project: OrchestratorProject | None,
        reviewer_agent_id: str | None,
    ) -> bool:
        chain = self._reviewer_chain_for_project(project)
        if not chain or not reviewer_agent_id:
            return False
        try:
            current_index = chain.index(str(reviewer_agent_id))
        except ValueError:
            return False
        if current_index >= len(chain) - 1:
            return False
        next_reviewer_id = chain[current_index + 1]
        metadata = dict(task.metadata_json or {})
        metadata["review_chain"] = {
            "reviewer_agent_ids": chain,
            "current_index": current_index + 1,
            "last_completed_reviewer_agent_id": reviewer_agent_id,
        }
        task.metadata_json = metadata
        task.reviewer_agent_id = next_reviewer_id
        if hasattr(task, "_sa_instance_state"):
            orm_attributes.flag_modified(task, "metadata_json")
        return True

    async def _apply_project_escalation_rules(
        self,
        project: OrchestratorProject,
        *,
        run: TaskRun,
        task: OrchestratorTask,
        trigger: str,
        rounds_completed: int | None = None,
        consensus_reached: bool | None = None,
    ) -> None:
        rules = self._project_execution_settings(project).get("escalation_rules", [])
        if not isinstance(rules, list):
            return
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            escalate_to = rule.get("escalate_to") or self._project_execution_settings(project).get(
                "manager_agent_id"
            )
            condition = rule.get("condition")
            if condition == "stuck_for_minutes" and trigger in {"task_blocked", "run_failed"}:
                threshold = int(rule.get("value", 0) or 0)
                if threshold <= 0:
                    continue
                started_at = run.started_at or run.created_at
                elapsed_minutes = int((datetime.now(UTC) - started_at).total_seconds() / 60)
                if elapsed_minutes >= threshold:
                    await self.repo.create_approval(
                        project_id=project.id,
                        task_id=task.id,
                        run_id=run.id,
                        requested_by_user_id=run.triggered_by_user_id,
                        approval_type="rule_escalation",
                        status="pending",
                        payload_json={
                            "condition": condition,
                            "value": threshold,
                            "elapsed_minutes": elapsed_minutes,
                            "escalate_to": escalate_to,
                        },
                    )
            if condition == "cost_exceeds_usd" and trigger == "run_completed":
                threshold = float(rule.get("value", 0) or 0)
                cost_usd = run.estimated_cost_micros / 1_000_000
                if threshold > 0 and cost_usd > threshold:
                    await self.repo.create_approval(
                        project_id=project.id,
                        task_id=task.id,
                        run_id=run.id,
                        requested_by_user_id=run.triggered_by_user_id,
                        approval_type="rule_escalation",
                        status="pending",
                        payload_json={
                            "condition": condition,
                            "value": threshold,
                            "cost_usd": cost_usd,
                            "escalate_to": escalate_to,
                        },
                    )
            if condition == "no_consensus_after_rounds" and trigger == "brainstorm_finished":
                threshold = int(rule.get("value", 0) or 0)
                if (
                    threshold > 0
                    and consensus_reached is False
                    and (rounds_completed or 0) >= threshold
                ):
                    await self.repo.create_approval(
                        project_id=project.id,
                        task_id=task.id,
                        run_id=run.id,
                        requested_by_user_id=run.triggered_by_user_id,
                        approval_type="rule_escalation",
                        status="pending",
                        payload_json={
                            "condition": condition,
                            "value": threshold,
                            "rounds_completed": rounds_completed,
                            "escalate_to": escalate_to,
                        },
                    )
        await self.db.commit()

    async def _escalate_blocker(
        self,
        run: TaskRun,
        *,
        task: OrchestratorTask | None,
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        escalate_to_agent_id = run.orchestrator_agent_id or task.reviewer_agent_id if task else None
        await self.repo.create_approval(
            project_id=run.project_id,
            task_id=task.id if task else None,
            run_id=run.id,
            requested_by_user_id=run.triggered_by_user_id,
            approval_type="task_escalation",
            status="pending",
            payload_json={
                "reason": reason,
                "escalate_to_agent_id": escalate_to_agent_id,
                "metadata": metadata or {},
            },
        )
        await self.db.commit()

    def _coerce_review_payload(self, text: str) -> dict[str, Any]:
        stripped = text.strip()
        if stripped.startswith("{"):
            try:
                data = json.loads(stripped)
                if isinstance(data, dict) and data.get("decision"):
                    reasons = data.get("reasons")
                    if isinstance(reasons, str):
                        reasons = [reasons]
                    elif not isinstance(reasons, list):
                        reasons = []
                    checklist = data.get("checklist")
                    if not isinstance(checklist, list):
                        checklist = []
                    return {
                        "decision": str(data.get("decision")),
                        "summary": str(data.get("summary") or stripped[:1200]),
                        "reasons": [str(x) for x in reasons],
                        "checklist": [str(x) for x in checklist],
                    }
            except json.JSONDecodeError:
                pass
        lowered = stripped.lower()
        decision = "approved" if "approve" in lowered and "rework" not in lowered else "rework"
        return {"decision": decision, "summary": stripped[:1200], "reasons": [], "checklist": []}
