"""Tests for flagship email approval template pack (PROD-001A)."""

from __future__ import annotations

from backend.modules.workforce.catalog import MARKETPLACE_WORKFLOWS
from backend.modules.workforce.email_approval_template import (
    EMAIL_APPROVAL_FLAGSHIP_SLUG,
    EMAIL_APPROVAL_TEMPLATE_PACK,
    flagship_email_approval_workflow,
)


def test_flagship_workflow_in_marketplace_catalog() -> None:
    workflow = next(item for item in MARKETPLACE_WORKFLOWS if item["slug"] == EMAIL_APPROVAL_FLAGSHIP_SLUG)
    assert workflow["flagship"] is True
    assert workflow["template_pack"]["flagship"] is True
    assert len(workflow["nodes"]) >= 7


def test_flagship_template_pack_governance_steps() -> None:
    actors = {step["actor"] for step in EMAIL_APPROVAL_TEMPLATE_PACK["steps"]}
    assert actors == {"system", "deterministic", "ai", "human"}
    step_ids = [step["id"] for step in EMAIL_APPROVAL_TEMPLATE_PACK["steps"]]
    assert step_ids[:3] == ["trigger", "normalize", "context"]
    assert "approve" in step_ids
    assert "stale_check" in step_ids
    assert "audit" in step_ids


def test_flagship_workflow_includes_context_and_reply_gate() -> None:
    workflow = flagship_email_approval_workflow()
    node_ids = {node["id"] for node in workflow["nodes"]}
    assert "fetch_context" in node_ids
    assert "should_reply" in node_ids
    assert "send_draft" in node_ids
    send_node = next(node for node in workflow["nodes"] if node["id"] == "send_draft")
    assert send_node["config"]["approval_delivery_channel"] == "in_app"
