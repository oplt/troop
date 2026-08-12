"""Unit tests for action policy deny-overrides resolution."""

from types import SimpleNamespace

from backend.modules.workforce.services.action_policy import (
    DECISION_APPROVAL,
    DECISION_AUTONOMOUS,
    DECISION_PROHIBITED,
    resolve_decision_from_policies,
)


def _policy(scope_type: str, decision: str, id_: str = "p") -> SimpleNamespace:
    return SimpleNamespace(id=id_, scope_type=scope_type, decision=decision, scope_id="x")


def test_most_specific_wins_when_no_deny():
    policies = [
        _policy("organization", DECISION_APPROVAL, "org"),
        _policy("task", DECISION_AUTONOMOUS, "task"),
    ]
    result = resolve_decision_from_policies(policies)
    assert result["decision"] == DECISION_AUTONOMOUS
    assert result["matched_scope"] == "task"
    assert result["deny_override"] is False


def test_organization_prohibit_blocks_task_autonomous():
    policies = [
        _policy("organization", DECISION_PROHIBITED, "org"),
        _policy("task", DECISION_AUTONOMOUS, "task"),
    ]
    result = resolve_decision_from_policies(policies)
    assert result["decision"] == DECISION_PROHIBITED
    assert result["deny_override"] is True


def test_default_when_empty():
    result = resolve_decision_from_policies([], default=DECISION_APPROVAL)
    assert result["decision"] == DECISION_APPROVAL
    assert result["reason"] == "no_policy_matched"
