"""Tests for durable engine migration review gate (ARCH-001)."""

from __future__ import annotations

from backend.modules.orchestration.execution.durable_engine_review import (
    DURABLE_ENGINE_MIGRATION_TRIGGERS,
    TRIGGERS_REQUIRED_FOR_REVIEW,
    build_durable_engine_review,
    evaluate_durable_engine_triggers,
)
from backend.modules.orchestration.execution.durable_execution import (
    SUPPORTED_DURABLE_BACKENDS,
    durable_backend_status,
)
from backend.modules.orchestration.router import router


def test_durable_backend_only_supports_celery_by_default():
    status = durable_backend_status()
    assert status["configured"] == "celery"
    assert status["active"] == "celery"
    assert status["temporal_worker_available"] is False
    assert SUPPORTED_DURABLE_BACKENDS == frozenset({"celery"})


def test_evaluate_triggers_defer_with_empty_evidence():
    evaluation = evaluate_durable_engine_triggers(
        {
            "runs_over_48h": 0,
            "runs_over_7d": 0,
            "workflow_signal_events": 0,
            "workflow_recovery_events": 0,
            "runs_high_resume_count": 0,
            "runs_high_recovery_count": 0,
            "stale_in_progress_recoveries": 0,
            "queue_failure_runs": 0,
            "manual_cross_language_requirement": 0,
        }
    )
    assert evaluation["verdict"] == "defer"
    assert evaluation["migration_default"] is False
    assert evaluation["triggers_met"] == 0


def test_evaluate_triggers_review_recommended_when_two_met():
    evaluation = evaluate_durable_engine_triggers(
        {
            "runs_over_48h": 12,
            "runs_over_7d": 4,
            "workflow_signal_events": 25,
            "workflow_recovery_events": 0,
            "runs_high_resume_count": 0,
            "runs_high_recovery_count": 0,
            "stale_in_progress_recoveries": 0,
            "queue_failure_runs": 0,
            "manual_cross_language_requirement": 0,
        }
    )
    assert evaluation["triggers_met"] >= TRIGGERS_REQUIRED_FOR_REVIEW
    assert evaluation["verdict"] == "review_recommended"


def test_build_review_preserves_adapter_policy():
    review = build_durable_engine_review(
        evidence={"total_runs": 0},
        recovery_benchmark=None,
        window_days=90,
        owner_id="owner-1",
    )
    assert review["policy"]["migration_by_default"] is False
    assert review["policy"]["preserve_adapter"] == "submit_orchestration_run"


def test_migration_triggers_match_architecture_doc_count():
    assert len(DURABLE_ENGINE_MIGRATION_TRIGGERS) == 6


def test_durable_engine_review_routes_registered():
    from fastapi.routing import APIRoute

    paths = {
        item.path
        for item in router.routes
        if isinstance(item, APIRoute) and "durable-engine" in item.path
    }
    assert "/durable-engine/review" in paths
    assert "/durable-engine/recovery-benchmark" in paths


def test_simulated_recovery_benchmark_structure():
    from backend.modules.orchestration.execution.durable_engine_review import (
        _simulate_hypothetical_engine_replay,
    )

    ms = _simulate_hypothetical_engine_replay(steps=3)
    assert ms >= 0.0
