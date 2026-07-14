from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.modules.github.service import OrchestrationGithubServiceMixin


class _GithubHarness(OrchestrationGithubServiceMixin):
    def __init__(self, repo: MagicMock) -> None:
        self.db = MagicMock()
        self.repo = repo
        self.db.commit = AsyncMock()


def _sign(body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def test_validate_github_webhook_signature_accepts_valid_hmac():
    secret = "whsec-test"
    body = b'{"action":"opened","repository":{"full_name":"acme/app"}}'
    harness = _GithubHarness(MagicMock())
    with patch("backend.modules.github.service.settings.GITHUB_APP_WEBHOOK_SECRET", secret):
        assert harness.validate_github_webhook_signature(body, _sign(body, secret)) is True


def test_validate_github_webhook_signature_rejects_invalid_signature():
    secret = "whsec-test"
    body = b'{"action":"opened"}'
    harness = _GithubHarness(MagicMock())
    with patch("backend.modules.github.service.settings.GITHUB_APP_WEBHOOK_SECRET", secret):
        assert harness.validate_github_webhook_signature(body, "sha256=deadbeef") is False
        assert harness.validate_github_webhook_signature(body, None) is False


@pytest.mark.asyncio
async def test_record_github_webhook_event_is_idempotent_by_delivery_id():
    repo = MagicMock()
    existing = MagicMock(
        id="sync-existing",
        action="webhook.issues.opened",
        status="queued",
        payload_json={"_webhook_meta": {"delivery_id": "delivery-1"}},
    )
    repo.get_sync_event_by_delivery_id = AsyncMock(return_value=existing)
    repo.create_sync_event = AsyncMock()
    harness = _GithubHarness(repo)

    payload = {"action": "opened", "repository": {"full_name": "acme/app"}}
    with patch("backend.modules.github.service.GITHUB_WEBHOOK_EVENT_ALLOWLIST", {"issues"}):
        sync_id = await harness.record_github_webhook_event(
            "issues",
            payload,
            delivery_id="delivery-1",
        )

    assert sync_id == "sync-existing"
    repo.create_sync_event.assert_not_awaited()
    repo.get_sync_event_by_delivery_id.assert_awaited_once_with("delivery-1")


@pytest.mark.asyncio
async def test_record_github_webhook_event_creates_new_delivery():
    repo = MagicMock()
    repo.get_sync_event_by_delivery_id = AsyncMock(return_value=None)
    repo.get_github_repository_by_full_name = AsyncMock(return_value=None)
    created = MagicMock(id="sync-new")
    repo.create_sync_event = AsyncMock(return_value=created)
    harness = _GithubHarness(repo)

    payload = {"action": "opened", "repository": {"full_name": "acme/app"}}
    with patch("backend.modules.github.service.GITHUB_WEBHOOK_EVENT_ALLOWLIST", {"issues"}):
        sync_id = await harness.record_github_webhook_event(
            "issues",
            payload,
            delivery_id="delivery-2",
        )

    assert sync_id == "sync-new"
    repo.create_sync_event.assert_awaited_once()


@pytest.mark.asyncio
async def test_issue_comment_webhook_replay_does_not_duplicate_task_thread_comment():
    repo = MagicMock()
    repository = MagicMock(id="repo-1", connection_id="conn-1", full_name="acme/app")
    link = MagicMock(id="link-1", task_id="task-1")
    connection = MagicMock(owner_id="owner-1")
    repo.get_issue_link_by_repo_and_number = AsyncMock(return_value=link)
    repo.get_github_entity_mapping_by_external = AsyncMock(return_value=MagicMock(id="mapping-1"))
    repo.create_task_comment = AsyncMock()
    harness = _GithubHarness(repo)
    harness.db.get = AsyncMock(return_value=connection)
    harness._ensure_repository_from_webhook_payload = AsyncMock(return_value=repository)
    sync_event = MagicMock()

    await harness._process_webhook_issue_comment(
        sync_event,
        {
            "issue": {"number": 7},
            "comment": {"id": 99, "body": "same delivery", "user": {"login": "octocat"}},
        },
    )

    repo.create_task_comment.assert_not_awaited()
    assert sync_event.issue_link_id == "link-1"
    assert sync_event.status == "completed"
    assert "already mirrored" in sync_event.detail


@pytest.mark.asyncio
async def test_pull_request_resolves_to_issue_from_closing_keyword():
    repo = MagicMock()
    expected = MagicMock(repository_id="repo-1", issue_number=42)
    repo.get_issue_link_by_repo_and_number = AsyncMock(
        side_effect=lambda _repo_id, number: expected if number == 42 else None
    )
    harness = _GithubHarness(repo)
    repository = MagicMock(id="repo-1")

    resolved = await harness._resolve_issue_link_for_pull_request(
        repository,
        {"number": 100, "body": "Closes #42", "head": {"ref": "feature/a"}},
    )

    assert resolved is expected
