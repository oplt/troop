from __future__ import annotations

import base64
import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from backend.core.config import settings
from backend.modules.orchestration.models import ApprovalRequest
from backend.modules.orchestration.security import decrypt_secret, encrypt_secret
from backend.modules.orchestration.tool_execution_context import arguments_hash
from backend.modules.workforce.constants import NATIVE_TOOL_CATALOG
from backend.modules.workforce.integrations.email import (
    canonical_email_action_arguments,
    email_action_arguments_hash,
    normalize_gmail_message,
    sanitize_email_html,
    thread_fingerprint,
)
from backend.modules.workforce.integrations.events import (
    decode_pubsub_push,
    verify_pubsub_token,
)
from backend.modules.workforce.integrations.gmail import (
    GMAIL_SCOPES,
    GmailAdapter,
    GmailAPIError,
    GmailOAuthService,
)
from backend.modules.workforce.integrations.telegram import (
    hash_link_token,
    validate_telegram_webhook_secret,
)
from backend.modules.workforce.models import (
    ApprovalDelivery,
    ApprovalInteraction,
    ConnectorInstallation,
    ConnectorOAuthState,
    DraftExecutionMetadata,
    ExternalActionExecution,
    ExternalEvent,
    TelegramIdentityBinding,
    TriggerSubscription,
)
from backend.modules.workforce.services.workflow_runtime import WorkflowRuntimeService


def _b64(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")


def test_normalize_gmail_message_sanitizes_html_and_preserves_attachment_metadata() -> None:
    message = {
        "id": "msg-1",
        "threadId": "thread-1",
        "internalDate": "1710000000000",
        "payload": {
            "mimeType": "multipart/mixed",
            "headers": [
                {"name": "From", "value": "Customer <Customer@Example.com>"},
                {"name": "To", "value": "Team <team@example.com>"},
                {"name": "Cc", "value": "audit@example.com"},
                {"name": "Subject", "value": "Question"},
                {"name": "Message-ID", "value": "<external@example.com>"},
            ],
            "parts": [
                {
                    "mimeType": "text/html",
                    "body": {
                        "data": _b64(
                            '<p onclick="steal()">Hello</p>'
                            '<script>alert("secret")</script>'
                            '<a href="javascript:alert(1)">bad</a>'
                        )
                    },
                },
                {
                    "mimeType": "application/pdf",
                    "filename": "invoice.pdf",
                    "body": {"attachmentId": "att-1", "size": 999_999_999},
                },
            ],
        },
    }
    normalized = normalize_gmail_message(message, connector_installation_id="gmail-install")
    assert normalized["from"]["email"] == "customer@example.com"
    assert normalized["to"][0]["email"] == "team@example.com"
    assert normalized["text_body"] == "Hello bad"
    assert "script" not in normalized["html_body"].lower()
    assert "onclick" not in normalized["html_body"].lower()
    assert "javascript:" not in normalized["html_body"].lower()
    assert normalized["attachments"] == [
        {
            "filename": "invoice.pdf",
            "mime_type": "application/pdf",
            "size": 999_999_999,
            "attachment_id": "att-1",
        }
    ]


@pytest.mark.parametrize(
    "unsafe",
    [
        "<SCRIPT>bad()</SCRIPT><p>safe</p>",
        '<img src="data:text/html,bad" onerror="bad()">',
        '<iframe src="https://evil.example">x</iframe>',
    ],
)
def test_sanitize_email_html_removes_active_content(unsafe: str) -> None:
    cleaned = sanitize_email_html(unsafe).lower()
    assert "<script" not in cleaned
    assert "<iframe" not in cleaned
    assert "onerror" not in cleaned
    assert "data:" not in cleaned


def test_email_approval_hash_is_canonical_and_exact() -> None:
    base = {
        "provider": "gmail",
        "connector_installation_id": "install-a",
        "gmail_draft_id": "draft-1",
        "thread_id": "thread-1",
        "in_reply_to": "<message-1>",
        "from": "Team@Example.com",
        "to": [{"email": "B@example.com"}, {"email": "a@example.com"}],
        "cc": [],
        "bcc": [],
        "subject": "Re: question",
        "body": "Exact approved body",
        "attachments": [
            {"attachment_id": "b", "filename": "b.pdf", "size": 2},
            {"attachment_id": "a", "filename": "a.pdf", "size": 1},
        ],
        "untrusted_ui_only_field": True,
    }
    reordered = {
        **base,
        "to": list(reversed(base["to"])),
        "attachments": list(reversed(base["attachments"])),
    }
    assert email_action_arguments_hash(base) == email_action_arguments_hash(reordered)
    assert email_action_arguments_hash(base) != email_action_arguments_hash(
        {**base, "body": "Modified after approval"}
    )
    assert email_action_arguments_hash(base) != email_action_arguments_hash(
        {**base, "connector_installation_id": "install-from-other-tenant"}
    )
    canonical = canonical_email_action_arguments(base)
    assert canonical["from"] == "team@example.com"
    assert "untrusted_ui_only_field" not in canonical


def test_thread_fingerprint_detects_new_message_and_ignores_unrelated_payload() -> None:
    original = {
        "id": "thread-1",
        "messages": [{"id": "m1", "historyId": "10", "internalDate": "100"}],
    }
    same = {**original, "snippet": "provider can change this"}
    changed = {
        **original,
        "messages": [
            *original["messages"],
            {"id": "m2", "historyId": "11", "internalDate": "101"},
        ],
    }
    assert thread_fingerprint(original) == thread_fingerprint(same)
    assert thread_fingerprint(original) != thread_fingerprint(changed)
    with_draft = {
        **original,
        "messages": [
            *original["messages"],
            {
                "id": "draft-message",
                "historyId": "12",
                "internalDate": "102",
                "labelIds": ["DRAFT"],
            },
        ],
    }
    assert thread_fingerprint(original) == thread_fingerprint(with_draft)


def test_pubsub_push_decoding_and_replay_identity() -> None:
    data = base64.b64encode(
        json.dumps({"emailAddress": "Owner@Example.com", "historyId": 123}).encode()
    ).decode()
    decoded = decode_pubsub_push({"message": {"messageId": "pubsub-1", "data": data}})
    assert decoded == {
        "email_address": "owner@example.com",
        "history_id": "123",
        "message_id": "pubsub-1",
    }


@pytest.mark.parametrize(
    "payload",
    [{}, {"message": {}}, {"message": {"data": "not-base64"}}, {"message": {"data": _b64("{}")}}],
)
def test_pubsub_push_rejects_malformed_payload(payload: dict) -> None:
    with pytest.raises(ValueError):
        decode_pubsub_push(payload)


def test_webhook_secret_checks_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "GOOGLE_PUBSUB_VERIFICATION_TOKEN", "pubsub-secret")
    monkeypatch.setattr(settings, "TELEGRAM_WEBHOOK_SECRET", "telegram-secret")
    assert verify_pubsub_token("Bearer pubsub-secret")
    assert not verify_pubsub_token("Bearer wrong")
    assert not verify_pubsub_token(None)
    assert validate_telegram_webhook_secret("telegram-secret")
    assert not validate_telegram_webhook_secret("wrong")
    assert not validate_telegram_webhook_secret(None)


