"""Tests for curated multi-agent patterns (AGENT-001)."""

from __future__ import annotations

from backend.modules.orchestration.agent_patterns import (
    BUILTIN_AGENT_PATTERNS,
    compute_pattern_advantage,
    get_agent_pattern,
    list_agent_patterns,
)
from backend.modules.orchestration.router import router


def test_agent_pattern_catalog_has_three_curated_patterns():
    patterns = list_agent_patterns()
    assert len(patterns) == 3
    ids = {item["id"] for item in patterns}
    assert ids == {"specialist_as_tool", "structured_handoff", "bounded_panel_reviewer"}
    for item in patterns:
        assert item["baseline_run_mode"] == "single_agent"
        assert item["pattern_run_mode"] in {"single_agent", "manager_worker"}


def test_get_agent_pattern_returns_none_for_unknown():
    assert get_agent_pattern("swarm_designer") is None
    assert get_agent_pattern("specialist_as_tool") is not None


def test_compute_pattern_advantage_requires_quality_and_no_regression():
    passed = compute_pattern_advantage(
        score_a=70.0,
        score_b=85.0,
        criteria_met_a=False,
        criteria_met_b=True,
        cost_a=1.0,
        cost_b=1.05,
        latency_a=1000.0,
        latency_b=1100.0,
    )
    assert passed["quality_advantage"] is True
    assert passed["released"] is True

    failed_cost = compute_pattern_advantage(
        score_a=70.0,
        score_b=90.0,
        criteria_met_a=False,
        criteria_met_b=True,
        cost_a=1.0,
        cost_b=1.5,
        latency_a=1000.0,
        latency_b=1000.0,
    )
    assert failed_cost["quality_advantage"] is True
    assert failed_cost["cost_regression"] is True
    assert failed_cost["released"] is False

    failed_quality = compute_pattern_advantage(
        score_a=90.0,
        score_b=80.0,
        criteria_met_a=True,
        criteria_met_b=False,
        cost_a=1.0,
        cost_b=0.5,
        latency_a=2000.0,
        latency_b=500.0,
    )
    assert failed_quality["released"] is False


def test_bounded_panel_pattern_caps_parallel_branches():
    pattern = get_agent_pattern("bounded_panel_reviewer")
    assert pattern is not None
    assert pattern["execution_overlay"]["max_parallel_branches"] == 3
    assert pattern["execution_overlay"]["require_reviewer"] is True


def test_agent_pattern_routes_registered():
    from fastapi.routing import APIRoute

    paths = {
        item.path
        for item in router.routes
        if isinstance(item, APIRoute) and "agent-patterns" in item.path
    }
    assert "/agent-patterns" in paths
    assert "/projects/{project_id}/agent-patterns" in paths
    assert "/projects/{project_id}/agent-patterns/{pattern_id}/apply" in paths
    assert "/projects/{project_id}/agent-patterns/{pattern_id}/benchmark" in paths
    assert "/projects/{project_id}/agent-patterns/{pattern_id}/enable" in paths


def test_invoke_specialist_in_native_catalog():
    from backend.modules.workforce.constants import NATIVE_TOOL_CATALOG

    slugs = {item["slug"] for item in NATIVE_TOOL_CATALOG}
    assert "invoke_specialist" in slugs


def test_builtin_patterns_match_roadmap_ids():
    assert {p["id"] for p in BUILTIN_AGENT_PATTERNS} == {
        "specialist_as_tool",
        "structured_handoff",
        "bounded_panel_reviewer",
    }
