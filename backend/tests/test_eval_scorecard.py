"""Tests for evaluation runner scorecard (EVAL-001B)."""

from __future__ import annotations

from types import SimpleNamespace

from backend.modules.ai.evaluations.judge import JUDGE_VERSION_ID, run_qualitative_judge
from backend.modules.ai.evaluations.metrics import aggregate_metrics, build_case_metrics
from backend.modules.ai.evaluations.scorecard import build_scorecard


def test_build_case_metrics_tracks_latency_tokens_and_schema() -> None:
    case = SimpleNamespace(
        provenance_json={"workflow_version_id": "wf-v1"},
        correction_json=None,
        input_snapshot_json={},
    )
    ai_run = SimpleNamespace(
        output_text='{"status":"ok"}',
        output_json={"status": "ok"},
        latency_ms=120,
        input_tokens=10,
        output_tokens=20,
        total_tokens=30,
        estimated_cost_micros=500,
    )
    metrics = build_case_metrics(
        case=case,
        ai_run=ai_run,
        passed=True,
        response_format="json",
        qualitative_score=0.8,
    )
    assert metrics["task_success"] is True
    assert metrics["schema_validity"] is True
    assert metrics["latency_ms"] == 120
    assert metrics["total_tokens"] == 30


def test_aggregate_metrics_summarizes_dataset() -> None:
    summary = aggregate_metrics(
        [
            {"task_success": True, "schema_validity": True, "tool_plan_valid": True, "latency_ms": 100, "total_tokens": 10, "estimated_cost_micros": 1, "human_correction_case": False},
            {"task_success": False, "schema_validity": True, "tool_plan_valid": False, "latency_ms": 200, "total_tokens": 20, "estimated_cost_micros": 2, "human_correction_case": True},
        ]
    )
    assert summary["task_success_rate"] == 0.5
    assert summary["schema_validity_rate"] == 1.0
    assert summary["tool_plan_valid_rate"] == 0.5
    assert summary["human_correction_cases"] == 1
    assert summary["avg_latency_ms"] == 150.0


def test_build_scorecard_blocks_regression() -> None:
    scorecard = build_scorecard(
        candidate_config={"prompt_version_id": "pv-2", "model_name": "gpt-test"},
        metrics={"task_success_rate": 0.7, "schema_validity_rate": 1.0},
        baseline_metrics={"task_success_rate": 0.9},
        regression_threshold=0.05,
        judge_version_id=None,
        judge_mode="deterministic",
    )
    assert scorecard["regression"]["detected"] is True
    assert scorecard["regression"]["publish_recommendation"] == "block"


def test_build_scorecard_approves_improved_candidate() -> None:
    scorecard = build_scorecard(
        candidate_config={"prompt_version_id": "pv-3"},
        metrics={"task_success_rate": 1.0, "schema_validity_rate": 1.0},
        baseline_metrics={"task_success_rate": 0.8},
        regression_threshold=0.05,
        judge_version_id=None,
        judge_mode="deterministic",
    )
    assert scorecard["regression"]["detected"] is False
    assert scorecard["regression"]["publish_recommendation"] == "approve"


def test_qualitative_judge_stores_judge_version() -> None:
    score, notes, version_id = run_qualitative_judge(
        output_text="The answer is concise and actionable.",
        output_json=None,
        rubric={"criteria": [{"keyword": "actionable"}, {"keyword": "missing-term"}]},
    )
    assert score == 0.5
    assert version_id == JUDGE_VERSION_ID
    assert "1/2" in (notes or "")


def test_qualitative_judge_skips_without_rubric() -> None:
    score, notes, version_id = run_qualitative_judge(
        output_text="hello",
        output_json=None,
        rubric=None,
    )
    assert score is None
    assert notes is None
    assert version_id is None
