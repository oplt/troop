"""REL-001B regression suite: duplicate delivery and external-effect replay."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from backend.modules.github.service import OrchestrationGithubServiceMixin
from backend.modules.identity_access.models import User
from backend.modules.orchestration.models import ApprovalRequest
from backend.modules.orchestration.tool_execution_context import arguments_hash
from backend.modules.workforce.integrations.email import (
    email_action_arguments_hash,
    thread_fingerprint,
)
from backend.modules.workforce.integrations.events import ExternalEventService
from backend.modules.workforce.integrations.gmail import GmailAdapter, GmailAPIError
from backend.modules.workforce.models import (
    ConnectorInstallation,
    DraftExecutionMetadata,
    ExternalActionExecution,
    ExternalEvent,
    TriggerSubscription,
)
from sqlalchemy.exc import IntegrityError


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one(self):
        if self.value is None:
            raise AssertionError("expected one row")
        return self.value

    def scalar_one_or_none(self):
        return self.value


class _ReplaySendDB:
    def __init__(
        self,
        *,
        approval: ApprovalRequest,
        query_sequence: list[object],
    ) -> None:
        self.approval = approval
        self.query_sequence = list(query_sequence)
        self.added: list[object] = []
        self.flushed = 0

    async def get(self, model, object_id):
        if model is ApprovalRequest and object_id == self.approval.id:
            return self.approval
        return None

    async def execute(self, _query):
        if not self.query_sequence:
            raise AssertionError("unexpected execute()")
        return _ScalarResult(self.query_sequence.pop(0))

    def add(self, item):
        self.added.append(item)

    async def flush(self):
        self.flushed += 1

    async def rollback(self):
        return None


def _send_arguments_and_approval(
    *,
    consumed: bool = True,
) -> tuple[dict, ApprovalRequest, ConnectorInstallation, DraftExecutionMetadata]:
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
    payload = {
        "owner_id": "owner",
        "workflow_run_id": "workflow-run",
        "workflow_node_id": "send",
        "arguments_hash": arguments_hash(approved_arguments),
        "draft_arguments": approved_arguments,
    }
    if consumed:
        payload["_consumed_at"] = datetime.now(UTC).isoformat()
    approval = ApprovalRequest(
        id="approval-1",
        approval_type="tool:gmail.send_draft",
        status="approved",
        requested_by_user_id="owner",
        payload_json=payload,
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
async def test_gmail_push_webhook_duplicate_ingest_returns_existing_event() -> None:
    existing = ExternalEvent(
        id="event-existing",
        owner_id="owner",
        provider="gmail",
        connector_installation_id="install-1",
        event_type="gmail.history_notification",
        dedupe_key="dedupe-1",
        payload_json={},
        status="pending",
    )
    subscription = TriggerSubscription(
        id="sub-1",
        owner_id="owner",
        connector_installation_id="install-1",
        workflow_id="wf-1",
        workflow_version_id="wfv-1",
        node_id="trigger",
        provider="gmail",
        status="active",
    )
    installation = ConnectorInstallation(
        id="install-1",
        connector_definition_id="def-1",
        owner_id="owner",
        name="Gmail",
        status="active",
        config_json={"email_address": "owner@example.com"},
        metadata_json={"email_address": "owner@example.com"},
    )
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock(side_effect=IntegrityError("duplicate", {}, Exception()))
    db.rollback = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    call_state = {"count": 0}

    async def _execute(query):
        call_state["count"] += 1
        if call_state["count"] == 1:
            return MagicMock(all=MagicMock(return_value=[(subscription, installation)]))
        return _ScalarResult(existing)

    db.execute = AsyncMock(side_effect=_execute)

    payload_data = (
        "eyJlbWFpbEFkZHJlc3MiOiJvd25lckBleGFtcGxlLmNvbSIsImhpc3RvcnlJZCI6IjEyIn0="
    )
    with patch(
        "backend.modules.workforce.integrations.events.AuditRepository"
    ) as audit_repo:
        audit_repo.return_value.log = AsyncMock()
        ingested = await ExternalEventService(db).ingest_gmail_push(
            {
                "message": {
                    "messageId": "msg-1",
                    "data": payload_data,
                }
            }
        )

    assert len(ingested) == 1
    event, created = ingested[0]
    assert created is False
    assert event.id == "event-existing"
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_external_event_process_skips_already_processed_and_processing() -> None:
    processed = ExternalEvent(
        id="processed",
        owner_id="owner",
        provider="gmail",
        connector_installation_id="install-1",
        event_type="gmail.history_notification",
        dedupe_key="dedupe-processed",
        payload_json={},
        status="processed",
    )
    processing = ExternalEvent(
        id="processing",
        owner_id="owner",
        provider="gmail",
        connector_installation_id="install-1",
        event_type="gmail.history_notification",
        dedupe_key="dedupe-processing",
        payload_json={},
        status="processing",
    )
    db = AsyncMock()

    async def _execute(query):
        if "processed" in str(query):
            return _ScalarResult(processed)
        return _ScalarResult(processing)

    db.execute = AsyncMock(side_effect=_execute)
    service = ExternalEventService(db)
    service._process_gmail = AsyncMock()

    await service.process("processed")
    await service.process("processing")

    service._process_gmail.assert_not_awaited()


@pytest.mark.asyncio
async def test_gmail_send_rejects_unconsumed_approval() -> None:
    arguments, approval, installation, metadata = _send_arguments_and_approval(consumed=False)
    db = _ReplaySendDB(approval=approval, query_sequence=[])
    adapter = GmailAdapter(db, installation)

    with pytest.raises(GmailAPIError, match="Approval grant has not been consumed"):
        await adapter.send_draft_exactly_once(arguments)


@pytest.mark.asyncio
async def test_gmail_send_concurrent_claim_raises_without_provider_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    arguments, approval, installation, _metadata = _send_arguments_and_approval()
    db = _ReplaySendDB(approval=approval, query_sequence=[None])
    adapter = GmailAdapter(db, installation)

    async def fail_flush():
        raise IntegrityError("duplicate key", {}, Exception())

    db.flush = fail_flush  # type: ignore[method-assign]

    async def should_not_call(*_args, **_kwargs):
        raise AssertionError("Gmail provider must not be called on concurrent claim")

    monkeypatch.setattr(adapter, "request", should_not_call)
    with pytest.raises(GmailAPIError, match="Concurrent duplicate"):
        await adapter.send_draft_exactly_once(arguments)


@pytest.mark.asyncio
async def test_gmail_send_crash_after_provider_success_marks_outcome_unknown_without_resend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    arguments, approval, installation, metadata = _send_arguments_and_approval()
    in_flight = ExternalActionExecution(
        owner_id="owner",
        connector_installation_id="gmail-install",
        workflow_run_id="workflow-run",
        approval_request_id="approval-1",
        action_key="gmail.send_draft",
        idempotency_key="existing",
        arguments_hash=email_action_arguments_hash(arguments),
        status="sending",
    )
    db = _ReplaySendDB(approval=approval, query_sequence=[in_flight, metadata])
    adapter = GmailAdapter(db, installation)
    calls: list[tuple[str, str]] = []

    async def track_request(method: str, path: str, **_kwargs):
        calls.append((method, path))
        raise GmailAPIError("missing draft", status_code=404)

    monkeypatch.setattr(adapter, "request", track_request)
    with pytest.raises(GmailAPIError, match="manual reconciliation"):
        await adapter.send_draft_exactly_once(arguments)

    assert calls == [("GET", "/users/me/drafts/draft-1")]
    assert in_flight.status == "outcome_unknown"


@pytest.mark.asyncio
async def test_gmail_send_resumes_claimed_row_with_single_provider_post(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    arguments, approval, installation, metadata = _send_arguments_and_approval()
    claimed = ExternalActionExecution(
        owner_id="owner",
        connector_installation_id="gmail-install",
        workflow_run_id="workflow-run",
        approval_request_id="approval-1",
        action_key="gmail.send_draft",
        idempotency_key="existing",
        arguments_hash=email_action_arguments_hash(arguments),
        status="claimed",
    )
    original_thread = {
        "id": "thread-1",
        "messages": [{"id": "m1", "historyId": "1", "internalDate": "1"}],
    }
    db = _ReplaySendDB(
        approval=approval,
        query_sequence=[claimed, metadata],
    )
    adapter = GmailAdapter(db, installation)
    calls: list[tuple[str, str]] = []

    async def track_request(method: str, path: str, **_kwargs):
        calls.append((method, path))
        if method == "POST" and path.endswith("/drafts/send"):
            return {"id": "sent-message"}
        return original_thread

    monkeypatch.setattr(adapter, "request", track_request)
    monkeypatch.setattr(adapter, "execute", AsyncMock(return_value=original_thread))
    with patch("backend.modules.workforce.integrations.gmail.AuditRepository") as audit_repo:
        audit_repo.return_value.log = AsyncMock()
        result = await adapter.send_draft_exactly_once(arguments)

    assert result == {"id": "sent-message"}
    assert ("POST", "/users/me/drafts/send") in calls
    assert calls.count(("POST", "/users/me/drafts/send")) == 1
    assert claimed.status == "succeeded"


class _GithubHarness(OrchestrationGithubServiceMixin):
    def __init__(self, repo: MagicMock) -> None:
        self.db = MagicMock()
        self.repo = repo
        self.db.commit = AsyncMock()
        self.db.refresh = AsyncMock()
        self.db.get = AsyncMock()
        self.db.begin_nested = MagicMock()

    def _effective_github_outbound_comment_policy(self, _project, _repository):
        return "manual", []


@pytest.mark.asyncio
async def test_github_comment_approval_replay_returns_existing_approval() -> None:
    repo = MagicMock()
    existing_approval = ApprovalRequest(
        id="approval-existing",
        approval_type="github_comment",
        status="pending",
        requested_by_user_id="owner-1",
        payload_json={"body": "hello"},
    )
    issue_link = MagicMock(id="link-1", repository_id="repo-1", task_id="task-1")
    repo.get_issue_link = AsyncMock(return_value=issue_link)
    repo.get_github_outbound_dedup_row = AsyncMock(
        return_value=MagicMock(approval_id="approval-existing")
    )
    repo.create_approval = AsyncMock()
    harness = _GithubHarness(repo)
    harness.db.get = AsyncMock(
        side_effect=lambda model, _id: {
            "GithubRepository": MagicMock(connection_id="conn-1"),
            "OrchestratorTask": MagicMock(project_id="project-1", id="task-1"),
            "OrchestratorProject": MagicMock(settings_json={}),
            "ApprovalRequest": existing_approval,
        }.get(getattr(model, "__name__", str(model)))
    )

    user = User(id="owner-1", email="owner@example.com")
    approval = await harness.create_github_comment_approval(
        user,
        issue_link_id="link-1",
        body="hello",
        close_issue=False,
        idempotency_key="dedupe-key-1",
    )

    assert approval.id == "approval-existing"
    repo.create_approval.assert_not_awaited()


@pytest.mark.asyncio
async def test_github_post_approved_comment_skips_when_already_posted() -> None:
    repo = MagicMock()
    harness = _GithubHarness(repo)
    approval = ApprovalRequest(
        id="approval-1",
        approval_type="github_comment",
        status="approved",
        requested_by_user_id="owner-1",
        issue_link_id="link-1",
        payload_json={"body": "already posted", "posted_comment_id": 12345},
    )
    harness._github_request = AsyncMock()

    await harness._post_approved_github_comment(approval)

    harness._github_request.assert_not_awaited()


@pytest.mark.asyncio
async def test_telegram_approval_callback_replay_rejects_non_pending_approval() -> None:
    from backend.modules.workforce.integrations.telegram import TelegramWebhookService

    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(first=MagicMock(return_value=None)))
    service = TelegramWebhookService(db)

    with pytest.raises(ValueError, match="Unauthorized or unavailable approval"):
        await service._callback(
            {
                "id": "cb-1",
                "from": {"id": 99},
                "message": {"chat": {"id": 1}, "message_id": 10},
                "data": "approve:approval-1",
            }
        )

    db.execute.assert_awaited()
