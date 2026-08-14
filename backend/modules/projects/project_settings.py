"""Pure project settings normalization, merge, and portfolio policy helpers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from backend.modules.memory.settings import merge_memory_settings
from backend.modules.orchestration.hierarchy_policy import policy_from_execution
from backend.modules.orchestration.hitl_policy import (
    DEFAULT_APPROVAL_GATES,
    normalize_approval_gates,
    normalize_autonomy_level,
    normalize_hitl_settings,
)

DEFAULT_PORTFOLIO_EXECUTION_POLICY: dict[str, Any] = {
    "routing_mode": "capability_based",
    "approval_policy": "manager_review",
    "repo_indexing_cadence": "daily",
    "cost_cap_usd": 250.0,
}


def normalize_project_settings(
    settings: dict[str, Any] | None,
    *,
    normalize_policy_routing: Callable[[Any], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    raw = dict(settings or {})
    execution = dict(raw.get("execution") or {})
    execution["autonomy_level"] = normalize_autonomy_level(execution.get("autonomy_level"))
    execution.setdefault("manager_agent_id", None)
    execution.setdefault("reviewer_agent_ids", [])
    execution.setdefault("reviewer_chain_mode", "sequential")
    execution.setdefault("provider_config_id", None)
    execution.setdefault("model_name", None)
    execution.setdefault("fallback_model", None)
    execution.setdefault("escalation_rules", [])
    execution.setdefault("routing_mode", "capability_based")
    execution.setdefault("default_run_mode", "single_agent")
    execution.setdefault("approval_policy", "manager_review")
    execution.setdefault("cost_cap_usd", 250.0)
    execution.setdefault("sibling_load_balance", "queue_depth")
    execution.setdefault("skip_unhealthy_worker_providers", True)
    execution.setdefault("offline_local_only_mode", False)
    execution.setdefault("enforce_project_model_policy", False)
    execution.setdefault("allowed_provider_types", [])
    execution.setdefault("allowed_model_slugs", [])
    blocked_handoff = dict(execution.get("blocked_handoff") or {})
    blocked_handoff.setdefault("mode", "escalation_path")
    blocked_handoff.setdefault("target_agent_id", None)
    blocked_handoff.setdefault("fallback_to_manager", True)
    execution["blocked_handoff"] = blocked_handoff
    execution["hierarchy_policy"] = policy_from_execution(execution)
    sla = dict(execution.get("sla") or {})
    sla.setdefault("enabled", True)
    sla.setdefault("warn_hours_before_due", 24)
    sla.setdefault("escalate_hours_after_due", 0)
    execution["sla"] = sla
    execution["approval_gates"] = normalize_approval_gates(
        execution.get("approval_gates", DEFAULT_APPROVAL_GATES)
    )
    execution.setdefault("expensive_model_cost_per_1k_usd", 0.01)
    if callable(normalize_policy_routing):
        execution["policy_routing"] = normalize_policy_routing(execution.get("policy_routing"))
    else:
        policy_routing = execution.get("policy_routing")
        execution["policy_routing"] = (
            dict(policy_routing)
            if isinstance(policy_routing, dict)
            else {"routes": list(policy_routing or [])}
        )
    raw["execution"] = execution
    github = dict(raw.get("github") or {})
    github.setdefault("branch_prefix", "troop/{task_id}-{slug}")
    github.setdefault("enforce_branch_naming", True)
    github.setdefault("auto_post_progress", False)
    github.setdefault("auto_review_on_pr_review", False)
    github.setdefault("auto_activate_review_on_pr_open", True)
    github.setdefault("draft_prs_by_default", True)
    github.setdefault("close_issue_with_manager_summary", True)
    github.setdefault("write_requires_approval", True)
    github.setdefault("sync_labels_to_github", True)
    github.setdefault("sync_assignees_to_github", True)
    github.setdefault("sync_state_to_github", True)
    github.setdefault("sync_milestone_to_github", True)
    github.setdefault("repo_indexing_cadence", "daily")
    github.setdefault("repo_agent_pools", {})
    github.setdefault("outbound_comment_policy", "manual_approval")
    github.setdefault("outbound_comment_trusted_user_ids", [])
    github.setdefault("github_field_locks", {})
    github.setdefault("commit_message_template", "troop: task {task_id} {slug}")
    github.setdefault("respect_branch_protections", True)
    raw["github"] = github
    raw["hitl"] = normalize_hitl_settings(raw.get("hitl"))
    mem_defaults = merge_memory_settings({})
    mem_in = dict(raw.get("memory") or {})
    raw["memory"] = {**mem_defaults, **mem_in}
    return raw


def normalize_portfolio_execution_policy(settings: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(DEFAULT_PORTFOLIO_EXECUTION_POLICY)
    if settings:
        raw.update({key: value for key, value in settings.items() if value is not None})
    raw["routing_mode"] = str(
        raw.get("routing_mode") or DEFAULT_PORTFOLIO_EXECUTION_POLICY["routing_mode"]
    )
    raw["approval_policy"] = str(
        raw.get("approval_policy") or DEFAULT_PORTFOLIO_EXECUTION_POLICY["approval_policy"]
    )
    raw["repo_indexing_cadence"] = str(
        raw.get("repo_indexing_cadence")
        or DEFAULT_PORTFOLIO_EXECUTION_POLICY["repo_indexing_cadence"]
    )
    try:
        raw["cost_cap_usd"] = round(
            float(raw.get("cost_cap_usd") or DEFAULT_PORTFOLIO_EXECUTION_POLICY["cost_cap_usd"]),
            2,
        )
    except (TypeError, ValueError):
        raw["cost_cap_usd"] = float(DEFAULT_PORTFOLIO_EXECUTION_POLICY["cost_cap_usd"])
    return raw


def apply_portfolio_defaults_to_project_settings(
    settings: dict[str, Any] | None,
    defaults: dict[str, Any],
    *,
    explicit_settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    raw = dict(settings or {})
    execution = dict(raw.get("execution") or {})
    github = dict(raw.get("github") or {})
    overrides = dict(raw.get("portfolio_policy_overrides") or {})
    explicit = dict(explicit_settings or {})
    explicit_execution = (
        explicit.get("execution") if isinstance(explicit.get("execution"), dict) else {}
    )
    explicit_github = explicit.get("github") if isinstance(explicit.get("github"), dict) else {}

    for key in ("routing_mode", "approval_policy", "cost_cap_usd"):
        if key in explicit_execution:
            overrides[key] = True
    if "repo_indexing_cadence" in explicit_github:
        overrides["repo_indexing_cadence"] = True

    if not overrides.get("routing_mode"):
        execution["routing_mode"] = defaults["routing_mode"]
    if not overrides.get("approval_policy"):
        execution["approval_policy"] = defaults["approval_policy"]
    if not overrides.get("cost_cap_usd"):
        execution["cost_cap_usd"] = defaults["cost_cap_usd"]
    if not overrides.get("repo_indexing_cadence"):
        github["repo_indexing_cadence"] = defaults["repo_indexing_cadence"]

    raw["execution"] = execution
    raw["github"] = github
    raw["portfolio_policy_overrides"] = overrides
    return raw


def merge_nested_project_settings(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in incoming.items():
        if key == "execution" and isinstance(value, dict):
            out["execution"] = {**(base.get("execution") or {}), **value}
        elif key == "memory" and isinstance(value, dict):
            out["memory"] = {**(base.get("memory") or {}), **value}
        else:
            out[key] = value
    return out


def project_execution_policy_summary(
    settings: dict[str, Any] | None,
    defaults: dict[str, Any],
    *,
    normalize_policy_routing: Callable[[Any], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    normalized = normalize_project_settings(
        settings,
        normalize_policy_routing=normalize_policy_routing,
    )
    execution = dict(normalized.get("execution") or {})
    github = dict(normalized.get("github") or {})
    overrides = dict(normalized.get("portfolio_policy_overrides") or {})

    def item(key: str, label: str, effective: Any, default: Any) -> dict[str, Any]:
        source = (
            "project_override"
            if overrides.get(key) or effective != default
            else "portfolio_default"
        )
        return {
            "key": key,
            "label": label,
            "effective": effective,
            "default": default,
            "source": source,
            "overridden": source == "project_override",
        }

    items = [
        item(
            "routing_mode",
            "Routing mode",
            execution.get("routing_mode"),
            defaults["routing_mode"],
        ),
        item(
            "approval_policy",
            "Approval policy",
            execution.get("approval_policy"),
            defaults["approval_policy"],
        ),
        item(
            "repo_indexing_cadence",
            "Repo indexing cadence",
            github.get("repo_indexing_cadence"),
            defaults["repo_indexing_cadence"],
        ),
        item(
            "cost_cap_usd",
            "Cost cap",
            execution.get("cost_cap_usd"),
            defaults["cost_cap_usd"],
        ),
    ]
    return {
        "items": items,
        "override_count": sum(1 for entry in items if entry["overridden"]),
    }
