"""Checkpointed execution workflow helpers.

The durable workflow state lives inside ``TaskRun.checkpoint_json`` so it can survive retries,
worker crashes, and replayed runs without introducing new tables.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

WORKFLOW_STATE_KEY = "durable_workflow_v1"


def utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


def normalize_workflow_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in steps:
        step_id = str(item.get("id") or "").strip()
        if not step_id:
            continue
        normalized.append(
            {
                "id": step_id,
                "title": str(item.get("title") or step_id.replace("_", " ").title()),
                "actor": str(item.get("actor") or "system"),
                "status": str(item.get("status") or "pending"),
                "started_at": item.get("started_at"),
                "completed_at": item.get("completed_at"),
                "resumable": bool(item.get("resumable", True)),
                "attempts": int(item.get("attempts") or 0),
                "last_error": str(item.get("last_error") or "") or None,
                "metadata": dict(item.get("metadata") or {}),
            }
        )
    return normalized


def ensure_workflow_state(
    checkpoint_json: dict[str, Any] | None,
    *,
    run_mode: str,
    steps: list[dict[str, Any]],
) -> dict[str, Any]:
    checkpoint = dict(checkpoint_json or {})
    state = dict(checkpoint.get(WORKFLOW_STATE_KEY) or {})
    state.setdefault("schema_version", "1.0")
    state.setdefault("backend", "celery_checkpointed")
    state.setdefault("run_mode", run_mode)
    state.setdefault("status", "pending")
    state.setdefault("created_at", utcnow_iso())
    state.setdefault("updated_at", state["created_at"])
    state.setdefault("resume_count", 0)
    state.setdefault("recovery_count", 0)
    state.setdefault("current_step_id", None)
    state.setdefault("last_completed_step_id", None)
    state.setdefault("last_failure", None)
    state.setdefault("artifacts", {})
    state["steps"] = normalize_workflow_steps(
        list(state.get("steps") or []) or deepcopy(steps)
    )
    if not state["steps"]:
        state["steps"] = normalize_workflow_steps(steps)
    checkpoint[WORKFLOW_STATE_KEY] = state
    return checkpoint


def workflow_state(checkpoint_json: dict[str, Any] | None) -> dict[str, Any]:
    return dict((checkpoint_json or {}).get(WORKFLOW_STATE_KEY) or {})


def workflow_steps(checkpoint_json: dict[str, Any] | None) -> list[dict[str, Any]]:
    return list(workflow_state(checkpoint_json).get("steps") or [])


def current_step(checkpoint_json: dict[str, Any] | None) -> dict[str, Any] | None:
    state = workflow_state(checkpoint_json)
    step_id = state.get("current_step_id")
    if not step_id:
        return None
    for item in state.get("steps") or []:
        if item.get("id") == step_id:
            return dict(item)
    return None


def mark_step(
    checkpoint_json: dict[str, Any] | None,
    *,
    step_id: str,
    status: str,
    error: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    checkpoint = dict(checkpoint_json or {})
    state = dict(checkpoint.get(WORKFLOW_STATE_KEY) or {})
    now = utcnow_iso()
    steps: list[dict[str, Any]] = []
    last_completed = state.get("last_completed_step_id")
    current_step_id: str | None = state.get("current_step_id")
    for item in state.get("steps") or []:
        updated = dict(item)
        if updated.get("id") == step_id:
            updated["status"] = status
            updated["metadata"] = {**dict(updated.get("metadata") or {}), **dict(metadata or {})}
            if status == "in_progress":
                updated["started_at"] = updated.get("started_at") or now
                updated["attempts"] = int(updated.get("attempts") or 0) + 1
                current_step_id = step_id
            elif status == "completed":
                updated["completed_at"] = now
                updated["last_error"] = None
                current_step_id = None
                last_completed = step_id
            elif status in {"failed", "blocked"}:
                updated["last_error"] = error or updated.get("last_error")
                current_step_id = step_id
            elif status == "pending":
                updated["started_at"] = None
                updated["completed_at"] = None
                updated["last_error"] = None
            if error and status in {"failed", "blocked"}:
                updated["last_error"] = error
        steps.append(updated)
    state["steps"] = steps
    state["current_step_id"] = current_step_id
    state["last_completed_step_id"] = last_completed
    state["status"] = status
    state["updated_at"] = now
    if status in {"failed", "blocked"}:
        state["last_failure"] = {
            "step_id": step_id,
            "status": status,
            "error": error or "",
            "at": now,
        }
        state["recovery_count"] = int(state.get("recovery_count") or 0) + 1
    checkpoint[WORKFLOW_STATE_KEY] = state
    return checkpoint


def increment_resume_count(checkpoint_json: dict[str, Any] | None) -> dict[str, Any]:
    checkpoint = dict(checkpoint_json or {})
    state = dict(checkpoint.get(WORKFLOW_STATE_KEY) or {})
    state["resume_count"] = int(state.get("resume_count") or 0) + 1
    state["updated_at"] = utcnow_iso()
    checkpoint[WORKFLOW_STATE_KEY] = state
    return checkpoint


def set_workflow_artifact(
    checkpoint_json: dict[str, Any] | None,
    *,
    key: str,
    value: Any,
) -> dict[str, Any]:
    checkpoint = dict(checkpoint_json or {})
    state = dict(checkpoint.get(WORKFLOW_STATE_KEY) or {})
    artifacts = dict(state.get("artifacts") or {})
    artifacts[key] = value
    state["artifacts"] = artifacts
    state["updated_at"] = utcnow_iso()
    checkpoint[WORKFLOW_STATE_KEY] = state
    return checkpoint


def get_workflow_artifact(checkpoint_json: dict[str, Any] | None, key: str, default: Any = None) -> Any:
    return workflow_state(checkpoint_json).get("artifacts", {}).get(key, default)


def summarize_trace(checkpoint_json: dict[str, Any] | None) -> list[dict[str, Any]]:
    state = workflow_state(checkpoint_json)
    steps = list(state.get("steps") or [])
    current = state.get("current_step_id")
    out: list[dict[str, Any]] = []
    for index, item in enumerate(steps, start=1):
        out.append(
            {
                "step_id": item.get("id"),
                "title": item.get("title"),
                "actor": item.get("actor"),
                "status": item.get("status"),
                "sequence": index,
                "started_at": item.get("started_at"),
                "completed_at": item.get("completed_at"),
                "last_error": item.get("last_error"),
                "is_current": item.get("id") == current,
                "resumable": bool(item.get("resumable", True)),
                "attempts": int(item.get("attempts") or 0),
                "metadata": dict(item.get("metadata") or {}),
            }
        )
    return out
