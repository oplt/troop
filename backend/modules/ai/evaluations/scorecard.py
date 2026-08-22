"""Evaluation regression scorecard (EVAL-001B)."""

from __future__ import annotations

from typing import Any


def build_scorecard(
    *,
    candidate_config: dict[str, Any],
    metrics: dict[str, Any],
    baseline_metrics: dict[str, Any] | None,
    regression_threshold: float,
    judge_version_id: str | None,
    judge_mode: str,
) -> dict[str, Any]:
    candidate_pass_rate = float(metrics.get("task_success_rate") or 0.0)
    baseline_pass_rate = (
        float(baseline_metrics.get("task_success_rate")) if baseline_metrics is not None else None
    )
    delta_pass_rate = (
        round(candidate_pass_rate - baseline_pass_rate, 4)
        if baseline_pass_rate is not None
        else None
    )
    regression_detected = (
        baseline_pass_rate is not None
        and delta_pass_rate is not None
        and delta_pass_rate < -abs(regression_threshold)
    )

    qualitative = metrics.get("avg_qualitative_score")
    if regression_detected:
        publish_recommendation = "block"
    elif qualitative is not None and qualitative < 0.6:
        publish_recommendation = "review"
    elif candidate_pass_rate >= 1.0:
        publish_recommendation = "approve"
    elif candidate_pass_rate >= max(0.8, (baseline_pass_rate or 0.0) - regression_threshold):
        publish_recommendation = "review"
    else:
        publish_recommendation = "block"

    return {
        "candidate": candidate_config,
        "metrics": metrics,
        "baseline_metrics": baseline_metrics,
        "regression": {
            "detected": regression_detected,
            "threshold": regression_threshold,
            "baseline_pass_rate": baseline_pass_rate,
            "candidate_pass_rate": candidate_pass_rate,
            "delta_pass_rate": delta_pass_rate,
            "publish_recommendation": publish_recommendation,
        },
        "judge": {
            "version_id": judge_version_id,
            "mode": judge_mode,
        },
    }
