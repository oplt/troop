from __future__ import annotations

from collections import defaultdict
from typing import Any


HIERARCHY_EDGE_TYPES = {
    "delegates_to",
    "reviews",
    "escalates_to",
    "collaborates_with",
}
HIERARCHY_ROLES = {"manager", "team_lead", "specialist", "reviewer"}
ROUTING_MODES = {
    "capability_based",
    "priority_sla",
    "sla_priority",
    "cost_aware",
    "model_availability",
    "user_pinned",
    "throughput",
}
LOAD_BALANCE_MODES = {"queue_depth", "round_robin"}
EXECUTION_MODES = {"single_agent", "manager_worker", "debate"}
HANDOFF_MODES = {"escalation_path", "configured_agent", "sibling_with_capacity"}


def _clean_ids(value: Any) -> list[str]:
    if isinstance(value, str):
        value = value.split(",")
    if not isinstance(value, (list, tuple, set)):
        return []
    result: list[str] = []
    for item in value:
        item_id = str(item).strip()
        if item_id and item_id not in result:
            result.append(item_id)
    return result


def normalize_hierarchy_policy(value: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = dict(value or {})
    edges: list[dict[str, str]] = []
    for item in raw.get("edges") or raw.get("hierarchy_edges") or []:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source_agent_id") or item.get("source") or "").strip()
        target = str(item.get("target_agent_id") or item.get("target") or "").strip()
        edge_data = item.get("data") if isinstance(item.get("data"), dict) else {}
        relationship = str(
            item.get("relationship") or item.get("semantic") or edge_data.get("semantic") or "delegates_to"
        ).strip()
        if source and target and relationship in HIERARCHY_EDGE_TYPES and source != target:
            edge = {
                "source_agent_id": source,
                "target_agent_id": target,
                "relationship": relationship,
            }
            if edge not in edges:
                edges.append(edge)

    delegation_rules: dict[str, list[str]] = {}
    for source, targets in (raw.get("delegation_rules") or {}).items():
        source_id = str(source).strip()
        if source_id:
            delegation_rules[source_id] = _clean_ids(targets)

    brainstorm_rules: dict[str, list[str]] = {}
    for source, targets in (raw.get("brainstorm_rules") or {}).items():
        source_id = str(source).strip()
        if source_id:
            brainstorm_rules[source_id] = _clean_ids(targets)

    reviewer_ids = _clean_ids(raw.get("reviewer_agent_ids"))
    blocked_handoff = dict(raw.get("blocked_handoff") or {})
    blocked_handoff_mode = str(blocked_handoff.get("mode") or "escalation_path").strip()
    if blocked_handoff_mode not in HANDOFF_MODES:
        blocked_handoff_mode = "escalation_path"

    default_execution_mode = str(raw.get("default_execution_mode") or "single_agent").strip()
    if default_execution_mode not in EXECUTION_MODES:
        default_execution_mode = "single_agent"
    routing_mode = str(raw.get("routing_mode") or "capability_based").strip()
    if routing_mode not in ROUTING_MODES:
        routing_mode = "capability_based"
    load_balance = str(raw.get("sibling_load_balance") or "queue_depth").strip()
    if load_balance not in LOAD_BALANCE_MODES:
        load_balance = "queue_depth"

    return {
        "manager_agent_id": str(raw.get("manager_agent_id") or "").strip() or None,
        "edges": edges,
        "delegation_rules": delegation_rules,
        "brainstorm_rules": brainstorm_rules,
        "reviewer_agent_ids": reviewer_ids,
        "reviewer_chain_mode": str(raw.get("reviewer_chain_mode") or "sequential").strip(),
        "routing_mode": routing_mode,
        "sibling_load_balance": load_balance,
        "default_execution_mode": default_execution_mode,
        "blocked_handoff": {
            "mode": blocked_handoff_mode,
            "target_agent_id": str(blocked_handoff.get("target_agent_id") or "").strip() or None,
            "fallback_to_manager": blocked_handoff.get("fallback_to_manager", True) is not False,
        },
        "final_authority": "human_user",
    }


def policy_from_execution(execution: dict[str, Any] | None) -> dict[str, Any]:
    execution = dict(execution or {})
    raw = dict(execution.get("hierarchy_policy") or {})
    for key in (
        "manager_agent_id",
        "reviewer_agent_ids",
        "reviewer_chain_mode",
        "routing_mode",
        "sibling_load_balance",
        "blocked_handoff",
    ):
        if key not in raw and key in execution:
            raw[key] = execution[key]
    if "default_execution_mode" not in raw:
        raw["default_execution_mode"] = execution.get("default_run_mode") or "single_agent"

    layout = execution.get("team_graph_layout")
    if not raw.get("edges") and isinstance(layout, dict):
        raw["edges"] = layout.get("edges") or []
    policy = normalize_hierarchy_policy(raw)
    return policy


def apply_policy_to_execution(execution: dict[str, Any], value: dict[str, Any] | None) -> dict[str, Any]:
    policy = normalize_hierarchy_policy(value)
    execution = dict(execution)
    execution["hierarchy_policy"] = policy
    execution["manager_agent_id"] = policy["manager_agent_id"]
    execution["reviewer_agent_ids"] = policy["reviewer_agent_ids"]
    execution["reviewer_chain_mode"] = policy["reviewer_chain_mode"]
    execution["routing_mode"] = policy["routing_mode"]
    execution["sibling_load_balance"] = policy["sibling_load_balance"]
    execution["blocked_handoff"] = policy["blocked_handoff"]
    execution["default_run_mode"] = policy["default_execution_mode"]
    return execution


def validate_hierarchy_policy(
    policy: dict[str, Any],
    member_ids: set[str],
    member_roles: dict[str, str] | None = None,
) -> list[str]:
    normalized = normalize_hierarchy_policy(policy)
    roles = member_roles or {}
    errors: list[str] = []

    manager_id = normalized.get("manager_agent_id")
    if manager_id and manager_id not in member_ids:
        errors.append("manager_agent_id must be a member of the project")
    if manager_id and roles.get(manager_id) not in {"manager", "team_lead"}:
        errors.append("manager_agent_id must reference a manager or team lead")

    reviewer_ids = normalized["reviewer_agent_ids"]
    if member_ids and roles and not any(
        roles.get(member_id) == "reviewer" for member_id in member_ids
    ):
        errors.append("Project must include at least one reviewer role")
    if member_ids and not reviewer_ids:
        errors.append("At least one reviewer agent must be configured in the reviewer chain")
    missing_reviewers = [item for item in reviewer_ids if item not in member_ids]
    if missing_reviewers:
        errors.append(f"reviewer_agent_ids contain non-members: {', '.join(missing_reviewers)}")
    invalid_reviewers = [item for item in reviewer_ids if roles.get(item) not in {"reviewer", "manager", "team_lead"}]
    if invalid_reviewers:
        errors.append(f"reviewer chain contains non-reviewer agents: {', '.join(invalid_reviewers)}")

    adjacency: dict[str, list[str]] = defaultdict(list)
    for edge in normalized["edges"]:
        source = edge["source_agent_id"]
        target = edge["target_agent_id"]
        if source not in member_ids or target not in member_ids:
            errors.append(f"hierarchy edge references a non-member: {source} -> {target}")
            continue
        if edge["relationship"] == "delegates_to":
            adjacency[source].append(target)

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            errors.append("delegation relationships cannot contain cycles")
            return
        if node in visited:
            return
        visiting.add(node)
        for child in adjacency.get(node, []):
            visit(child)
        visiting.remove(node)
        visited.add(node)

    for member_id in member_ids:
        visit(member_id)

    for source, targets in normalized["delegation_rules"].items():
        if source not in member_ids:
            errors.append(f"delegation rule source is not a project member: {source}")
        missing = [target for target in targets if target not in member_ids]
        if missing:
            errors.append(f"delegation rule for {source} contains non-members: {', '.join(missing)}")
    for source, targets in normalized["brainstorm_rules"].items():
        if source not in member_ids:
            errors.append(f"brainstorm rule source is not a project member: {source}")
        missing = [target for target in targets if target not in member_ids]
        if missing:
            errors.append(f"brainstorm rule for {source} contains non-members: {', '.join(missing)}")

    blocked_target = normalized["blocked_handoff"].get("target_agent_id")
    if blocked_target and blocked_target not in member_ids:
        errors.append("blocked handoff target must be a member of the project")
    return list(dict.fromkeys(errors))
