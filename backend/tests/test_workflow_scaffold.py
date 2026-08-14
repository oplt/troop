"""Tests for natural-language workflow scaffold (PROD-002)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.modules.workforce.connectors.manifest import (
    AuthStrategyType,
    ConnectorAuthManifest,
    ConnectorManifest,
    ConnectorOperationManifest,
    OperationKind,
)
from backend.modules.workforce.services.workflow_scaffold_service import (
    WorkflowScaffoldService,
    _heuristic_generate,
)
from backend.modules.workforce.services.workflow_scaffold_validator import WorkflowScaffoldValidator


def _gmail_manifest() -> ConnectorManifest:
    return ConnectorManifest(
        provider_slug="gmail",
        version="1.0.0",
        name="Gmail",
        auth=ConnectorAuthManifest(type=AuthStrategyType.OAUTH2),
        triggers=[
            ConnectorOperationManifest(
                slug="gmail.new_message",
                name="New message",
                operation_kind=OperationKind.TRIGGER,
                required_scopes=["https://www.googleapis.com/auth/gmail.readonly"],
            )
        ],
        actions=[
            ConnectorOperationManifest(
                slug="gmail.get_thread",
                name="Get thread",
                operation_kind=OperationKind.READ,
                required_scopes=["https://www.googleapis.com/auth/gmail.readonly"],
            ),
            ConnectorOperationManifest(
                slug="gmail.create_draft",
                name="Create draft",
                operation_kind=OperationKind.ACTION,
                required_scopes=["https://www.googleapis.com/auth/gmail.compose"],
            ),
            ConnectorOperationManifest(
                slug="gmail.send_draft",
                name="Send draft",
                operation_kind=OperationKind.ACTION,
                requires_approval=True,
                required_scopes=["https://www.googleapis.com/auth/gmail.send"],
            ),
        ],
    )


def test_heuristic_generate_email_workflow_uses_installed_gmail_ops() -> None:
    catalog = {
        "installed_providers": ["gmail"],
        "operations": [
            {"slug": "gmail.new_message"},
            {"slug": "gmail.get_thread"},
            {"slug": "gmail.create_draft"},
            {"slug": "gmail.send_draft"},
        ],
    }
    installations = {
        "gmail": {
            "id": "inst-gmail",
            "granted_scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
        }
    }
    graph = _heuristic_generate(
        prompt="When a new email arrives, draft a reply and send after approval",
        catalog=catalog,
        installations_by_provider=installations,
    )
    node_types = [node["type"] for node in graph["nodes"]]
    assert node_types[0] == "trigger"
    assert "approval" in node_types
    assert any(
        node.get("config", {}).get("tool_slug") == "gmail.send_draft"
        for node in graph["nodes"]
        if node["type"] == "tool"
    )


def test_validator_flags_missing_connection_scope_and_approval() -> None:
    manifest = _gmail_manifest()
    validator = WorkflowScaffoldValidator(
        allowed_operation_slugs={
            "gmail.new_message",
            "gmail.get_thread",
            "gmail.send_draft",
        },
        manifests_by_provider={"gmail": manifest},
        installations_by_provider={
            "gmail": {
                "id": "inst-gmail",
                "granted_scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
            }
        },
    )
    gaps = validator.analyze_gaps(
        nodes=[
            {
                "id": "trigger",
                "type": "trigger",
                "config": {"trigger_type": "gmail_new_message"},
            },
            {
                "id": "send",
                "type": "tool",
                "config": {"tool_slug": "gmail.send_draft", "connector_installation_id": "inst-gmail"},
            },
        ],
        edges=[{"from": "trigger", "to": "send"}],
        entry_node_id="trigger",
    )
    kinds = {gap["kind"] for gap in gaps}
    assert "missing_connection" in kinds
    assert "missing_scope" in kinds
    assert "missing_approval_step" in kinds


def test_validator_rejects_unavailable_operation() -> None:
    validator = WorkflowScaffoldValidator(
        allowed_operation_slugs={"gmail.get_thread"},
        manifests_by_provider={"gmail": _gmail_manifest()},
        installations_by_provider={
            "gmail": {"id": "inst-gmail", "granted_scopes": []},
        },
    )
    gaps = validator.analyze_gaps(
        nodes=[
            {
                "id": "hubspot",
                "type": "tool",
                "config": {
                    "tool_slug": "hubspot.update_contact",
                    "connector_installation_id": "inst-gmail",
                },
            }
        ],
        edges=[],
        entry_node_id="hubspot",
    )
    assert any(gap["kind"] == "unavailable_operation" for gap in gaps)


@pytest.mark.asyncio
async def test_generate_persists_draft_without_publish() -> None:
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.get = AsyncMock(return_value=None)

    service = WorkflowScaffoldService(db)
    manifest = _gmail_manifest()

    with (
        patch.object(
            service,
            "_load_installation_context",
            AsyncMock(
                return_value=(
                    {
                        "gmail": {
                            "id": "inst-gmail",
                            "name": "Gmail",
                            "status": "active",
                            "granted_scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
                        }
                    },
                    {"gmail": manifest},
                )
            ),
        ),
        patch(
            "backend.modules.workforce.services.workflow_scaffold_service.WorkflowVersionService.ensure_draft",
            AsyncMock(
                return_value=SimpleNamespace(
                    metadata_json={},
                    nodes_json=[],
                    edges_json=[],
                    entry_node_id="trigger",
                )
            ),
        ) as ensure_draft_mock,
    ):
        result = await service.generate(
            owner_id="owner-1",
            prompt="Triage incoming Gmail and draft replies",
            use_llm=False,
        )

    assert result["published"] is False
    assert result["workflow_id"]
    assert result["draft"]["nodes"]
    assert isinstance(result["gaps"], list)
    assert result["provenance"]["source"] == "nl_scaffold"
    ensure_draft_mock.assert_awaited_once()
