"""Pure execution result contracts, subtask graph normalization, and snapshot helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from backend.modules.orchestration.execution.execution_workflow import (
    current_step,
    durable_handle,
    get_workflow_artifact,
    workflow_state,
)
from backend.modules.projects.orchestration_models import OrchestratorTask

EXTERNAL_ACTION_STEP_ID = "external_action_sync"


def run_event_tail_payloads(events: list[Any], *, limit: int = 12) -> list[dict[str, Any]]:
    tail = events[-limit:] if len(events) > limit else events
    out: list[dict[str, Any]] = []
    for event in tail:
        msg = event.message or ""
        if len(msg) > 400:
            msg = msg[:400] + "…"
        out.append(
            {
                "event_type": event.event_type,
                "level": event.level,
                "message": msg,
                "created_at": event.created_at,
            }
        )
    return out


def normalize_subtask_graph(
    sub_tasks: list[dict[str, Any]],
    *,
    parent_task: OrchestratorTask | None,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(sub_tasks):
        branch_id = str(item.get("branch_id") or item.get("id") or f"branch-{index + 1}").strip()
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
                    str(value) for value in (item.get("required_tools") or []) if str(value).strip()
                ],
                "required_capabilities": [
                    str(value)
                    for value in (item.get("required_capabilities") or [])
                    if str(value).strip()
                ],
                "parallelizable": bool(item.get("parallelizable", False)),
                "manager_notes": str(item.get("manager_notes") or ""),
                "dependency_ids": dep_ids,
                "tool_calls": list(item.get("tool_calls") or []),
                "rework_scope": list(item.get("rework_scope") or []),
            }
        )
    return normalized


def worker_result_contract(
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
        "artifacts": list(payload.get("artifacts") or []),
        "evidence": list(payload.get("evidence") or payload.get("evidence_refs") or []),
        "decisions": list(payload.get("decisions") or []),
        "risks": [str(value) for value in risks if str(value).strip()],
        "tool_calls": list(payload.get("tool_calls") or []),
        "external_actions": list(payload.get("external_actions") or []),
        "blockers": list(payload.get("blockers") or []),
        "metrics": dict(payload.get("metrics") or {}),
        "blocker_reason": str(payload.get("blocker_reason") or ""),
        "rework_scope": [
            str(value)
            for value in (payload.get("rework_scope") or sub_task.get("rework_scope") or [])
            if str(value).strip()
        ],
        "raw_output": output_text,
        "changed_files": [str(value) for value in changed_files if str(value).strip()],
        "evidence_refs": [str(value) for value in evidence_refs if str(value).strip()],
    }


def review_state_from_payload(
    review_payload: dict[str, Any], *, round_number: int
) -> dict[str, Any]:
    return {
        "round": round_number,
        "decision": str(review_payload.get("decision") or "rework"),
        "summary": str(review_payload.get("summary") or "")[:1200],
        "reasons": [
            str(value) for value in (review_payload.get("reasons") or []) if str(value).strip()
        ],
        "checklist": [
            str(value) for value in (review_payload.get("checklist") or []) if str(value).strip()
        ],
        "rework_scope": [
            str(value) for value in (review_payload.get("rework_scope") or []) if str(value).strip()
        ],
        "last_reviewed_at": datetime.now(UTC).isoformat(),
    }


def run_is_resumable(*, status: str, checkpoint_json: dict[str, Any]) -> bool:
    if status not in {"failed", "blocked"}:
        return False
    step = current_step(checkpoint_json)
    return bool(step and step.get("resumable", True))


def stage_state_payload(checkpoint_json: dict[str, Any]) -> dict[str, Any]:
    external_action = get_workflow_artifact(
        checkpoint_json, "manager_worker.github_action_state", {}
    )
    return {
        "manager_plan": get_workflow_artifact(checkpoint_json, "manager_worker.plan", {}),
        "routed_sub_tasks": get_workflow_artifact(
            checkpoint_json, "manager_worker.routed_sub_tasks", []
        ),
        "branch_results": get_workflow_artifact(
            checkpoint_json, "manager_worker.branch_results", []
        ),
        "review": get_workflow_artifact(checkpoint_json, "manager_worker.review_state", {}),
        EXTERNAL_ACTION_STEP_ID: external_action,
        "github_sync": external_action,
    }


def durable_workflow_payload(
    checkpoint_json: dict[str, Any],
    *,
    resumable: bool,
) -> dict[str, Any]:
    state = workflow_state(checkpoint_json)
    migration = dict(state.get("migration") or {})
    return {
        "workflow_id": state.get("workflow_id"),
        "backend": state.get("backend"),
        "schema_version": state.get("schema_version"),
        "status": state.get("status"),
        "execution_handle": durable_handle(checkpoint_json),
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
        "resumable": resumable,
    }
