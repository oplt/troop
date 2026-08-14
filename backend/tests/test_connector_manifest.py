"""Tests for CONN-001A connector manifest schema and provider contract."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.workforce.action_metadata import SideEffect
from backend.modules.workforce.connectors import (
    AuthStrategyType,
    ConnectorAuthContext,
    ConnectorAuthResult,
    ConnectorHealthResult,
    ConnectorManifest,
    ConnectorManifestRegistry,
    ConnectorNormalizedEvent,
    ConnectorOperationManifest,
    ConnectorProvider,
    OperationKind,
    WebhookVerificationStrategy,
    build_gmail_manifest,
    build_telegram_manifest,
    provider_implements_contract,
    register_builtin_manifests,
    register_builtin_providers,
)
from backend.modules.workforce.connectors.provider import (
    ConnectorActionResult,
    ConnectorTriggerRegistration,
)


class _StubConnectorProvider:
    def __init__(self, manifest: ConnectorManifest) -> None:
        self._manifest = manifest

    @property
    def manifest(self) -> ConnectorManifest:
        return self._manifest

    async def authorize(
        self,
        db: AsyncSession,
        context: ConnectorAuthContext,
    ) -> ConnectorAuthResult:
        return ConnectorAuthResult(status="pending", authorization_url="https://example.test/auth")

    async def refresh(self, db: AsyncSession, installation_id: str) -> ConnectorAuthResult:
        return ConnectorAuthResult(status="active", installation_id=installation_id)

    async def health(self, db: AsyncSession, installation_id: str) -> ConnectorHealthResult:
        return ConnectorHealthResult(ok=True, status="healthy")

    async def register_trigger(
        self,
        db: AsyncSession,
        installation_id: str,
        trigger_slug: str,
        config: dict[str, Any],
    ) -> ConnectorTriggerRegistration:
        return ConnectorTriggerRegistration(
            trigger_slug=trigger_slug,
            subscription_id="sub-1",
            metadata={"installation_id": installation_id},
        )

    async def unregister_trigger(
        self,
        db: AsyncSession,
        installation_id: str,
        subscription_id: str,
    ) -> None:
        return None

    async def normalize_event(
        self,
        raw_event: dict[str, Any],
        *,
        installation_id: str | None = None,
    ) -> ConnectorNormalizedEvent:
        return ConnectorNormalizedEvent(
            event_type="test.event",
            dedupe_key=str(raw_event.get("id") or "dedupe"),
            payload=raw_event,
            occurred_at=datetime.now(UTC),
            installation_id=installation_id,
        )

    async def execute_action(
        self,
        db: AsyncSession,
        installation_id: str,
        action_slug: str,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> ConnectorActionResult:
        return ConnectorActionResult(status="succeeded", output={"action": action_slug})


@pytest.fixture(autouse=True)
def _reset_registry() -> None:
    ConnectorManifestRegistry.reset()
    register_builtin_manifests()
    register_builtin_providers()


def test_gmail_manifest_has_required_fields():
    manifest = build_gmail_manifest()
    assert manifest.provider_slug == "gmail"
    assert manifest.version == "1.0.0"
    assert manifest.auth.type == AuthStrategyType.OAUTH2
    assert manifest.auth.pkce_required is True
    assert manifest.webhook is not None
    assert manifest.webhook.strategy == WebhookVerificationStrategy.OIDC_JWT
    assert manifest.health is not None
    assert manifest.rate_limits is not None
    assert manifest.get_operation("gmail.send_draft") is not None
    assert manifest.get_operation("gmail.new_message") is not None


def test_telegram_manifest_uses_bot_token_and_hmac_webhook():
    manifest = build_telegram_manifest()
    assert manifest.auth.type == AuthStrategyType.BOT_TOKEN
    assert manifest.webhook is not None
    assert manifest.webhook.strategy == WebhookVerificationStrategy.HMAC_SECRET
    assert {action.slug for action in manifest.actions} == {
        "telegram.send_message",
        "telegram.edit_message",
        "telegram.answer_callback",
    }


def test_read_actions_expose_parallel_safe_governance():
    manifest = build_gmail_manifest()
    read_ops = [
        manifest.get_operation("gmail.search_messages"),
        manifest.get_operation("gmail.get_thread"),
    ]
    for operation in read_ops:
        assert operation is not None
        assert operation.governance is not None
        assert operation.governance.side_effect == SideEffect.READ
        assert operation.parallel_safe is True


def test_send_draft_requires_approval_and_durable_idempotency():
    operation = build_gmail_manifest().get_operation("gmail.send_draft")
    assert operation is not None
    assert operation.requires_approval is True
    assert operation.idempotency_strategy == "durable_claim"


def test_manifest_rejects_duplicate_operation_slugs():
    duplicate = ConnectorOperationManifest(
        slug="gmail.get_thread",
        name="Duplicate",
        operation_kind=OperationKind.READ,
    )
    with pytest.raises(ValidationError):
        ConnectorManifest(
            provider_slug="bad",
            version="1",
            name="Bad",
            auth={"type": "none"},
            actions=[duplicate, duplicate],
        )


def test_registry_lists_builtin_manifests():
    manifests = ConnectorManifestRegistry.list_manifests()
    assert {item.provider_slug for item in manifests} == {
        "gmail",
        "outlook",
        "google_calendar",
        "microsoft_calendar",
        "telegram",
        "slack",
        "teams",
    }


def test_provider_contract_validation():
    manifest = build_gmail_manifest()
    provider = _StubConnectorProvider(manifest)
    assert isinstance(provider, ConnectorProvider)
    assert provider_implements_contract(provider) is True


def test_incomplete_provider_fails_contract_validation():
    class _Incomplete:
        @property
        def manifest(self) -> ConnectorManifest:
            return build_gmail_manifest()

    assert provider_implements_contract(_Incomplete()) is False


@pytest.mark.asyncio
async def test_stub_provider_lifecycle_methods():
    provider = _StubConnectorProvider(build_gmail_manifest())
    db = None  # stub methods do not touch db
    auth = await provider.authorize(
        db,
        ConnectorAuthContext(owner_id="owner-1"),
    )
    assert auth.authorization_url is not None

    health = await provider.health(db, "install-1")
    assert health.ok is True

    registration = await provider.register_trigger(
        db,
        "install-1",
        "gmail.new_message",
        {"label_ids": ["INBOX"]},
    )
    assert registration.subscription_id == "sub-1"

    event = await provider.normalize_event({"id": "evt-1"}, installation_id="install-1")
    assert event.dedupe_key == "evt-1"

    result = await provider.execute_action(
        db,
        "install-1",
        "gmail.get_thread",
        {"thread_id": "t-1"},
        {"owner_id": "owner-1"},
    )
    assert result.status == "succeeded"
