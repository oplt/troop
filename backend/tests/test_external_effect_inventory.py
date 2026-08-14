"""Tests for REL-001A external-effect / idempotency inventory."""

from __future__ import annotations

import pytest
from backend.modules.orchestration.external_effect_inventory import (
    IdempotencyStrategy,
    SideEffect,
    assert_inventory_covers_mutating_catalog,
    get_external_effect_contract,
    is_autonomous_blocked,
    list_autonomous_blocked_action_keys,
    mutating_catalog_slugs,
)
from backend.modules.workforce.constants import NATIVE_TOOL_CATALOG


def test_inventory_covers_native_tool_catalog():
    for item in NATIVE_TOOL_CATALOG:
        slug = item["slug"]
        contract = get_external_effect_contract(slug)
        assert contract is not None, f"missing contract for {slug}"


def test_mutating_catalog_has_contract_entries():
    assert_inventory_covers_mutating_catalog()


def test_durable_claim_mutators_in_catalog():
    durable_mutators = []
    for slug in mutating_catalog_slugs():
        contract = get_external_effect_contract(slug)
        assert contract is not None
        if contract.idempotency_strategy == IdempotencyStrategy.DURABLE_CLAIM:
            durable_mutators.append(slug)
    assert set(durable_mutators) == {
        "gmail.send_draft",
        "outlook.send_draft",
        "slack.post_message",
        "teams.post_message",
    }


@pytest.mark.parametrize(
    "slug",
    [
        "gmail.create_draft",
        "gmail.add_label",
        "telegram.send_message",
        "github_comment",
        "github_create_pr",
        "fs_write",
    ],
)
def test_known_mutators_block_autonomous(slug: str):
    contract = get_external_effect_contract(slug)
    assert contract is not None
    assert contract.side_effect != SideEffect.READ
    assert contract.blocks_autonomous_use is True
    assert is_autonomous_blocked(slug) is True


@pytest.mark.parametrize(
    "slug",
    ["gmail.search_messages", "web_fetch", "fs_read", "db_query"],
)
def test_read_actions_do_not_block_autonomous(slug: str):
    contract = get_external_effect_contract(slug)
    assert contract is not None
    assert contract.side_effect == SideEffect.READ
    assert contract.blocks_autonomous_use is False


def test_mcp_and_a2a_patterns_block_autonomous():
    assert is_autonomous_blocked("mcp.server/tool") is True
    assert is_autonomous_blocked("a2a.send_task") is True
    assert "mcp.*" in list_autonomous_blocked_action_keys()


@pytest.mark.asyncio
async def test_authorize_tool_upgrades_autonomous_when_idempotency_missing():
    from unittest.mock import AsyncMock, MagicMock, patch

    from backend.modules.workforce.services.tool_registry import ToolRegistryService

    db = AsyncMock()
    service = ToolRegistryService(db)
    provider = MagicMock()
    provider.validate_permissions = AsyncMock(return_value=True)
    service.providers["connector"] = provider

    with patch.object(
        service.policy, "resolve", AsyncMock(return_value={"decision": "autonomous"})
    ):
        auth = await service.authorize_tool(
            "owner-1",
            "telegram.send_message",
            {"owner_id": "owner-1", "connector_installation_id": "inst-1"},
        )

    assert auth["permitted"] is True
    assert auth["decision"] == "approval_required"
    resolution = auth.get("resolution") or {}
    assert resolution.get("matched_scope") == "idempotency_contract"
    assert resolution.get("idempotency_blocked_autonomous") is True


@pytest.mark.asyncio
async def test_authorize_tool_allows_autonomous_read_tools():
    from unittest.mock import AsyncMock, MagicMock, patch

    from backend.modules.workforce.services.tool_registry import ToolRegistryService

    db = AsyncMock()
    service = ToolRegistryService(db)
    provider = MagicMock()
    provider.validate_permissions = AsyncMock(return_value=True)
    service.providers["native"] = provider

    with patch.object(
        service.policy, "resolve", AsyncMock(return_value={"decision": "autonomous"})
    ):
        auth = await service.authorize_tool(
            "owner-1",
            "web_fetch",
            {"owner_id": "owner-1"},
        )

    assert auth["decision"] == "autonomous"
    assert (auth.get("resolution") or {}).get("idempotency_blocked_autonomous") is not True
