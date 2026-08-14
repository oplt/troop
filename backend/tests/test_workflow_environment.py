"""Tests for workflow environment deployments (ENV-001)."""

from __future__ import annotations

import pytest

from backend.modules.workforce.services.workflow_environment_service import (
    apply_bindings_to_graph,
    diff_bindings,
    extract_bindings_from_graph,
    installation_allowed_for_environment,
    normalize_environment,
)


def test_installation_allowed_for_environment_prod_rejects_dev() -> None:
    assert installation_allowed_for_environment("dev", "prod") is False
    assert installation_allowed_for_environment(None, "prod") is False
    assert installation_allowed_for_environment("prod", "prod") is True
    assert installation_allowed_for_environment("dev", "dev") is True
    assert installation_allowed_for_environment("staging", "staging") is True
    assert installation_allowed_for_environment("dev", "staging") is False


def test_extract_and_apply_bindings_roundtrip() -> None:
    nodes = [
        {
            "id": "trigger",
            "type": "trigger",
            "config": {"connector_installation_id": "inst-dev", "trigger_type": "manual"},
        },
        {
            "id": "send",
            "type": "tool",
            "config": {"tool_slug": "gmail.send_draft"},
        },
    ]
    bindings = extract_bindings_from_graph(nodes)
    assert bindings["trigger"]["connector_installation_id"] == "inst-dev"

    resolved = apply_bindings_to_graph(
        [{"id": "send", "type": "tool", "config": {}}],
        {"send": {"connector_installation_id": "inst-prod"}},
    )
    assert resolved[0]["config"]["connector_installation_id"] == "inst-prod"


def test_diff_bindings_reports_changes() -> None:
    diff = diff_bindings(
        {"n1": {"connector_installation_id": "a"}},
        {"n1": {"connector_installation_id": "b"}, "n2": {"connector_installation_id": "c"}},
    )
    assert diff["bindings_changed_count"] == 2
    assert "n2" in diff["bindings_added"]


def test_normalize_environment_rejects_unknown() -> None:
    assert normalize_environment("prod") == "prod"
    with pytest.raises(ValueError):
        normalize_environment("qa")
