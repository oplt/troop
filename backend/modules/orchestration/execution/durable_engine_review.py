"""Durable engine migration review gate (ARCH-001).

Collects production evidence against ARCHITECTURE.md triggers and recommends deferring
Temporal/DBOS/Restate migration unless at least two triggers are met. Preserves the
``submit_orchestration_run`` adapter boundary — no migration is performed here.
"""

from __future__ import annotations

import time
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any

from backend.modules.orchestration.execution.durable_execution import (
    SUPPORTED_DURABLE_BACKENDS,
    durable_backend_status,
)
from backend.modules.orchestration.execution.execution_workflow import WORKFLOW_STATE_KEY

# Re-evaluate when at least two triggers have production evidence (troop-audit/ARCHITECTURE.md §5).
TRIGGERS_REQUIRED_FOR_REVIEW = 2

DURABLE_ENGINE_ALTERNATIVES = (
    {"id": "celery_postgres", "label": "Celery + PostgreSQL checkpoints", "status": "active"},
    {"id": "temporal", "label": "Temporal", "status": "deferred"},
    {"id": "dbos", "label": "DBOS", "status": "deferred"},
    {"id": "restate", "label": "Restate", "status": "deferred"},
)

DURABLE_ENGINE_MIGRATION_TRIGGERS: list[dict[str, Any]] = [
    {
        "id": "long_lived_workflows",
        "label": "Workflows routinely wait days/weeks",
        "source": "troop-audit/ARCHITECTURE.md",
        "evidence_keys": ("runs_over_48h", "runs_over_7d"),
        "thresholds": {"runs_over_48h": 10, "runs_over_7d": 3},
    },
    {
        "id": "signal_query_operators",
        "label": "Operators need arbitrary signal/query APIs",
        "source": "troop-audit/ARCHITECTURE.md",
        "evidence_keys": ("workflow_signal_events",),
        "thresholds": {"workflow_signal_events": 20},
    },
    {
        "id": "retry_recovery_burden",
        "label": "Retry/checkpoint recovery consumes engineering time",
        "source": "troop-audit/ARCHITECTURE.md",
        "evidence_keys": ("workflow_recovery_events", "runs_high_resume_count"),
        "thresholds": {"workflow_recovery_events": 15, "runs_high_resume_count": 10},
    },
    {
        "id": "cross_language_activities",
        "label": "Cross-language durable activities required",
        "source": "troop-audit/ARCHITECTURE.md",
        "evidence_keys": ("manual_cross_language_requirement",),
        "thresholds": {"manual_cross_language_requirement": 1},
    },
    {
        "id": "celery_broker_incidents",
        "label": "Celery broker/result semantics causing incidents",
        "source": "troop-audit/ARCHITECTURE.md",
        "evidence_keys": ("stale_in_progress_recoveries", "queue_failure_runs"),
        "thresholds": {"stale_in_progress_recoveries": 5, "queue_failure_runs": 8},
    },
    {
        "id": "replay_version_migration",
        "label": "Workflow replay/version migration is difficult",
        "source": "troop-audit/ARCHITECTURE.md",
        "evidence_keys": ("runs_high_resume_count", "runs_high_recovery_count"),
        "thresholds": {"runs_high_resume_count": 8, "runs_high_recovery_count": 8},
    },
]


def _trigger_met(trigger: dict[str, Any], evidence: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    thresholds = dict(trigger.get("thresholds") or {})
    details: dict[str, Any] = {}
    for key, threshold in thresholds.items():
        observed = int(evidence.get(key) or 0)
        details[key] = {"observed": observed, "threshold": int(threshold)}
    met = any(
        int(evidence.get(key) or 0) >= int(threshold)
        for key, threshold in thresholds.items()
    )
    return met, details


def evaluate_durable_engine_triggers(evidence: dict[str, Any]) -> dict[str, Any]:
    """Return per-trigger status and migration recommendation."""
    trigger_rows: list[dict[str, Any]] = []
    met_count = 0
    for trigger in DURABLE_ENGINE_MIGRATION_TRIGGERS:
        met, details = _trigger_met(trigger, evidence)
        if met:
            met_count += 1
        trigger_rows.append(
            {
                "id": trigger["id"],
                "label": trigger["label"],
                "met": met,
                "details": details,
            }
        )

    if met_count >= TRIGGERS_REQUIRED_FOR_REVIEW:
        verdict = "review_recommended"
        recommended_action = (
            "Run a side-by-side failure-recovery benchmark and prototype one workflow "
            "before committing to Temporal/DBOS/Restate. Keep Celery + Postgres as default."
        )
    elif met_count == 1:
        verdict = "monitor"
        recommended_action = "Continue Celery + Postgres; collect another month of evidence."
    else:
        verdict = "defer"
        recommended_action = (
            "Keep Celery + PostgreSQL checkpoints. Re-run this review quarterly or after incidents."
        )

    return {
        "triggers_required_for_review": TRIGGERS_REQUIRED_FOR_REVIEW,
        "triggers_met": met_count,
        "verdict": verdict,
        "migration_default": False,
        "recommended_action": recommended_action,
        "triggers": trigger_rows,
        "alternatives": list(DURABLE_ENGINE_ALTERNATIVES),
        "active_backend": durable_backend_status(),
        "supported_backends": sorted(SUPPORTED_DURABLE_BACKENDS),
        "adapter_entrypoint": "submit_orchestration_run",
    }


def build_durable_engine_review(
    *,
    evidence: dict[str, Any],
    recovery_benchmark: dict[str, Any] | None = None,
    window_days: int,
    owner_id: str,
) -> dict[str, Any]:
    evaluation = evaluate_durable_engine_triggers(evidence)
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "owner_id": owner_id,
        "window_days": window_days,
        "evidence": evidence,
        "evaluation": evaluation,
        "recovery_benchmark": recovery_benchmark,
        "policy": {
            "migration_by_default": False,
            "prototype_only_when_triggers_met": True,
            "preserve_adapter": "submit_orchestration_run",
            "architecture_reference": "troop-audit/ARCHITECTURE.md#5-durable-execution-decision",
        },
    }


