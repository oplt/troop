"""Layer 1 — authoritative execution state (memory architecture Phase 1).

Execution truth lives in **relational rows and append-only events**, not in vector search.
Celery (see ``submit_orchestration_run``) is the **durable start signal** for worker
execution; the **source of truth** for outcomes remains ``task_runs`` + ``run_events``
in Postgres until/unless Temporal workflow history replaces that (ADR 0004).

**Semantic / RAG** (``_search_project_knowledge``, document chunk embeddings) may only
**enrich prompts** — it must never decide run lifecycle, task status transitions, or
approval outcomes.
"""

from __future__ import annotations

from typing import Any

EXECUTION_SNAPSHOT_SCHEMA_VERSION = "1.0"

# Documented first-class execution fields (existing columns / JSON keys — no new tables).
TASK_RUN_CORE_FIELDS = (
    "id",
    "project_id",
    "task_id",
    "status",
    "run_mode",
    "orchestrator_agent_id",
    "worker_agent_id",
    "reviewer_agent_id",
    "attempt_number",
    "retry_count",
    "error_message",
    "started_at",
    "completed_at",
    "checkpoint_json",
)

RUN_EVENT_SIGNAL_TYPES = frozenset(
    {
        "started",
        "completed",
        "failed",
        "blocked",
        "cancelled",
        "queued",
        "tool_call_started",
        "tool_call_completed",
        "tool_call_failed",
        "tool_calls_skipped",
        "reopened",
        "brainstorm_round",
        "brainstorm_finalized",
    }
)

EXECUTION_TRUTH_DESCRIPTION = (
    "Authoritative execution state is read from PostgreSQL: TaskRun + RunEvent + "
    "OrchestratorTask + ApprovalRequest + GithubSyncEvent. "
    "Queue backend (Celery) delivers work; it does not replace the run row. "
    "Vector search over project_document_chunks is not used for these reads."
)


def extract_execution_metadata_views(task_metadata: dict[str, Any] | None) -> dict[str, Any]:
    """Split task.metadata_json into handoff/hint keys vs opaque tail for snapshots."""
    meta = dict(task_metadata or {})
    handoff: dict[str, Any] = {}
    rest_keys: list[str] = []
    for key, value in meta.items():
        lk = key.lower()
        if lk.startswith("suggested_handoff") or "handoff" in lk or lk.startswith("sla_"):
            handoff[key] = value
        else:
            rest_keys.append(key)
    execution_memory_ref = None
    em = meta.get("execution_memory")
    if isinstance(em, dict) and em.get("last_run_id"):
        execution_memory_ref = {
            "last_run_id": em.get("last_run_id"),
            "last_completed_at": em.get("last_completed_at"),
            "has_diff": bool(em.get("since_last_run_unified_diff")),
        }
    return {
        "handoff_and_sla_hints": handoff,
        "other_metadata_keys": sorted(rest_keys),
        "execution_memory_ref": execution_memory_ref,
    }


def extract_execution_memory_details(task_metadata: dict[str, Any] | None) -> dict[str, Any]:
    meta = dict(task_metadata or {})
    em = meta.get("execution_memory")
    if not isinstance(em, dict):
        return {}
    return {
        "last_run_id": em.get("last_run_id"),
        "last_completed_at": em.get("last_completed_at"),
        "previous_summary_excerpt": em.get("previous_summary_excerpt") or "",
        "latest_summary_excerpt": em.get("latest_summary_excerpt") or "",
        "since_last_run_unified_diff": em.get("since_last_run_unified_diff") or "",
    }


def checkpoint_excerpt(
    checkpoint_json: dict[str, Any] | None, *, max_str: int = 500
) -> dict[str, Any]:
    """Bounded subset of ``TaskRun.checkpoint_json`` for snapshots (no vector reads)."""
    cp = dict(checkpoint_json or {})
    keys = (
        "next_step",
        "scratchpad",
        "last_assistant_preview",
        "blocking_reason",
        "tool_failure",
        "objective",
        "open_questions",
    )
    out: dict[str, Any] = {}
    for key in keys:
        if key not in cp:
            continue
        value = cp[key]
        if isinstance(value, str) and len(value) > max_str:
            value = value[:max_str] + "…"
        out[key] = value
    wm = cp.get("working_memory_v1")
    if isinstance(wm, dict):
        for wkey in ("objective", "open_questions", "latest_findings"):
            val = wm.get(wkey)
            if isinstance(val, str) and val.strip():
                excerpt = val.strip()
                if len(excerpt) > max_str:
                    excerpt = excerpt[:max_str] + "…"
                out[f"working_memory.{wkey}"] = excerpt
    return out


SNAPSHOT_SOURCES_TASK = [
    "orchestrator_tasks",
    "task_runs",
    "run_events",
    "approval_requests",
    "github_sync_events",
]

SNAPSHOT_SOURCES_RUN = [
    "task_runs",
    "run_events",
    "approval_requests",
    "github_sync_events",
]
