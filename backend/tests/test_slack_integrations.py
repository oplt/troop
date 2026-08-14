"""Tests for Slack connector integrations (CONN-002)."""

from __future__ import annotations

import hashlib
import hmac
import time

import pytest

from backend.modules.workforce.integrations.slack import (
    hash_link_token,
    validate_slack_request_signature,
)


def _sign(body: bytes, *, secret: str, timestamp: str) -> str:
    basestring = f"v0:{timestamp}:{body.decode()}"
    digest = hmac.new(secret.encode(), basestring.encode(), hashlib.sha256).hexdigest()
    return f"v0={digest}"


def test_validate_slack_request_signature_accepts_valid_request() -> None:
    secret = "slack-signing-secret"
    body = b'{"type":"event_callback","event":{"type":"message","text":"hello"}}'
    timestamp = str(int(time.time()))
    signature = _sign(body, secret=secret, timestamp=timestamp)
    assert validate_slack_request_signature(
        body=body,
        timestamp=timestamp,
        signature=signature,
        signing_secret=secret,
    )


def test_validate_slack_request_signature_rejects_bad_signature() -> None:
    body = b"{}"
    timestamp = str(int(time.time()))
    assert not validate_slack_request_signature(
        body=body,
        timestamp=timestamp,
        signature="v0=deadbeef",
        signing_secret="slack-signing-secret",
    )


def test_validate_slack_request_signature_rejects_stale_timestamp() -> None:
    secret = "slack-signing-secret"
    body = b"{}"
    timestamp = str(int(time.time()) - 600)
    signature = _sign(body, secret=secret, timestamp=timestamp)
    assert not validate_slack_request_signature(
        body=body,
        timestamp=timestamp,
        signature=signature,
        signing_secret=secret,
    )


def test_hash_link_token_is_deterministic() -> None:
    assert hash_link_token("abc") == hash_link_token("abc")
    assert hash_link_token("abc") != hash_link_token("def")


@pytest.mark.parametrize(
    ("provider_slug", "expected_strategy"),
    [
        ("slack", "provider_signature"),
        ("telegram", "hmac_secret"),
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


def test_slack_tools_registered_in_catalog() -> None:
    from backend.modules.workforce.constants import NATIVE_TOOL_CATALOG

    slugs = {item["slug"] for item in NATIVE_TOOL_CATALOG if item["slug"].startswith("slack.")}
    assert slugs >= {
        "slack.search_messages",
        "slack.get_thread",
        "slack.get_message",
        "slack.post_message",
        "slack.update_message",
    }


def test_slack_post_message_contract_requires_durable_claim() -> None:
    from backend.modules.orchestration.external_effect_inventory import get_external_effect_contract
    from backend.modules.workforce.action_metadata import IdempotencyStrategy

    contract = get_external_effect_contract("slack.post_message")
    assert contract is not None
    assert contract.idempotency_strategy == IdempotencyStrategy.DURABLE_CLAIM
    assert "approval_required" in contract.approval_rule
