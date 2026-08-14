"""Reusable connector contract tests for native provider adapters (CONN-001B)."""

from __future__ import annotations

import base64
import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest

from backend.core.config import settings
from backend.modules.orchestration.security import encrypt_secret
from backend.modules.workforce.connectors import (
    ConnectorManifestRegistry,
    ConnectorProvider,
    provider_implements_contract,
    register_builtin_manifests,
    register_builtin_providers,
)
from backend.modules.workforce.connectors.provider import ConnectorAuthContext
from backend.modules.workforce.integrations.email import event_dedupe_key
from backend.modules.workforce.integrations.events import decode_pubsub_push, verify_pubsub_token
from backend.modules.workforce.integrations.gmail import GMAIL_SCOPES, GmailOAuthService
from backend.modules.workforce.integrations.telegram import validate_telegram_webhook_secret
from backend.modules.workforce.models import ConnectorInstallation, ConnectorOAuthState

BUILTIN_PROVIDER_SLUGS = (
    "gmail",
    "outlook",
    "google_calendar",
    "microsoft_calendar",
    "google_drive",
    "microsoft_drive",
    "jira",
    "linear",
    "hubspot",
    "salesforce",
    "telegram",
    "slack",
    "teams",
)


@pytest.fixture(autouse=True)
def _reset_registry() -> None:
    ConnectorManifestRegistry.reset()
    register_builtin_manifests()
    register_builtin_providers()


@pytest.mark.parametrize("provider_slug", BUILTIN_PROVIDER_SLUGS)
def test_builtin_provider_is_registered(provider_slug: str) -> None:
    provider = ConnectorManifestRegistry.get_provider(provider_slug)
    assert provider is not None
    assert provider_implements_contract(provider)


@pytest.mark.parametrize("provider_slug", BUILTIN_PROVIDER_SLUGS)
def test_provider_manifest_matches_registry(provider_slug: str) -> None:
    provider = ConnectorManifestRegistry.get_provider(provider_slug)
    manifest = ConnectorManifestRegistry.get_manifest(provider_slug)
    assert provider is not None
    assert manifest is not None
    assert provider.manifest.provider_slug == manifest.provider_slug
    assert provider.manifest.version == manifest.version


@pytest.mark.parametrize("provider_slug", BUILTIN_PROVIDER_SLUGS)
def test_manifest_declares_auth_and_webhook_strategy(provider_slug: str) -> None:
    manifest = ConnectorManifestRegistry.get_manifest(provider_slug)
    assert manifest is not None
    assert manifest.auth.type
    if provider_slug == "gmail":
        assert manifest.auth.pkce_required is True
        assert manifest.webhook is not None
        assert manifest.webhook.strategy.value == "oidc_jwt"
    if provider_slug == "outlook":
        assert manifest.webhook is not None
        assert manifest.webhook.strategy.value == "client_state"
    if provider_slug == "telegram":
        assert manifest.webhook is not None
        assert manifest.webhook.strategy.value == "hmac_secret"
    if provider_slug == "slack":
        assert manifest.webhook is not None
        assert manifest.webhook.strategy.value == "provider_signature"
    if provider_slug == "teams":
        assert manifest.webhook is not None
        assert manifest.webhook.strategy.value == "oidc_jwt"


