"""Tests for Microsoft Teams connector integrations (CONN-003)."""

from __future__ import annotations

import pytest

from backend.modules.workforce.integrations.teams import (
    hash_link_token,
    validate_teams_bot_jwt,
)


@pytest.mark.asyncio
async def test_validate_teams_bot_jwt_rejects_missing_authorization() -> None:
    assert not await validate_teams_bot_jwt(None)
    assert not await validate_teams_bot_jwt("")
    assert not await validate_teams_bot_jwt("Basic abc")


@pytest.mark.asyncio
async def test_validate_teams_bot_jwt_rejects_malformed_bearer() -> None:
    assert not await validate_teams_bot_jwt("Bearer not-a-jwt")


def test_hash_link_token_is_deterministic() -> None:
    assert hash_link_token("abc") == hash_link_token("abc")
    assert hash_link_token("abc") != hash_link_token("def")


@pytest.mark.parametrize(
    ("provider_slug", "expected_strategy"),
    [
        ("teams", "oidc_jwt"),
        ("slack", "provider_signature"),
    ],
)
def test_manifest_webhook_strategy(provider_slug: str, expected_strategy: str) -> None:
    from backend.modules.workforce.connectors import (
        ConnectorManifestRegistry,
        register_builtin_manifests,
    )

    ConnectorManifestRegistry.reset()
    register_builtin_manifests()
    manifest = ConnectorManifestRegistry.get_manifest(provider_slug)
    assert manifest is not None
    assert manifest.webhook is not None
    assert manifest.webhook.strategy.value == expected_strategy


def test_teams_tools_registered_in_catalog() -> None:
    from backend.modules.workforce.constants import NATIVE_TOOL_CATALOG

    slugs = {item["slug"] for item in NATIVE_TOOL_CATALOG if item["slug"].startswith("teams.")}
    assert slugs >= {
        "teams.search_messages",
        "teams.get_thread",
        "teams.get_message",
        "teams.post_message",
        "teams.update_message",
    }


def test_teams_post_message_contract_requires_durable_claim() -> None:
    from backend.modules.orchestration.external_effect_inventory import get_external_effect_contract
    from backend.modules.workforce.action_metadata import IdempotencyStrategy

    contract = get_external_effect_contract("teams.post_message")
    assert contract is not None
    assert contract.idempotency_strategy == IdempotencyStrategy.DURABLE_CLAIM
    assert "approval_required" in contract.approval_rule
