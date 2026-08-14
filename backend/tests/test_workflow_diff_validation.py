"""Tests for workflow diff, validation, test mode, and rollback (WF-001B)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.modules.workforce.models import WorkflowDefinition, WorkflowVersion
from backend.modules.workforce.services.workflow_graph_diff import diff_workflow_graphs
from backend.modules.workforce.services.workflow_runtime import WorkflowRuntimeService
from backend.modules.workforce.services.workflow_validation import WorkflowValidationService
from backend.modules.workforce.services.workflow_version_service import (
    DRAFT_VERSION_NUMBER,
    WorkflowVersionService,
)


def test_diff_workflow_graphs_detects_node_and_edge_changes() -> None:
    diff = diff_workflow_graphs(
        left_nodes=[{"id": "a", "type": "trigger"}, {"id": "b", "type": "tool"}],
        left_edges=[{"from": "a", "to": "b"}],
        left_entry_node_id="a",
        right_nodes=[
            {"id": "a", "type": "trigger"},
            {"id": "b", "type": "tool", "config": {"tool": "web_search"}},
            {"id": "c", "type": "condition"},
        ],
        right_edges=[{"from": "a", "to": "b"}, {"from": "b", "to": "c"}],
        right_entry_node_id="a",
    )
    assert diff["nodes_added"] == ["c"]
    assert diff["nodes_removed"] == []
    assert diff["nodes_changed"] == [{"id": "b", "changed_fields": ["config"]}]
    assert len(diff["edges_added"]) == 1
    assert diff["graph_changed"] is True


def test_validate_for_publish_flags_missing_tool_and_gmail_trigger() -> None:
    service = WorkflowValidationService(AsyncMock())
    report = service.validate_for_publish(
        nodes=[
            {"id": "t1", "type": "trigger", "config": {"trigger_type": "gmail_new_message"}},
            {"id": "tool-1", "type": "tool", "config": {}},
            {"id": "orphan", "type": "condition"},
        ],
        edges=[],
        entry_node_id="t1",
    )
    assert report["valid"] is False
    assert any("tool node" in err for err in report["errors"])
    assert any("Gmail trigger" in err for err in report["errors"])
    assert any("unreachable" in warn for warn in report["warnings"])


def test_validate_for_publish_lists_external_write_nodes() -> None:
    service = WorkflowValidationService(AsyncMock())
    report = service.validate_for_publish(
        nodes=[
            {"id": "t1", "type": "trigger"},
            {"id": "send", "type": "tool", "config": {"tool": "gmail.send_draft"}},
        ],
        edges=[{"from": "t1", "to": "send"}],
        entry_node_id="t1",
    )
    assert report["valid"] is True
    assert len(report["external_write_nodes"]) == 1
    assert report["external_write_nodes"][0]["tool_slug"] == "gmail.send_draft"


@pytest.mark.asyncio
async def test_publish_draft_rejects_invalid_graph() -> None:
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.execute = AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: 0))

    definition = WorkflowDefinition(id="wf-1", owner_id="owner-1", slug="demo", name="Demo")
    draft = WorkflowVersion(
        id="draft-1",
        workflow_id="wf-1",
        version_number=DRAFT_VERSION_NUMBER,
        nodes_json=[{"id": "tool-1", "type": "tool", "config": {}}],
        edges_json=[],
        entry_node_id="tool-1",
        is_published=False,
    )
    definition.draft_version_id = draft.id

    service = WorkflowVersionService(db)

    async def _get_version(model, version_id: str):
        if model is WorkflowVersion and version_id == draft.id:
            return draft
        return None

    db.get = AsyncMock(side_effect=_get_version)

    with pytest.raises(ValueError) as exc_info:
        await service.publish_draft(definition, actor_user_id="owner-1")

    detail = exc_info.value.args[0]
    assert isinstance(detail, dict)
    assert detail["errors"]
    assert detail.get("validation", {}).get("valid") is False


@pytest.mark.asyncio
async def test_rollback_to_version_updates_pointer_and_audits() -> None:
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()

    definition = WorkflowDefinition(
        id="wf-1",
        owner_id="owner-1",
        slug="demo",
        name="Demo",
        published_version_id="v-old",
    )
    target = WorkflowVersion(
        id="v-target",
        workflow_id="wf-1",
        version_number=2,
        is_published=True,
    )

    service = WorkflowVersionService(db)
    db.get = AsyncMock(return_value=target)

    with patch(
        "backend.modules.workforce.services.workflow_version_service.AuditRepository"
    ) as audit_cls:
        audit = AsyncMock()
        audit.log = AsyncMock()
        audit_cls.return_value = audit

        rolled = await service.rollback_to_version(
            definition,
            target_version_id="v-target",
            actor_user_id="owner-1",
        )

    assert rolled.id == "v-target"
    assert definition.published_version_id == "v-target"
    audit.log.assert_awaited_once()
    assert audit.log.await_args.args[0] == "workflow.rollback"


@pytest.mark.asyncio
async def test_test_run_simulates_external_mutating_tool() -> None:
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    runtime = WorkflowRuntimeService(db)

    definition = SimpleNamespace(id="wf-1", owner_id="user-1")
    draft = SimpleNamespace(
        id="draft-1",
        workflow_id="wf-1",
        nodes_json=[
            {"id": "tool-1", "type": "tool", "config": {"tool": "gmail.send_draft"}},
        ],
        edges_json=[],
        entry_node_id="tool-1",
    )
    run = SimpleNamespace(
        id="run-1",
        workflow_id="wf-1",
        workflow_version_id="draft-1",
        project_id=None,
        task_id=None,
        status="running",
        current_node_id="tool-1",
        context_json={
            "completed": [],
            "vars": {},
            "test_mode": True,
            "simulate_external_writes": True,
        },
        result_json={},
        created_by="user-1",
    )

    with (
        patch.object(runtime, "get_definition", new_callable=AsyncMock, return_value=definition),
        patch(
            "backend.modules.workforce.services.workflow_version_service.WorkflowVersionService.get_draft",
            new_callable=AsyncMock,
            return_value=draft,
        ),
        patch.object(runtime, "_advance", new_callable=AsyncMock) as advance,
        patch.object(runtime, "_deliver_pending_external_approval", new_callable=AsyncMock),
        patch.object(runtime, "_notify_workflow_run_completed_if_terminal", new_callable=AsyncMock),
    ):
        created_run = await runtime.start_test_run("user-1", "wf-1")

    assert created_run.context_json["test_mode"] is True
    assert created_run.context_json["simulate_external_writes"] is True
    advance.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_tool_node_simulates_external_write_in_test_mode() -> None:
    db = AsyncMock()
    runtime = WorkflowRuntimeService(db)
    run = SimpleNamespace(
        id="run-1",
        workflow_id="wf-1",
        project_id=None,
        task_id=None,
        created_by="user-1",
        context_json={"test_mode": True, "simulate_external_writes": True},
    )
    node = {"id": "tool-1", "type": "tool", "config": {"tool": "gmail.send_draft"}}
    vars_: dict = {}

    status, output, run_status = await runtime._execute_tool_node(
        run=run,
        node=node,
        node_id="tool-1",
        vars_=vars_,
    )

    assert status == "succeeded"
    assert output["simulated"] is True
    assert run_status is None
    assert vars_["tool_result_tool-1"]["status"] == "simulated"
