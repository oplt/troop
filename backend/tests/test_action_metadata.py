"""Tests for POL-001A consolidated action governance metadata."""

from __future__ import annotations

import pytest
from backend.modules.orchestration.external_effect_inventory import (
    IdempotencyStrategy,
    SideEffect,
    get_external_effect_contract,
)
from backend.modules.workforce.action_metadata import (
    CommitCheckStrategy,
    Reversibility,
    assert_native_catalog_has_governance,
    default_action_policies_with_governance,
    governance_for_action_key,
    native_tool_governance_rows,
)
from backend.modules.workforce.constants import DEFAULT_ACTION_POLICIES, NATIVE_TOOL_CATALOG
from backend.modules.workforce.services.action_policy import (
    DECISION_APPROVAL,
    resolve_decision_from_policies,
)


def test_native_catalog_has_governance_for_every_slug():
    assert_native_catalog_has_governance()
    slugs = {item["slug"] for item in NATIVE_TOOL_CATALOG}
    covered = {slug for slug, _ in native_tool_governance_rows()}
    assert slugs == covered


@pytest.mark.parametrize("slug", [item["slug"] for item in NATIVE_TOOL_CATALOG])
def test_governance_aligns_with_external_effect_inventory(slug: str):
    contract = get_external_effect_contract(slug)
    assert contract is not None
    governance = governance_for_action_key(slug)
    assert governance.side_effect == SideEffect(contract.side_effect)
    assert governance.idempotency_strategy == IdempotencyStrategy(contract.idempotency_strategy)


def test_gmail_send_draft_commit_check_strategy():
    governance = governance_for_action_key("gmail.send_draft")
    assert governance.idempotency_strategy == IdempotencyStrategy.DURABLE_CLAIM
    assert governance.commit_check_strategy == CommitCheckStrategy.APPROVAL_AND_FINGERPRINT
    assert governance.reversibility == Reversibility.NONE


def test_read_tools_are_parallel_safe():
    for slug in ("web_fetch", "fs_read", "gmail.search_messages"):
        governance = governance_for_action_key(slug)
        assert governance.side_effect == SideEffect.READ
        assert governance.parallel_safe is True
        assert governance.reversibility == Reversibility.FULL


def test_default_action_policies_include_governance():
    enriched = default_action_policies_with_governance()
    assert len(enriched) == len(DEFAULT_ACTION_POLICIES)
    for row in enriched:
        governance = row.get("governance") or {}
        assert governance.get("side_effect")
        assert governance.get("idempotency_strategy")
        assert governance.get("commit_check_strategy")


def test_resolve_includes_governance_from_tool_defaults():
    from types import SimpleNamespace

    result = resolve_decision_from_policies([], default=DECISION_APPROVAL)
    assert result["decision"] == DECISION_APPROVAL

    tool = SimpleNamespace(
        id="t1",
        slug="fs_write",
        risk_level="high",
        requires_approval=True,
        side_effect="internal_mutating",
        reversibility="partial",
        data_sensitivity="internal",
        parallel_safe=False,
        idempotency_strategy="none",
        commit_check_strategy="none",
    )
    governance = governance_for_action_key(tool.slug)
    payload = {
        **governance.to_dict(),
        "risk_level": tool.risk_level,
        "requires_approval": tool.requires_approval,
    }
    assert payload["side_effect"] == "internal_mutating"
    assert payload["requires_approval"] is True
