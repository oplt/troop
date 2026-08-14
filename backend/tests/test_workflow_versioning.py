"""Tests for immutable workflow versions and draft/publish pointers (WF-001A)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.modules.workforce.models import WorkflowDefinition, WorkflowVersion
from backend.modules.workforce.services.workflow_graph import (
    canonicalize_workflow_graph,
    workflow_graph_hash,
)
from backend.modules.workforce.services.workflow_version_service import (
    DRAFT_VERSION_NUMBER,
    WorkflowVersionImmutableError,
    WorkflowVersionService,
)


def test_canonicalize_workflow_graph_sorts_nodes_and_edges() -> None:
    graph = canonicalize_workflow_graph(
        nodes=[
            {"id": "b", "type": "tool", "config": {"z": 1, "a": 2}},
            {"id": "a", "type": "trigger"},
        ],
        edges=[
            {"from": "b", "to": "a"},
            {"from": "a", "to": "b"},
        ],
        entry_node_id="a",
    )
    assert [node["id"] for node in graph["nodes"]] == ["a", "b"]
    assert graph["edges"][0]["from"] == "a"
    assert graph["entry_node_id"] == "a"
    assert len(workflow_graph_hash(graph)) == 64


def test_assert_mutable_rejects_published_version() -> None:
    version = WorkflowVersion(id="v1", workflow_id="wf1", version_number=1, is_published=True)
    with pytest.raises(WorkflowVersionImmutableError):
        WorkflowVersionService.assert_mutable(version)


@pytest.mark.asyncio
async def test_publish_draft_creates_immutable_copy_and_keeps_mutable_draft() -> None:
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.execute = AsyncMock(
        return_value=SimpleNamespace(scalar_one_or_none=lambda: 0)
    )

    definition = WorkflowDefinition(
        id="wf-1",
        owner_id="owner-1",
        slug="demo",
        name="Demo",
    )
    draft = WorkflowVersion(
        id="draft-1",
        workflow_id="wf-1",
        version_number=DRAFT_VERSION_NUMBER,
        nodes_json=[{"id": "n1", "type": "trigger"}],
        edges_json=[],
        entry_node_id="n1",
        is_published=False,
    )
    definition.draft_version_id = draft.id

    service = WorkflowVersionService(db)

    async def _get_version(model, version_id: str):
        if model is WorkflowVersion and version_id == draft.id:
            return draft
        return None

    db.get = AsyncMock(side_effect=_get_version)

    published = await service.publish_draft(definition, actor_user_id="owner-1")

    assert published.is_published is True
    assert published.version_number == 1
    assert published.id != draft.id
    assert definition.published_version_id == published.id
    assert definition.draft_version_id == draft.id
    assert draft.is_published is False
    assert db.add.called


@pytest.mark.asyncio
async def test_update_draft_rejects_published_row() -> None:
    db = AsyncMock()
    definition = WorkflowDefinition(id="wf-1", owner_id="owner-1", slug="demo", name="Demo")
    published = WorkflowVersion(
        id="pub-1",
        workflow_id="wf-1",
        version_number=1,
        is_published=True,
        nodes_json=[{"id": "n1", "type": "trigger"}],
        edges_json=[],
        entry_node_id="n1",
    )
    definition.draft_version_id = published.id

    service = WorkflowVersionService(db)
    db.get = AsyncMock(return_value=published)

    with pytest.raises(WorkflowVersionImmutableError):
        await service.update_draft(
            definition,
            nodes=[{"id": "n1", "type": "trigger"}],
            edges=[],
            entry_node_id="n1",
            actor_user_id="owner-1",
        )


@pytest.mark.asyncio
async def test_resolve_run_version_uses_published_pointer() -> None:
    db = AsyncMock()
    definition = WorkflowDefinition(
        id="wf-1",
        owner_id="owner-1",
        slug="demo",
        name="Demo",
        published_version_id="pub-1",
        draft_version_id="draft-1",
    )
    published = WorkflowVersion(
        id="pub-1",
        workflow_id="wf-1",
        version_number=1,
        is_published=True,
        nodes_json=[{"id": "n1", "type": "trigger"}],
        edges_json=[],
        entry_node_id="n1",
    )
    service = WorkflowVersionService(db)
    db.get = AsyncMock(return_value=published)

    resolved = await service.resolve_run_version(definition)
    assert resolved.id == "pub-1"
    assert resolved.is_published is True
