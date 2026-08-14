"""Snapshot tests for POL-001B centralized tool governance decisions."""

from __future__ import annotations

import json

import pytest
from backend.modules.workforce.constants import DEFAULT_ACTION_POLICIES, NATIVE_TOOL_CATALOG
from backend.modules.workforce.services.action_policy import DECISION_APPROVAL, DECISION_PROHIBITED
from backend.modules.workforce.services.tool_governance import (
    built_in_tool_decision_snapshots,
    catalog_tool_requires_approval,
    effective_tool_decision_from_catalog,
    is_governed_high_risk_tool,
    is_low_risk_tool,
    tool_requires_hitl_execution_grant,
)

# Frozen expected decisions — update intentionally when catalog/policy changes.
_EXPECTED_SNAPSHOTS: dict[str, dict] = {
    "gmail.search_messages": {
        "decision": "autonomous",
        "requires_approval": False,
        "is_low_risk": True,
        "requires_hitl_grant": False,
        "source": "catalog",
    },
    "gmail.send_draft": {
        "decision": "approval_required",
        "requires_approval": True,
        "is_low_risk": False,
        "requires_hitl_grant": True,
        "source": "catalog",
    },
    "fs_write": {
        "decision": "approval_required",
        "requires_approval": True,
        "is_low_risk": False,
        "requires_hitl_grant": True,
        "source": "catalog",
    },
    "github_comment": {
        "decision": "approval_required",
        "requires_approval": True,
        "is_low_risk": False,
        "requires_hitl_grant": True,
        "source": "catalog",
    },
    "web_fetch": {
        "decision": "autonomous",
        "requires_approval": False,
        "is_low_risk": True,
        "requires_hitl_grant": False,
        "source": "catalog",
    },
    "shell_destructive_action": {
        "decision": "prohibited",
        "requires_approval": True,
        "is_low_risk": False,
        "requires_hitl_grant": True,
        "source": "abstract_policy",
    },
    "__unknown__": {
        "decision": "approval_required",
        "requires_approval": True,
        "is_low_risk": False,
        "requires_hitl_grant": True,
        "source": "unknown_fail_closed",
    },
}


def test_built_in_snapshot_registry_covers_catalog_and_policies():
    snapshots = built_in_tool_decision_snapshots()
    for item in NATIVE_TOOL_CATALOG:
        assert item["slug"] in snapshots
    for row in DEFAULT_ACTION_POLICIES:
        assert row["action_key"] in snapshots
    assert "__unknown__" in snapshots


@pytest.mark.parametrize("slug,expected", list(_EXPECTED_SNAPSHOTS.items()))
def test_effective_decision_snapshot(slug: str, expected: dict):
    key = "not.a.registered.tool" if slug == "__unknown__" else slug
    snapshot = effective_tool_decision_from_catalog(key).to_snapshot()
    for field, value in expected.items():
        assert snapshot[field] == value, f"{slug}.{field}: {snapshot[field]!r} != {value!r}"


@pytest.mark.parametrize("slug", [item["slug"] for item in NATIVE_TOOL_CATALOG])
def test_catalog_requires_approval_matches_tool_definition(slug: str):
    catalog = next(item for item in NATIVE_TOOL_CATALOG if item["slug"] == slug)
    assert catalog_tool_requires_approval(slug) == bool(catalog.get("requires_approval"))


def test_unknown_tool_fails_closed():
    assert catalog_tool_requires_approval("totally.unknown.tool") is True
    assert is_low_risk_tool("totally.unknown.tool") is False
    assert tool_requires_hitl_execution_grant("totally.unknown.tool") is True
    decision = effective_tool_decision_from_catalog("totally.unknown.tool")
    assert decision.decision == DECISION_APPROVAL
    assert decision.source == "unknown_fail_closed"


def test_ecosystem_tools_fail_closed():
    for slug in ("mcp.server/tool", "a2a.send_task"):
        assert catalog_tool_requires_approval(slug) is True
        assert is_low_risk_tool(slug) is False


def test_low_risk_tools_are_read_only_catalog_entries():
    low_risk = [item["slug"] for item in NATIVE_TOOL_CATALOG if is_low_risk_tool(item["slug"])]
    assert "web_search" in low_risk
    assert "fs_read" in low_risk
    assert "fs_write" not in low_risk
    assert "github_comment" not in low_risk


def test_governed_high_risk_includes_approval_and_high_risk_tools():
    assert is_governed_high_risk_tool("fs_write") is True
    assert is_governed_high_risk_tool("web_search") is False
    assert is_governed_high_risk_tool("shell_destructive_action") is True


def test_full_snapshot_file_is_stable():
    """Guard against accidental drift — entire snapshot blob is checked in."""
    snapshots = built_in_tool_decision_snapshots()
    payload = json.dumps(snapshots, sort_keys=True, indent=2)
    assert "gmail.send_draft" in payload
    assert snapshots["shell_destructive_action"]["decision"] == DECISION_PROHIBITED
