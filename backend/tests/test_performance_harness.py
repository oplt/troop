"""P5.6 performance harness smoke tests."""

from __future__ import annotations

import pytest

from backend.tools.performance_harness import (
    compare_benchmark_reports,
    metric_path,
)
from backend.tools.phase0_baseline import summarize_timings


def test_compare_benchmark_reports_flags_regression():
    baseline = {
        "in_process": {
            "benchmarks": [
                {
                    "name": "portfolio_control_plane",
                    "latency": {"p95_ms": 100.0},
                }
            ]
        }
    }
    current = {
        "in_process": {
            "benchmarks": [
                {
                    "name": "portfolio_control_plane",
                    "latency": {"p95_ms": 250.0},
                }
            ]
        }
    }
    result = compare_benchmark_reports(current, baseline, threshold=2.0)
    assert result["passed"] is False
    assert result["regression_count"] == 1
    assert result["regressions"][0]["name"] == "portfolio_control_plane"


def test_compare_benchmark_reports_passes_within_threshold():
    baseline = {
        "in_process": {
            "benchmarks": [{"name": "run_claim_precheck", "latency": {"p95_ms": 10.0}}]
        }
    }
    current = {
        "in_process": {
            "benchmarks": [{"name": "run_claim_precheck", "latency": {"p95_ms": 15.0}}]
        }
    }
    result = compare_benchmark_reports(current, baseline, threshold=2.0)
    assert result["passed"] is True


def test_metric_path_reads_p95():
    assert metric_path({"latency": {"p95_ms": 42.0}}) == 42.0
    assert metric_path({"skipped": "x"}) is None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_collect_in_process_benchmarks_runs_when_db_available(tenant_pair):
    from backend.tools.performance_harness import collect_in_process_benchmarks

    user_a, _user_b = tenant_pair
    result = await collect_in_process_benchmarks(owner_id=user_a.id, samples=2)
    if result.get("skipped"):
        pytest.skip(result["skipped"])
    names = {item["name"] for item in result["benchmarks"]}
    assert "portfolio_control_plane" in names
    assert "run_claim_precheck" in names


def test_summarize_timings_used_by_harness():
    stats = summarize_timings([1.0, 2.0, 3.0, 4.0, 5.0])
    assert stats["count"] == 5
    assert stats["p50_ms"] == 3.0
