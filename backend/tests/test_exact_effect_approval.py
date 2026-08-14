"""Tests for canonical exact-effect approval bindings."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.modules.orchestration.execution.hitl.exact_effect import (
    ExactEffectError,
    apply_proposed_effect_to_approval,
    build_proposed_effect,
    create_replacement_approval,
    is_approval_expired,
    normalize_proposed_effect,
    read_proposed_effect,
    validate_committed_effect,
)
from backend.modules.orchestration.models import ApprovalRequest
from backend.modules.orchestration.tool_execution_context import arguments_hash
from backend.modules.workforce.integrations.email import email_action_arguments_hash


def _gmail_arguments(**overrides: object) -> dict:
    base = {
        "connector_installation_id": "gmail-install",
        "gmail_draft_id": "draft-1",
        "thread_id": "thread-1",
        "to": [{"email": "customer@example.com"}],
        "cc": [],
        "bcc": [],
        "subject": "Re: question",
        "body": "Approved exact body",
    }
    base.update(overrides)
    return base


def test_normalize_gmail_effect_is_deterministic() -> None:
    raw = _gmail_arguments(to=[{"email": "Customer@Example.com"}])
    normalized = normalize_proposed_effect("gmail.send_draft", raw)
    assert normalized["to"] == ["customer@example.com"]
    assert email_action_arguments_hash(raw) == build_proposed_effect(
        action_key="gmail.send_draft",
        raw_arguments=raw,
    ).effect_hash


def test_apply_and_read_proposed_effect_round_trip() -> None:
    effect = build_proposed_effect(
        action_key="tool:gmail.send_draft",
        raw_arguments=_gmail_arguments(),
        precondition_fingerprint="thread-fp",
        effect_version=2,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    approval = ApprovalRequest(
        approval_type="tool:gmail.send_draft",
        status="pending",
        payload_json={"workflow_run_id": "run-1"},
    )
    apply_proposed_effect_to_approval(approval, effect)
    bound = read_proposed_effect(approval)
    assert bound is not None
    assert bound.action_key == "gmail.send_draft"
    assert bound.effect_hash == effect.effect_hash
    assert bound.effect_version == 2
    assert bound.precondition_fingerprint == "thread-fp"


def test_validate_committed_effect_requires_exact_hash() -> None:
    arguments = _gmail_arguments()
    effect = build_proposed_effect(action_key="gmail.send_draft", raw_arguments=arguments)
    approval = ApprovalRequest(
        approval_type="tool:gmail.send_draft",
        status="approved",
        requested_by_user_id="owner",
        payload_json={
            "owner_id": "owner",
            "workflow_run_id": "run-1",
            "_consumed_at": datetime.now(UTC).isoformat(),
        },
    )
    apply_proposed_effect_to_approval(approval, effect)
    validate_committed_effect(
        approval,
        action_key="gmail.send_draft",
        raw_arguments=arguments,
        require_consumed=True,
        owner_id="owner",
        workflow_run_id="run-1",
    )
    with pytest.raises(ExactEffectError, match="effect hash"):
        validate_committed_effect(
            approval,
            action_key="gmail.send_draft",
            raw_arguments=_gmail_arguments(body="Different body"),
            require_consumed=True,
            owner_id="owner",
            workflow_run_id="run-1",
        )


def test_validate_committed_effect_rejects_precondition_drift() -> None:
    effect = build_proposed_effect(
        action_key="gmail.send_draft",
        raw_arguments=_gmail_arguments(),
        precondition_fingerprint="fp-original",
    )
    approval = ApprovalRequest(
        approval_type="tool:gmail.send_draft",
        status="approved",
        payload_json={"_consumed_at": datetime.now(UTC).isoformat()},
    )
    apply_proposed_effect_to_approval(approval, effect)
    with pytest.raises(ExactEffectError, match="precondition"):
        validate_committed_effect(
            approval,
            action_key="gmail.send_draft",
            raw_arguments=_gmail_arguments(),
            precondition_fingerprint="fp-changed",
            require_consumed=True,
        )


def test_is_approval_expired() -> None:
    effect = build_proposed_effect(
        action_key="gmail.send_draft",
        raw_arguments=_gmail_arguments(),
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    approval = ApprovalRequest(approval_type="tool:gmail.send_draft", status="approved")
    apply_proposed_effect_to_approval(approval, effect)
    assert is_approval_expired(approval) is True


@pytest.mark.asyncio
async def test_create_replacement_approval_increments_version() -> None:
    class _DB:
        def add(self, _item):
            return None

    original = ApprovalRequest(
        id="approval-1",
        approval_type="tool:gmail.send_draft",
        status="pending",
        payload_json={"workflow_run_id": "run-1", "draft_arguments": _gmail_arguments()},
    )
    original_effect = build_proposed_effect(
        action_key="gmail.send_draft",
        raw_arguments=_gmail_arguments(),
        effect_version=1,
    )
    apply_proposed_effect_to_approval(original, original_effect)

    revised = build_proposed_effect(
        action_key="gmail.send_draft",
        raw_arguments=_gmail_arguments(body="Edited body"),
        effect_version=2,
    )
    replacement = create_replacement_approval(
        _DB(),  # type: ignore[arg-type]
        approval=original,
        effect=revised,
        owner_id="owner",
    )
    assert original.status == "invalidated"
    assert replacement.status == "pending"
    assert replacement.effect_version == 2
    assert replacement.effect_hash == revised.effect_hash
    assert replacement.effect_hash != original.effect_hash
    assert read_proposed_effect(replacement).replaces_approval_id == "approval-1"


def test_read_proposed_effect_legacy_payload_fallback() -> None:
    arguments = _gmail_arguments()
    approval = ApprovalRequest(
        approval_type="tool:gmail.send_draft",
        status="pending",
        payload_json={
            "action_key": "gmail.send_draft",
            "arguments_hash": arguments_hash(arguments),
            "draft_arguments": arguments,
        },
    )
    bound = read_proposed_effect(approval)
    assert bound is not None
    assert bound.effect_hash == email_action_arguments_hash(arguments)
