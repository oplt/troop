"""Phase 0 — characterization tests for project settings normalization."""

from __future__ import annotations

from types import SimpleNamespace

from backend.modules.projects.service import (
    DEFAULT_PORTFOLIO_EXECUTION_POLICY,
    OrchestrationProjectsServiceMixin,
)


def _projects_host() -> OrchestrationProjectsServiceMixin:
    return OrchestrationProjectsServiceMixin()


def test_normalize_project_settings_applies_execution_defaults():
    host = _projects_host()
    normalized = host._normalize_project_settings({})

    execution = normalized["execution"]
    assert execution["routing_mode"] == "capability_based"
    assert execution["default_run_mode"] == "single_agent"
    assert execution["cost_cap_usd"] == 250.0
    assert execution["blocked_handoff"]["fallback_to_manager"] is True
    assert execution["sla"]["enabled"] is True
    assert isinstance(execution["approval_gates"], list)
    assert normalized["github"]["branch_prefix"] == "troop/{task_id}-{slug}"
    assert "hitl" in normalized
    assert "memory" in normalized


def test_normalize_project_settings_preserves_explicit_execution_overrides():
    host = _projects_host()
    normalized = host._normalize_project_settings(
        {
            "execution": {
                "routing_mode": "round_robin",
                "cost_cap_usd": 99.5,
                "blocked_handoff": {"mode": "fixed_agent", "target_agent_id": "agent-1"},
            }
        }
    )

    execution = normalized["execution"]
    assert execution["routing_mode"] == "round_robin"
    assert execution["cost_cap_usd"] == 99.5
    assert execution["blocked_handoff"]["target_agent_id"] == "agent-1"


def test_normalize_portfolio_execution_policy_rounds_cost_cap():
    host = _projects_host()
    policy = host._normalize_portfolio_execution_policy(
        {"cost_cap_usd": "123.456", "routing_mode": "manual"}
    )

    assert policy["routing_mode"] == "manual"
    assert policy["cost_cap_usd"] == 123.46
    assert policy["approval_policy"] == DEFAULT_PORTFOLIO_EXECUTION_POLICY["approval_policy"]


def test_normalize_portfolio_execution_policy_falls_back_on_invalid_cost():
    host = _projects_host()
    policy = host._normalize_portfolio_execution_policy({"cost_cap_usd": "not-a-number"})

    assert policy["cost_cap_usd"] == DEFAULT_PORTFOLIO_EXECUTION_POLICY["cost_cap_usd"]


def test_apply_portfolio_defaults_respects_explicit_overrides():
    host = _projects_host()
    defaults = host._normalize_portfolio_execution_policy(None)
    merged = host._apply_portfolio_defaults_to_project_settings(
        {"execution": {"routing_mode": "manual"}, "github": {}},
        defaults,
        explicit_settings={"execution": {"routing_mode": "manual"}},
    )

    assert merged["execution"]["routing_mode"] == "manual"
    assert merged["portfolio_policy_overrides"]["routing_mode"] is True
    assert merged["execution"]["approval_policy"] == defaults["approval_policy"]


def test_merge_nested_project_settings_deep_merges_execution_and_memory():
    host = _projects_host()
    base = {
        "execution": {"routing_mode": "capability_based", "cost_cap_usd": 250.0},
        "memory": {"search_limit": 5, "ttl_days": 30},
        "github": {"auto_post_progress": False},
    }
    incoming = {
        "execution": {"cost_cap_usd": 100.0},
        "memory": {"ttl_days": 7},
        "hitl": {"require_human_for_destructive": True},
    }

    merged = host._merge_nested_project_settings(base, incoming)

    assert merged["execution"]["routing_mode"] == "capability_based"
    assert merged["execution"]["cost_cap_usd"] == 100.0
    assert merged["memory"]["search_limit"] == 5
    assert merged["memory"]["ttl_days"] == 7
    assert merged["hitl"]["require_human_for_destructive"] is True


def test_project_execution_policy_summary_marks_overridden_fields():
    host = _projects_host()
    defaults = host._normalize_portfolio_execution_policy(None)
    project = SimpleNamespace(
        settings_json={
            "execution": {"routing_mode": "manual", "cost_cap_usd": 250.0},
            "github": {"repo_indexing_cadence": "daily"},
            "portfolio_policy_overrides": {"routing_mode": True},
        }
    )

    summary = host._project_execution_policy_summary(project, defaults)

    assert summary["override_count"] >= 1
    routing = next(item for item in summary["items"] if item["key"] == "routing_mode")
    assert routing["overridden"] is True
    assert routing["source"] == "project_override"
