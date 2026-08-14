"""Tests for Outlook Mail connector integrations (CONN-004)."""

from __future__ import annotations

import pytest

from backend.modules.workforce.integrations.email import (
    canonical_outlook_email_action_arguments,
    normalize_outlook_message,
    outlook_email_action_arguments_hash,
    outlook_thread_fingerprint,
)


def test_normalize_outlook_message_maps_graph_fields() -> None:
    message = {
        "id": "msg-1",
        "conversationId": "conv-1",
        "subject": "Question",
        "receivedDateTime": "2026-01-01T12:00:00Z",
        "from": {"emailAddress": {"name": "Customer", "address": "Customer@Example.com"}},
        "toRecipients": [{"emailAddress": {"name": "Team", "address": "team@example.com"}}],
        "body": {"contentType": "html", "content": "<p>Hello</p><script>x</script>"},
        "attachments": [{"id": "att-1", "name": "invoice.pdf", "contentType": "application/pdf", "size": 42}],
    }
    normalized = normalize_outlook_message(message, connector_installation_id="outlook-install")
    assert normalized["provider"] == "outlook"
    assert normalized["from"]["email"] == "customer@example.com"
    assert normalized["thread_id"] == "conv-1"
    assert "script" not in normalized["html_body"].lower()


def test_outlook_email_hash_is_canonical() -> None:
    base = {
        "provider": "outlook",
        "connector_installation_id": "install-a",
        "outlook_draft_id": "draft-1",
        "thread_id": "conv-1",
        "from": "Team@Example.com",
        "to": [{"email": "a@example.com"}, {"email": "b@example.com"}],
        "subject": "Re: question",
        "body": "Exact approved body",
    }
    reordered = {**base, "to": list(reversed(base["to"]))}
    assert outlook_email_action_arguments_hash(base) == outlook_email_action_arguments_hash(reordered)
    assert outlook_email_action_arguments_hash(base) != outlook_email_action_arguments_hash(
        {**base, "body": "Changed"}
    )
    canonical = canonical_outlook_email_action_arguments(base)
    assert canonical["provider"] == "outlook"
    assert canonical["outlook_draft_id"] == "draft-1"


def test_outlook_thread_fingerprint_detects_new_message() -> None:
    original = {
        "conversation_id": "conv-1",
        "value": [{"id": "m1", "lastModifiedDateTime": "t1", "receivedDateTime": "r1"}],
    }
    changed = {
        "conversation_id": "conv-1",
        "value": [
            {"id": "m1", "lastModifiedDateTime": "t1", "receivedDateTime": "r1"},
            {"id": "m2", "lastModifiedDateTime": "t2", "receivedDateTime": "r2"},
        ],
    }
    assert outlook_thread_fingerprint(original) != outlook_thread_fingerprint(changed)
    with_draft = {
        **original,
        "value": [
            *original["value"],
            {"id": "draft", "isDraft": True, "lastModifiedDateTime": "t2", "receivedDateTime": "r2"},
        ],
    }
    assert outlook_thread_fingerprint(original) == outlook_thread_fingerprint(with_draft)


def test_outlook_tools_registered_in_catalog() -> None:
    from backend.modules.workforce.constants import NATIVE_TOOL_CATALOG

    slugs = {item["slug"] for item in NATIVE_TOOL_CATALOG if item["slug"].startswith("outlook.")}
    assert slugs >= {
        "outlook.search_messages",
        "outlook.get_message",
        "outlook.get_thread",
        "outlook.create_draft",
        "outlook.update_draft",
        "outlook.send_draft",
        "outlook.add_label",
    }


def test_outlook_send_draft_contract_requires_durable_claim() -> None:
    from backend.modules.orchestration.external_effect_inventory import get_external_effect_contract
    from backend.modules.workforce.action_metadata import IdempotencyStrategy

    contract = get_external_effect_contract("outlook.send_draft")
    assert contract is not None
    assert contract.idempotency_strategy == IdempotencyStrategy.DURABLE_CLAIM
    assert "approval_required" in contract.approval_rule


@pytest.mark.parametrize("provider_slug", ["outlook"])
def test_manifest_webhook_strategy_outlook(provider_slug: str) -> None:
    from backend.modules.workforce.connectors import (
        ConnectorManifestRegistry,
        register_builtin_manifests,
    )

    ConnectorManifestRegistry.reset()
    register_builtin_manifests()
    manifest = ConnectorManifestRegistry.get_manifest(provider_slug)
    assert manifest is not None
    assert manifest.webhook is not None
    assert manifest.webhook.strategy.value == "client_state"