def test_link_tokens_are_one_way_and_stable() -> None:
    assert hash_link_token("one-time-token") == hash_link_token("one-time-token")
    assert hash_link_token("one-time-token") != hash_link_token("other-token")
    assert "one-time-token" not in hash_link_token("one-time-token")


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


@pytest.mark.asyncio
async def test_oauth_begin_uses_state_pkce_and_never_returns_verifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr(settings, "GOOGLE_OAUTH_REDIRECT_URI", "https://troop.example/callback")
    fake_db = _FakeDB()
    result = await GmailOAuthService(fake_db).begin(
        "owner-1",
        company_id="company-1",
        scopes=list(GMAIL_SCOPES),
    )
    assert "response_type=code" in result["authorization_url"]
    assert "code_challenge=" in result["authorization_url"]
    assert "code_verifier" not in result["authorization_url"]
    assert "client_secret" not in result["authorization_url"]
    assert fake_db.commits == 1
    state = fake_db.added[0]
    assert isinstance(state, ConnectorOAuthState)
    assert len(state.state_hash) == 64
    assert "client-id" not in state.encrypted_code_verifier


@pytest.mark.asyncio
async def test_oauth_begin_rejects_scope_escalation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr(settings, "GOOGLE_OAUTH_REDIRECT_URI", "https://troop.example/callback")
    with pytest.raises(Exception) as exc:
        await GmailOAuthService(_FakeDB()).begin(
            "owner-1", scopes=["https://www.googleapis.com/auth/drive"]
        )
    assert getattr(exc.value, "status_code", None) == 422


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
        self.requests: list[dict] = []

    async def post(self, url: str, **kwargs):
        self.requests.append({"url": url, **kwargs})
        return self.response


@pytest.mark.asyncio
async def test_gmail_access_token_refresh_is_encrypted_and_revocation_fails_closed(
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
    async def fake_client(*_args, **_kwargs):
        yield client

    monkeypatch.setattr(
        "backend.modules.workforce.integrations.gmail.managed_http_client",
        fake_client,
    )
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "client")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "secret")
    token = await GmailAdapter(fake_db, installation)._access_token()
    assert token == "new-access"
    stored = json.loads(decrypt_secret(installation.secrets_ref) or "{}")
    assert stored == {
        "access_token": "new-access",
        "refresh_token": "refresh-secret",
    }
    assert client.requests[0]["data"]["grant_type"] == "refresh_token"

    client.response = _HTTPResponse(400, {"error": "invalid_grant"})
    installation.config_json["token_expires_at"] = (
        datetime.now(UTC) - timedelta(minutes=1)
    ).isoformat()
    with pytest.raises(GmailAPIError):
        await GmailAdapter(fake_db, installation)._access_token()
    assert installation.status == "reauthorization_required"


