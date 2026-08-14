"""Execution snapshot and explainability read models."""

from __future__ import annotations

from typing import Any

from backend.modules.identity_access.models import User
from backend.modules.orchestration.execution.execution_state import (
    EXECUTION_SNAPSHOT_SCHEMA_VERSION,
    EXECUTION_TRUTH_DESCRIPTION,
    SNAPSHOT_SOURCES_RUN,
    SNAPSHOT_SOURCES_TASK,
    checkpoint_excerpt,
    extract_execution_memory_details,
    extract_execution_metadata_views,
)
from backend.modules.orchestration.execution.result_contracts import EXTERNAL_ACTION_STEP_ID
from backend.modules.orchestration.models import TaskRun
from backend.modules.projects.orchestration_models import OrchestratorTask


class ExecutionSnapshotsMixin:
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
            "external_action_state": stage_state.get(EXTERNAL_ACTION_STEP_ID)
            or stage_state.get("github_sync")
            or {},
            "github_action_state": stage_state.get(EXTERNAL_ACTION_STEP_ID)
            or stage_state.get("github_sync")
            or {},
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
            "external_action_state": stage_state.get(EXTERNAL_ACTION_STEP_ID)
            or stage_state.get("github_sync")
            or {},
            "github_action_state": stage_state.get(EXTERNAL_ACTION_STEP_ID)
            or stage_state.get("github_sync")
            or {},
            "resumable": self._run_is_resumable(run),
        }


    async def get_run_durable_workflow(self, user: User, run_id: str) -> dict[str, Any]:
        run = await self.get_run(user, run_id)
        return self._durable_workflow_payload(run)


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