def _simulate_hypothetical_engine_replay(*, steps: int = 5) -> float:
    """In-memory stand-in for durable-engine event replay (no external worker)."""
    state: dict[str, Any] = {"events": [], "commands": []}
    started = time.perf_counter()
    for index in range(steps):
        state = deepcopy(state)
        state["events"].append({"type": "ActivityScheduled", "seq": index})
        state["commands"].append({"type": "CompleteActivity", "seq": index})
        _ = len(state["events"]) + len(state["commands"])
    return (time.perf_counter() - started) * 1000


async def benchmark_durable_recovery_side_by_side(
    repo: Any,
    *,
    samples: int = 12,
) -> dict[str, Any]:
    """Compare Postgres checkpoint claim path vs hypothetical replay-only engine model."""
    from sqlalchemy import select

    from backend.modules.orchestration.models import TaskRun
    from backend.tools.performance_harness import benchmark_run_claim_precheck

    current = await benchmark_run_claim_precheck(repo, samples=samples)
    probe = await repo.db.execute(
        select(TaskRun.id, TaskRun.checkpoint_json)
        .order_by(TaskRun.created_at.desc())
        .limit(1)
    )
    row = probe.first()
    checkpoint_reads_ms: list[float] = []
    workflow_state: dict[str, Any] = {}
    if row is not None:
        _run_id, checkpoint = row
        workflow_state = dict((checkpoint or {}).get(WORKFLOW_STATE_KEY) or {})
        for _ in range(max(1, samples)):
            started = time.perf_counter()
            run = await repo.get_run_for_worker(_run_id)
            if run is not None:
                state = dict((run.checkpoint_json or {}).get(WORKFLOW_STATE_KEY) or {})
                _ = state.get("resume_count"), state.get("recovery_count"), state.get("steps")
            checkpoint_reads_ms.append((time.perf_counter() - started) * 1000)

    replay_ms = [_simulate_hypothetical_engine_replay(steps=5) for _ in range(max(1, samples))]
    replay_avg = sum(replay_ms) / len(replay_ms)
    current_p95 = float((current.get("latency") or {}).get("p95_ms") or 0)
    checkpoint_p95 = sorted(checkpoint_reads_ms)[int(len(checkpoint_reads_ms) * 0.95)] if checkpoint_reads_ms else 0.0

    return {
        "interpretation": (
            "Side-by-side model only — no Temporal/DBOS/Restate worker is installed. "
            "Use this to compare recovery complexity before any migration commitment."
        ),
        "current_path": {
            "label": "Celery + Postgres checkpoint claim/read",
            "run_claim_precheck": current,
            "checkpoint_read": {
                "samples": len(checkpoint_reads_ms),
                "p95_ms": round(checkpoint_p95, 3),
                "avg_ms": round(sum(checkpoint_reads_ms) / max(len(checkpoint_reads_ms), 1), 3),
            },
            "resume_count_observed": int(workflow_state.get("resume_count") or 0),
            "recovery_count_observed": int(workflow_state.get("recovery_count") or 0),
        },
        "hypothetical_durable_engine": {
            "label": "Simulated event-replay engine (Temporal-class)",
            "replay_steps_per_sample": 5,
            "avg_ms": round(replay_avg, 3),
            "p95_ms": round(sorted(replay_ms)[int(len(replay_ms) * 0.95)], 3),
        },
        "comparison": {
            "checkpoint_read_p95_ms": round(checkpoint_p95, 3),
            "simulated_replay_p95_ms": round(sorted(replay_ms)[int(len(replay_ms) * 0.95)], 3),
            "claim_precheck_p95_ms": round(current_p95, 3),
        },
    }


def default_evidence_window_days() -> int:
    return 90