def test_catalog_marks_send_high_risk_and_approval_required() -> None:
    by_slug = {item["slug"]: item for item in NATIVE_TOOL_CATALOG}
    required = {
        "gmail.search_messages",
        "gmail.get_message",
        "gmail.get_thread",
        "gmail.create_draft",
        "gmail.update_draft",
        "gmail.send_draft",
        "gmail.add_label",
        "telegram.send_message",
        "telegram.edit_message",
        "telegram.answer_callback",
    }
    assert required <= by_slug.keys()
    assert by_slug["gmail.send_draft"]["risk_level"] == "high"
    assert by_slug["gmail.send_draft"]["requires_approval"] is True
    assert by_slug["gmail.get_thread"]["requires_approval"] is False


def test_workflow_argument_mapping_is_explicit_and_non_executable() -> None:
    service = WorkflowRuntimeService(None)
    variables = {
        "email": {
            "thread_id": "thread-1",
            "from": {"email": "customer@example.com"},
        },
        "body_text": "Reply",
    }
    resolved = service._resolve_workflow_mapping(
        {
            "thread_id": "$.email.thread_id",
            "to": {"$path": "email.from", "wrap_list": True},
            "body": "$.body_text",
            "missing": "$.email.nope",
            "literal": "__import__('os').system('false')",
        },
        variables,
    )
    assert resolved == {
        "thread_id": "thread-1",
        "to": [{"email": "customer@example.com"}],
        "body": "Reply",
        "missing": None,
        "literal": "__import__('os').system('false')",
    }


class _ScalarResult:
    def __init__(self, value) -> None:
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _SendDB(_FakeDB):
    def __init__(self, approval: ApprovalRequest, query_values: list[object]) -> None:
        super().__init__()
        self.approval = approval
        self.query_values = list(query_values)

    async def get(self, model, object_id):
        if model is ApprovalRequest and object_id == self.approval.id:
            return self.approval
        return None

    async def execute(self, _query):
        return _ScalarResult(self.query_values.pop(0))


def _send_fixture() -> tuple[dict, ApprovalRequest, ConnectorInstallation, DraftExecutionMetadata]:
    arguments = {
        "connector_installation_id": "gmail-install",
        "gmail_draft_id": "draft-1",
        "thread_id": "thread-1",
        "in_reply_to": "<m1>",
        "to": [{"email": "customer@example.com"}],
        "cc": [],
        "bcc": [],
        "subject": "Re: question",
        "body": "Approved exact body",
        "workflow_run_id": "workflow-run",
        "approval_request_id": "approval-1",
    }
    approved_arguments = {
        key: value
        for key, value in arguments.items()
        if key not in {"workflow_run_id", "approval_request_id"}
    }
    approval = ApprovalRequest(
        id="approval-1",
        approval_type="tool:gmail.send_draft",
        status="approved",
        requested_by_user_id="owner",
        payload_json={
            "owner_id": "owner",
            "workflow_run_id": "workflow-run",
            "workflow_node_id": "send",
            "arguments_hash": arguments_hash(approved_arguments),
            "draft_arguments": approved_arguments,
            "_consumed_at": datetime.now(UTC).isoformat(),
        },
    )
    installation = ConnectorInstallation(
        id="gmail-install",
        connector_definition_id="gmail-definition",
        owner_id="owner",
        name="Gmail",
        status="active",
        config_json={},
    )
    original_thread = {
        "id": "thread-1",
        "messages": [{"id": "m1", "historyId": "1", "internalDate": "1"}],
    }
    metadata = DraftExecutionMetadata(
        owner_id="owner",
        connector_installation_id="gmail-install",
        provider_draft_id="draft-1",
        thread_id="thread-1",
        thread_fingerprint=thread_fingerprint(original_thread),
        content_hash=email_action_arguments_hash(arguments),
        status="current",
    )
    return arguments, approval, installation, metadata


@pytest.mark.asyncio
async def test_gmail_send_claims_once_and_rejects_stale_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    arguments, approval, installation, metadata = _send_fixture()
    db = _SendDB(approval, [None, metadata])
    adapter = GmailAdapter(db, installation)

    async def stale_request(method: str, path: str, **_kwargs):
        assert method == "GET"
        assert "threads/thread-1" in path
        return {
            "id": "thread-1",
            "messages": [
                {"id": "m1", "historyId": "1", "internalDate": "1"},
                {"id": "m2", "historyId": "2", "internalDate": "2"},
            ],
        }

    monkeypatch.setattr(adapter, "request", stale_request)
    with pytest.raises(GmailAPIError, match="thread changed"):
        await adapter.send_draft_exactly_once(arguments)
    action = next(item for item in db.added if isinstance(item, ExternalActionExecution))
    assert action.status == "stale"
    assert metadata.status == "stale"
    assert approval.status == "stale"