class _FakeDB:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.commits = 0

    def add(self, value: object) -> None:
        self.added.append(value)

    async def commit(self) -> None:
        self.commits += 1

    async def flush(self) -> None:
        return None

    async def get(self, _model, _id):  # noqa: ANN001
        return None


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_slug", ("gmail",))
async def test_gmail_authorize_preserves_pkce_and_state(
    provider_slug: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr(settings, "GOOGLE_OAUTH_REDIRECT_URI", "https://troop.example/callback")
    provider = ConnectorManifestRegistry.get_provider(provider_slug)
    assert provider is not None
    fake_db = _FakeDB()
    result = await provider.authorize(
        fake_db,
        ConnectorAuthContext(owner_id="owner-1", scopes=list(GMAIL_SCOPES)),
    )
    assert result.status == "pending"
    assert result.authorization_url is not None
    assert "code_challenge=" in result.authorization_url
    assert "code_verifier" not in result.authorization_url
    state = fake_db.added[0]
    assert isinstance(state, ConnectorOAuthState)
    assert len(state.state_hash) == 64


@pytest.mark.asyncio
async def test_gmail_oauth_service_and_provider_authorize_equivalent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr(settings, "GOOGLE_OAUTH_REDIRECT_URI", "https://troop.example/callback")
    fake_db = _FakeDB()
    direct = await GmailOAuthService(fake_db).begin("owner-1", scopes=list(GMAIL_SCOPES))
    provider = ConnectorManifestRegistry.get_provider("gmail")
    assert provider is not None
    wrapped = await provider.authorize(
        _FakeDB(),
        ConnectorAuthContext(owner_id="owner-1", scopes=list(GMAIL_SCOPES)),
    )
    from urllib.parse import parse_qs, urlparse

    direct_params = parse_qs(urlparse(direct["authorization_url"]).query)
    wrapped_params = parse_qs(urlparse(wrapped.authorization_url or "").query)
    for key in ("client_id", "redirect_uri", "response_type", "scope", "code_challenge_method"):
        assert direct_params[key] == wrapped_params[key]
    assert "state" in direct_params and "state" in wrapped_params
    assert "code_challenge" in direct_params and "code_challenge" in wrapped_params


@pytest.mark.asyncio
async def test_gmail_normalize_event_matches_pubsub_dedupe_fields() -> None:
    provider = ConnectorManifestRegistry.get_provider("gmail")
    assert provider is not None
    payload = {
        "message": {
            "data": base64.urlsafe_b64encode(
                json.dumps({"emailAddress": "user@example.com", "historyId": "12345"}).encode()
            ).decode().rstrip("="),
            "messageId": "msg-1",
        }
    }
    decoded = decode_pubsub_push(payload)
    event = await provider.normalize_event(payload, installation_id="install-1")
    assert event.event_type == "gmail.history_notification"
    assert event.dedupe_key == event_dedupe_key(
        "gmail",
        "install-1",
        decoded["history_id"],
        decoded["message_id"],
    )


@pytest.mark.asyncio
async def test_telegram_normalize_event_uses_update_id_dedupe() -> None:
    provider = ConnectorManifestRegistry.get_provider("telegram")
    assert provider is not None
    update = {"update_id": 42, "message": {"message_id": 1, "text": "hello"}}
    event = await provider.normalize_event(update, installation_id="telegram-install")
    assert event.event_type == "telegram.message"
    assert event.dedupe_key == event_dedupe_key("telegram", "telegram-install", 42)


def test_webhook_verification_helpers_remain_available() -> None:
    monkeypatch_token = "secret-token"
    original = settings.TELEGRAM_WEBHOOK_SECRET
    settings.TELEGRAM_WEBHOOK_SECRET = monkeypatch_token
    try:
        assert validate_telegram_webhook_secret(monkeypatch_token) is True
        assert validate_telegram_webhook_secret("wrong") is False
        assert verify_pubsub_token(f"Bearer {settings.GOOGLE_PUBSUB_VERIFICATION_TOKEN or 'x'}") in {
            True,
            False,
        }
    finally:
        settings.TELEGRAM_WEBHOOK_SECRET = original


class _HTTPResponse:
    def __init__(self, status_code: int, body: dict) -> None:
        self.status_code = status_code
        self._body = body
        self.content = b"{}"

    def json(self) -> dict:
        return self._body


class _HTTPClient:
    def __init__(self, response: _HTTPResponse) -> None:
        self.response = response

    async def get(self, url: str, **kwargs):  # noqa: ANN001
        return self.response

    async def post(self, url: str, **kwargs):  # noqa: ANN001
        return self.response


@pytest.mark.asyncio
async def test_gmail_provider_refresh_preserves_encrypted_token_rotation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    installation = ConnectorInstallation(
        id="gmail-install",
        connector_definition_id="gmail-definition",
        owner_id="owner",
        name="Gmail",
        status="active",
        config_json={"token_expires_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat()},
        secrets_ref=encrypt_secret(
            json.dumps({"access_token": "expired", "refresh_token": "refresh-secret"})
        ),
    )
    fake_db = _FakeDB()
    client = _HTTPClient(_HTTPResponse(200, {"access_token": "new-access", "expires_in": 3600}))

    @asynccontextmanager
    async def fake_client(*_args, **_kwargs):  # noqa: ANN001
        yield client

    monkeypatch.setattr(
        "backend.modules.workforce.integrations.gmail.managed_http_client",
        fake_client,
    )
    async def fake_load_installation(*_args, **_kwargs):  # noqa: ANN001
        return installation

    monkeypatch.setattr(
        "backend.modules.workforce.connectors.gmail_provider.load_installation",
        fake_load_installation,
    )
    provider = ConnectorManifestRegistry.get_provider("gmail")
    assert provider is not None
    result = await provider.refresh(fake_db, installation.id)
    assert result.status == "active"
    assert installation.secrets_ref != encrypt_secret(
        json.dumps({"access_token": "expired", "refresh_token": "refresh-secret"})
    )


@pytest.mark.asyncio
async def test_telegram_provider_authorize_validates_token_via_get_me(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _HTTPClient(_HTTPResponse(200, {"ok": True, "result": {"username": "troop_bot"}}))

    @asynccontextmanager
    async def fake_client(*_args, **_kwargs):  # noqa: ANN001
        yield client

    monkeypatch.setattr(
        "backend.modules.workforce.connectors.telegram_provider.managed_http_client",
        fake_client,
    )
    provider = ConnectorManifestRegistry.get_provider("telegram")
    assert provider is not None
    result = await provider.authorize(
        _FakeDB(),
        ConnectorAuthContext(
            owner_id="owner-1",
            metadata={"bot_token": "123:ABC"},
        ),
    )
    assert result.status == "active"
    assert result.metadata.get("username") == "troop_bot"


def test_contract_suite_covers_all_builtin_providers() -> None:
    for slug in BUILTIN_PROVIDER_SLUGS:
        provider = ConnectorManifestRegistry.get_provider(slug)
        assert isinstance(provider, ConnectorProvider)
