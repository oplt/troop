"""Shared exact-effect approval creation helpers."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.orchestration.execution.hitl.approver_resolver import (
    snapshot_routing_on_approval,
)
from backend.modules.orchestration.execution.hitl.exact_effect import (
    ProposedEffect,
    apply_proposed_effect_to_approval,
    build_proposed_effect,
)
from backend.modules.orchestration.models import ApprovalRequest


async def create_exact_effect_approval(
    db: AsyncSession,
    *,
    project_id: str | None,
    task_id: str | None,
    run_id: str | None,
    issue_link_id: str | None,
    requested_by_user_id: str | None,
    approval_type: str,
    action_key: str,
    raw_arguments: dict[str, Any] | None,
    reason: str | None = None,
    precondition_fingerprint: str | None = None,
    effect_version: int = 1,
    extra_payload: dict[str, Any] | None = None,
) -> ApprovalRequest:
    """Create an ApprovalRequest with canonical exact-effect binding."""
    effect = build_proposed_effect(
        action_key=action_key,
        raw_arguments=raw_arguments,
        precondition_fingerprint=precondition_fingerprint,
        effect_version=effect_version,
    )
    payload: dict[str, Any] = dict(extra_payload or {})
    payload.setdefault("owner_id", requested_by_user_id)
    if raw_arguments and "draft_arguments" not in payload:
        payload["draft_arguments"] = dict(raw_arguments)

    approval = ApprovalRequest(
        id=str(uuid4()),
        project_id=project_id,
        task_id=task_id,
        run_id=run_id,
        issue_link_id=issue_link_id,
        requested_by_user_id=requested_by_user_id,
        approval_type=approval_type,
        status="pending",
        reason=reason,
        payload_json=payload,
    )
    apply_proposed_effect_to_approval(approval, effect)
    if payload.get("draft_arguments"):
        merged = dict(approval.payload_json or {})
        merged["draft_arguments"] = dict(payload["draft_arguments"])
        approval.payload_json = merged
    db.add(approval)
    await db.flush()
    await snapshot_routing_on_approval(db, approval)
    await db.flush()
    return approval


def proposed_effect_summary(effect: ProposedEffect) -> dict[str, Any]:
    return {
        "action_key": effect.action_key,
        "effect_hash": effect.effect_hash,
        "effect_version": effect.effect_version,
        "precondition_fingerprint": effect.precondition_fingerprint,
        "expires_at": effect.expires_at.isoformat() if effect.expires_at else None,
        "proposed_effect": dict(effect.normalized_effect),
        "replaces_approval_id": effect.replaces_approval_id,
    }
