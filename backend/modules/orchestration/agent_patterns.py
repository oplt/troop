"""Curated multi-agent execution patterns (AGENT-001)."""

from __future__ import annotations

from typing import Any

BUILTIN_AGENT_PATTERNS: list[dict[str, Any]] = [
    {
        "id": "specialist_as_tool",
        "name": "Specialist as tool",
        "description": (
            "A parent single agent delegates bounded sub-work to specialists via "
            "the invoke_specialist tool (max depth 1)."
        ),
        "category": "delegation",
        "baseline_run_mode": "single_agent",
        "pattern_run_mode": "single_agent",
        "execution_overlay": {
            "agent_pattern_tools": ["invoke_specialist"],
            "specialist_depth_limit": 1,
            "max_specialist_invocations": 3,
        },
    },
    {
        "id": "structured_handoff",
        "name": "Structured handoff",
        "description": (
            "Manager-worker sequential handoffs: a supervisor plans and routes work "
            "to specialists one branch at a time."
        ),
        "category": "handoff",
        "baseline_run_mode": "single_agent",
        "pattern_run_mode": "manager_worker",
        "execution_overlay": {
            "handoff_mode": "configured_agent",
            "plan_mode": "auto",
            "parallel_branches_allowed": False,
        },
    },
    {
        "id": "bounded_panel_reviewer",
        "name": "Bounded parallel panel + reviewer",
        "description": (
            "Up to three parallel specialist branches with a mandatory reviewer synthesis pass."
        ),
        "category": "panel",
        "baseline_run_mode": "single_agent",
        "pattern_run_mode": "manager_worker",
        "execution_overlay": {
            "max_parallel_branches": 3,
            "require_reviewer": True,
            "panel_mode": True,
            "plan_mode": "auto",
        },
    },
]

_PATTERN_INDEX = {item["id"]: item for item in BUILTIN_AGENT_PATTERNS}

# Quality must improve; cost/latency may not regress beyond these ratios vs baseline.
_COST_REGRESSION_RATIO = 1.10
_LATENCY_REGRESSION_RATIO = 1.25


def get_agent_pattern(pattern_id: str) -> dict[str, Any] | None:
    return _PATTERN_INDEX.get(str(pattern_id or "").strip())


def list_agent_patterns() -> list[dict[str, Any]]:
    return list(BUILTIN_AGENT_PATTERNS)


def compute_pattern_advantage(
    *,
    score_a: float | None,
    score_b: float | None,
    criteria_met_a: bool | None,
    criteria_met_b: bool | None,
    cost_a: float | None,
    cost_b: float | None,
    latency_a: float | None,
    latency_b: float | None,
) -> dict[str, Any]:
    """Decide whether a pattern beats single-agent baseline on quality/latency/cost."""
    sa = float(score_a or 0.0)
    sb = float(score_b or 0.0)
    quality_advantage = sb > sa or (bool(criteria_met_b) and not bool(criteria_met_a))
    cost_regression = False
    if cost_a is not None and cost_b is not None and cost_a > 0:
        cost_regression = float(cost_b) > float(cost_a) * _COST_REGRESSION_RATIO
    latency_regression = False
    if latency_a is not None and latency_b is not None and latency_a > 0:
        latency_regression = float(latency_b) > float(latency_a) * _LATENCY_REGRESSION_RATIO
    released = quality_advantage and not cost_regression and not latency_regression
    return {
        "released": released,
        "quality_advantage": quality_advantage,
        "cost_regression": cost_regression,
        "latency_regression": latency_regression,
        "score_a": sa,
        "score_b": sb,
        "cost_a": cost_a,
        "cost_b": cost_b,
        "latency_a": latency_a,
        "latency_b": latency_b,
    }