@pytest.mark.asyncio
async def test_gmail_send_returns_recorded_result_without_second_provider_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    arguments, approval, installation, _metadata = _send_fixture()
    existing = ExternalActionExecution(
        owner_id="owner",
        connector_installation_id="gmail-install",
        workflow_run_id="workflow-run",
        approval_request_id="approval-1",
        action_key="gmail.send_draft",
        idempotency_key="existing",
        arguments_hash=email_action_arguments_hash(arguments),
        status="succeeded",
        result_json={"id": "sent-message"},
    )
    db = _SendDB(approval, [existing])
    adapter = GmailAdapter(db, installation)

    async def should_not_call(*_args, **_kwargs):
        raise AssertionError("Gmail must not be called twice")

    monkeypatch.setattr(adapter, "request", should_not_call)
    result = await adapter.send_draft_exactly_once(arguments)
    assert result == {"id": "sent-message"}


def test_models_define_security_uniques_and_tenant_ownership() -> None:
    models = (
        TriggerSubscription,
        ExternalEvent,
        ApprovalDelivery,
        TelegramIdentityBinding,
        ApprovalInteraction,
        ExternalActionExecution,
    )
    for model in models:
        assert "owner_id" in model.__table__.columns
    event_uniques = {
        tuple(column.name for column in constraint.columns)
        for constraint in ExternalEvent.__table__.constraints
        if hasattr(constraint, "columns")
    }
    action_uniques = {
        tuple(column.name for column in constraint.columns)
        for constraint in ExternalActionExecution.__table__.constraints
        if hasattr(constraint, "columns")
    }
    assert ("provider", "dedupe_key") in event_uniques
    assert ("idempotency_key",) in action_uniques


@pytest.mark.asyncio
async def test_public_webhooks_reject_missing_auth_before_processing(app_client) -> None:
    gmail = await app_client.post("/api/v1/workforce/webhooks/gmail", json={})
    telegram = await app_client.post("/api/v1/workforce/webhooks/telegram", json={})
    assert gmail.status_code == 401
    assert telegram.status_code == 401


def test_expired_link_and_interaction_state_are_persistable() -> None:
    now = datetime.now(UTC)
    binding = TelegramIdentityBinding(
        owner_id="owner",
        connector_installation_id="telegram-install",
        link_token_hash=hash_link_token("token"),
        status="pending",
        token_expires_at=now - timedelta(seconds=1),
    )
    interaction = ApprovalInteraction(
        owner_id="owner",
        approval_request_id="approval",
        telegram_user_id="telegram-user",
        mode="replace_email_body",
        expected_input="text",
        status="pending",
        expires_at=now - timedelta(seconds=1),
    )
    assert binding.token_expires_at <= now
    assert interaction.expires_at <= now


def test_no_token_columns_are_exposed_on_installation_responses() -> None:
    from backend.modules.workforce.routers.connectors import ConnectorInstallationResponse

    fields = set(ConnectorInstallationResponse.model_fields)
    assert not fields.intersection({"access_token", "refresh_token", "bot_token", "secrets_ref"})


def test_browser_integration_contract_routes_are_registered() -> None:
    from backend.api.main import app

    routes = {
        (method, route.path)
        for route in app.routes
        for method in getattr(route, "methods", set())
    }
    required = {
        ("POST", "/api/v1/workforce/connectors/gmail/authorize"),
        ("GET", "/api/v1/workforce/connectors/gmail/status"),
        ("POST", "/api/v1/workforce/connectors/gmail/{installation_id}/disconnect"),
        ("GET", "/api/v1/workforce/connectors/telegram/status"),
        ("POST", "/api/v1/workforce/connectors/telegram/link"),
        ("GET", "/api/v1/workforce/trigger-subscriptions"),
        ("GET", "/api/v1/workforce/workflows/runs/{run_id}"),
        ("GET", "/api/v1/workforce/workflows/runs/{run_id}/steps"),
        ("PATCH", "/api/v1/orchestration/approvals/{approval_id}/payload"),
        ("POST", "/api/v1/orchestration/approvals/{approval_id}/request-changes"),
    }
    assert required <= routes


def test_approval_delivery_has_no_provider_send_capability() -> None:
    fields = set(ApprovalDelivery.__table__.columns.keys())
    assert "approval_request_id" in fields
    assert "external_message_id" in fields
    assert "gmail_draft_id" not in fields
    assert "send_email" not in fields
