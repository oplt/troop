"""Commit-time authorization: exact-effect validation, idempotency claim, receipts."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from backend.modules.audit.repository import AuditRepository
from backend.modules.orchestration.execution.hitl.approver_resolver import (
    ApproverEligibilityError,
    recheck_decided_approver_at_commit,
)
from backend.modules.orchestration.execution.hitl.exact_effect import (
    ExactEffectError,
    ProposedEffect,
    validate_committed_effect,
)
from backend.modules.orchestration.models import ApprovalRequest
from backend.modules.workforce.models import ExternalActionExecution


class CommitAuthorizationError(Exception):
    """Commit blocked before or during provider execution."""


@dataclass(frozen=True)
class CommitClaim:
    execution: ExternalActionExecution
    approval: ApprovalRequest
    effect: ProposedEffect
    replayed: bool = False


def build_idempotency_key(*parts: object) -> str:
    raw = ":".join(str(part) for part in parts if part is not None and str(part) != "")
    return hashlib.sha256(raw.encode()).hexdigest()


async def authorize_and_claim_execution(
    db: AsyncSession,
    *,
    owner_id: str,
    action_key: str,
    raw_arguments: dict[str, Any],
    approval_id: str,
    idempotency_key: str,
    arguments_hash: str,
    connector_installation_id: str | None = None,
    workflow_run_id: str | None = None,
    require_consumed: bool = False,
    precondition_fingerprint: str | None = None,
    require_approver: bool = False,
) -> CommitClaim:
    """Validate approved exact effect and claim a durable idempotency row."""
    approval = await db.get(ApprovalRequest, approval_id)
    if approval is None:
        raise CommitAuthorizationError("Approval request not found")
    if approval.status != "approved":
        raise CommitAuthorizationError(f"Approval status {approval.status!r} is not committable")
    if require_approver:
        if not approval.approved_by_user_id:
            raise CommitAuthorizationError("Approval requires an eligible approver decision")
        try:
            await recheck_decided_approver_at_commit(db, approval=approval)
        except ApproverEligibilityError as exc:
            raise CommitAuthorizationError(str(exc)) from exc

    try:
        effect = validate_committed_effect(
            approval,
            action_key=action_key,
            raw_arguments=raw_arguments,
            precondition_fingerprint=precondition_fingerprint,
            require_consumed=require_consumed,
            owner_id=owner_id,
            workflow_run_id=workflow_run_id,
        )
    except ExactEffectError as exc:
        raise CommitAuthorizationError(str(exc)) from exc

    result = await db.execute(
        select(ExternalActionExecution).where(
            ExternalActionExecution.idempotency_key == idempotency_key
        )
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        if existing.arguments_hash != arguments_hash:
            raise CommitAuthorizationError("Idempotency key was reused with different content")
        if existing.status == "succeeded":
            return CommitClaim(execution=existing, approval=approval, effect=effect, replayed=True)
        if existing.status in {"claimed", "sending", "retryable_failure"}:
            return CommitClaim(execution=existing, approval=approval, effect=effect)
        if existing.status in {"failed", "stale", "outcome_unknown"}:
            raise CommitAuthorizationError(
                existing.error or f"External action blocked in status {existing.status}"
            )
        raise CommitAuthorizationError(
            existing.error or f"External action blocked in status {existing.status}",
        )

    execution = ExternalActionExecution(
        owner_id=owner_id,
        connector_installation_id=connector_installation_id,
        workflow_run_id=workflow_run_id,
        approval_request_id=approval_id,
        action_key=action_key,
        idempotency_key=idempotency_key,
        arguments_hash=arguments_hash,
        status="claimed",
    )
    db.add(execution)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise CommitAuthorizationError("Concurrent duplicate external action blocked") from exc
    return CommitClaim(execution=execution, approval=approval, effect=effect)


async def mark_execution_sending(
    db: AsyncSession,
    execution: ExternalActionExecution,
    *,
    owner_id: str,
    audit_action: str,
    audit_metadata: dict[str, Any] | None = None,
) -> None:
    execution.status = "sending"
    await AuditRepository(db).log(
        audit_action,
        user_id=owner_id,
        resource_type="external_action_execution",
        resource_id=execution.id,
        metadata=audit_metadata or {},
    )
    await db.flush()


async def mark_execution_succeeded(
    db: AsyncSession,
    execution: ExternalActionExecution,
    *,
    owner_id: str,
    result_json: dict[str, Any],
    external_result_id: str | None = None,
    audit_action: str,
    audit_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    execution.status = "succeeded"
    execution.external_result_id = external_result_id
    execution.result_json = dict(result_json)
    execution.error = None
    await AuditRepository(db).log(
        audit_action,
        user_id=owner_id,
        resource_type="external_action_execution",
        resource_id=execution.id,
        metadata=audit_metadata or {},
    )
    from backend.modules.platform.activation_hooks import record_activation_for_owner

    await record_activation_for_owner(
        db,
        owner_id,
        "first_external_effect",
        at=execution.created_at,
        resource_type="external_action_execution",
        resource_id=execution.id,
        metadata={
            "action_key": execution.action_key,
            "external_result_id": external_result_id,
        },
    )
    await db.flush()
    return dict(result_json)


async def mark_execution_failed(
    db: AsyncSession,
    execution: ExternalActionExecution,
    *,
    owner_id: str,
    error: str,
    retryable: bool = False,
    audit_action: str | None = None,
    audit_metadata: dict[str, Any] | None = None,
) -> None:
    execution.status = "retryable_failure" if retryable else "failed"
    execution.error = error
    if audit_action:
        await AuditRepository(db).log(
            audit_action,
            user_id=owner_id,
            resource_type="external_action_execution",
            resource_id=execution.id,
            metadata={"retryable": retryable, **(audit_metadata or {})},
        )
    await db.flush()


async def mark_execution_stale(
    db: AsyncSession,
    execution: ExternalActionExecution,
    approval: ApprovalRequest,
    *,
    error: str,
) -> None:
    execution.status = "stale"
    execution.error = error
    approval.status = "stale"
    approval.reason = error
    payload = dict(approval.payload_json or {})
    payload["stale_reason"] = error
    approval.payload_json = payload
    flag_modified(approval, "payload_json")
    await db.flush()


async def mark_execution_outcome_unknown(
    db: AsyncSession,
    execution: ExternalActionExecution,
    *,
    error: str,
) -> None:
    execution.status = "outcome_unknown"
    execution.error = error
    await db.flush()
