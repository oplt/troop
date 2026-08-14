"""Tests for shared commit-time authorization."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.modules.github.commit_checks import github_issue_precondition_fingerprint
from backend.modules.github.models import GithubIssueLink
from backend.modules.github.service import OrchestrationGithubServiceMixin
from backend.modules.orchestration.execution.hitl.commit_authorization import (
    CommitAuthorizationError,
    authorize_and_claim_execution,
    build_idempotency_key,
)
from backend.modules.orchestration.execution.hitl.exact_effect import (
    apply_proposed_effect_to_approval,
    build_proposed_effect,
)
from backend.modules.orchestration.models import ApprovalRequest
from backend.modules.workforce.models import ExternalActionExecution


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _CommitDB:
    def __init__(self, *, approval: ApprovalRequest, execution: ExternalActionExecution | None):
        self.approval = approval
        self.execution = execution
        self.added: list[object] = []

    async def get(self, model, object_id):
        if model is ApprovalRequest and object_id == self.approval.id:
            return self.approval
        return None

    async def execute(self, _query):
        return _ScalarResult(self.execution)

    def add(self, item):
        self.added.append(item)

    async def flush(self):
        return None

    async def rollback(self):
        return None


@pytest.mark.asyncio
async def test_authorize_and_claim_creates_execution_row(monkeypatch) -> None:
    from backend.modules.orchestration.execution.hitl.approver_resolver import EligibleApprover

    async def _allow_recheck(*_args, **_kwargs):
        return EligibleApprover(user_id="owner", role="owner", reasons=("project_owner",))

    monkeypatch.setattr(
        "backend.modules.orchestration.execution.hitl.commit_authorization.recheck_decided_approver_at_commit",
        _allow_recheck,
    )
    arguments = {
        "issue_link_id": "link-1",
        "repository_id": "repo-1",
        "issue_number": 7,
        "body": "Ship it",
        "close_issue": False,
    }
    effect = build_proposed_effect(action_key="github_comment", raw_arguments=arguments)
    approval = ApprovalRequest(
        id="approval-1",
        approval_type="github_comment",
        status="approved",
        approved_by_user_id="owner",
        requested_by_user_id="owner",
        issue_link_id="link-1",
        payload_json={"body": "Ship it", "close_issue": False},
    )
    apply_proposed_effect_to_approval(approval, effect)
    db = _CommitDB(approval=approval, execution=None)
    claim = await authorize_and_claim_execution(
        db,
        owner_id="owner",
        action_key="github_comment",
        raw_arguments=arguments,
        approval_id=approval.id,
        idempotency_key=build_idempotency_key("github_comment", approval.id, "link-1"),
        arguments_hash=effect.effect_hash,
        require_approver=True,
    )
    assert claim.replayed is False
    assert len(db.added) == 1
    assert isinstance(db.added[0], ExternalActionExecution)
    assert db.added[0].status == "claimed"


@pytest.mark.asyncio
async def test_authorize_and_claim_rejects_missing_approver() -> None:
    arguments = {"body": "hello", "close_issue": False, "issue_link_id": "link-1"}
    effect = build_proposed_effect(action_key="github_comment", raw_arguments=arguments)
    approval = ApprovalRequest(
        id="approval-1",
        approval_type="github_comment",
        status="approved",
        issue_link_id="link-1",
        payload_json={"body": "hello"},
    )
    apply_proposed_effect_to_approval(approval, effect)
    db = _CommitDB(approval=approval, execution=None)
    with pytest.raises(CommitAuthorizationError, match="eligible approver"):
        await authorize_and_claim_execution(
            db,
            owner_id="owner",
            action_key="github_comment",
            raw_arguments=arguments,
            approval_id=approval.id,
            idempotency_key="key",
            arguments_hash=effect.effect_hash,
            require_approver=True,
        )


def test_github_issue_precondition_fingerprint_changes_with_state() -> None:
    link = GithubIssueLink(
        id="link-1",
        repository_id="repo-1",
        issue_number=3,
        title="Bug",
        state="open",
        last_synced_at=datetime.now(UTC),
    )
    original = github_issue_precondition_fingerprint(link)
    link.state = "closed"
    assert github_issue_precondition_fingerprint(link) != original


class _GithubPostHarness(OrchestrationGithubServiceMixin):
    def __init__(self) -> None:
        self.db = AsyncMock()
        self.repo = MagicMock()


@pytest.mark.asyncio
async def test_post_approved_github_comment_uses_durable_receipt(monkeypatch) -> None:
    from backend.modules.orchestration.execution.hitl.approver_resolver import EligibleApprover

    async def _allow_recheck(*_args, **_kwargs):
        return EligibleApprover(user_id="owner-1", role="owner", reasons=("project_owner",))

    monkeypatch.setattr(
        "backend.modules.orchestration.execution.hitl.commit_authorization.recheck_decided_approver_at_commit",
        _allow_recheck,
    )
    issue_link = GithubIssueLink(
        id="link-1",
        repository_id="repo-1",
        issue_number=9,
        title="Task",
        state="open",
        last_synced_at=datetime.now(UTC),
    )
    repository = MagicMock(id="repo-1", connection_id="conn-1", full_name="acme/repo")
    connection = MagicMock(owner_id="owner-1")
    approval = ApprovalRequest(
        id="approval-1",
        approval_type="github_comment",
        status="approved",
        approved_by_user_id="owner-1",
        requested_by_user_id="owner-1",
        issue_link_id="link-1",
        payload_json={
            "body": "Ready to merge",
            "close_issue": False,
            "issue_link_id": "link-1",
            "repository_id": "repo-1",
            "issue_number": 9,
        },
    )
    effect = build_proposed_effect(
        action_key="github_comment",
        raw_arguments={
            "issue_link_id": "link-1",
            "repository_id": "repo-1",
            "issue_number": 9,
            "body": "Ready to merge",
            "close_issue": False,
        },
        precondition_fingerprint=github_issue_precondition_fingerprint(issue_link),
    )
    apply_proposed_effect_to_approval(approval, effect)

    harness = _GithubPostHarness()
    harness.repo.resolve_authorized_issue_link = AsyncMock(return_value=issue_link)
    harness.repo.resolve_authorized_repository = AsyncMock(return_value=repository)
    harness.db.get = AsyncMock(
        side_effect=lambda model, object_id: (
            approval
            if model is ApprovalRequest and object_id == approval.id
            else connection
            if getattr(model, "__name__", "") == "GithubConnection"
            else None
        )
    )
    harness.db.execute = AsyncMock(return_value=_ScalarResult(None))
    harness.db.add = MagicMock()
    harness.db.flush = AsyncMock()
    harness._github_request = AsyncMock(
        return_value=MagicMock(
            status_code=201,
            json=lambda: {"id": 999, "html_url": "https://github.com/acme/repo/issues/9#issuecomment-999"},
        )
    )
    harness.repo.create_sync_event = AsyncMock()

    await harness._post_approved_github_comment(approval)

    harness._github_request.assert_awaited_once()
    assert any(
        isinstance(call.args[0], ExternalActionExecution)
        for call in harness.db.add.call_args_list
    )
    assert approval.payload_json["posted_comment_id"] == 999
