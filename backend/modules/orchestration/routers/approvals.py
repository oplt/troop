from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_current_user
from backend.api.deps.orchestration import get_approvals_service
from backend.core.config import settings
from backend.core.error_payloads import error_payload
from backend.core.logging import get_logger
from backend.core.pagination import build_cursor_page, token_from_created_at_id
from backend.core.schemas import CursorPageResponse, RequestModel
from backend.db.session import get_db
from backend.modules.identity_access.models import User
from backend.modules.orchestration._helpers import resolve_query_limit
from backend.modules.orchestration.hitl_policy import redact_approval_payload
from backend.modules.orchestration.presenters import to_approval_list_item
from backend.modules.orchestration.schemas import (
    ApprovalDecision,
    ApprovalListItem,
    ApprovalResponse,
)
from backend.modules.orchestration.services.approvals_domain import ApprovalsService

logger = get_logger(__name__)

router = APIRouter()


class EmailApprovalEditRequest(RequestModel):
    subject: str = Field(max_length=998)
    body_text: str = Field(min_length=1, max_length=100_000)
    to: list[str] = Field(default_factory=list, max_length=100)
    cc: list[str] = Field(default_factory=list, max_length=100)
    bcc: list[str] = Field(default_factory=list, max_length=100)


class ApprovalChangesRequest(RequestModel):
    reason: str = Field(min_length=1, max_length=2_000)


class ApprovalDelegateRequest(RequestModel):
    to_user_id: str = Field(min_length=1, max_length=128)
    reason: str | None = Field(default=None, max_length=2_000)


def _approval_response(item) -> ApprovalResponse:
    return ApprovalResponse(
        id=item.id,
        project_id=item.project_id,
        task_id=item.task_id,
        run_id=item.run_id,
        issue_link_id=item.issue_link_id,
        requested_by_user_id=item.requested_by_user_id,
        approved_by_user_id=item.approved_by_user_id,
        approval_type=item.approval_type,
        status=item.status,
        reason=item.reason,
        payload=redact_approval_payload(item.payload_json),
        effect_hash=item.effect_hash,
        effect_version=item.effect_version or 1,
        precondition_fingerprint=item.precondition_fingerprint,
        expires_at=item.expires_at,
        proposed_effect=item.proposed_effect_json,
        workspace_id=item.workspace_id,
        eligible_approvers=list(item.eligible_approvers_json or []),
        routing_snapshot=dict(item.routing_snapshot_json or {}),
        decided_eligibility_reason=item.decided_eligibility_reason,
        due_at=item.due_at,
        sla_policy=dict(item.sla_policy_json or {}),
        delegations=list(item.delegations_json or []),
        escalation_state=dict(item.escalation_state_json or {}),
        created_at=item.created_at,
        resolved_at=item.resolved_at,
    )


@router.get("/approvals", response_model=CursorPageResponse[ApprovalListItem])
async def list_approvals(
    limit: int = Query(
        settings.APPROVALS_LIST_DEFAULT_LIMIT,
        ge=1,
        le=settings.APPROVALS_LIST_MAX_LIMIT,
    ),
    cursor_created_at: datetime | None = Query(default=None),
    cursor_id: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    service: ApprovalsService = Depends(get_approvals_service),
):
    effective_limit = resolve_query_limit(
        limit,
        default=settings.APPROVALS_LIST_DEFAULT_LIMIT,
        maximum=settings.APPROVALS_LIST_MAX_LIMIT,
    )
    rows = await service.list_approvals(
        current_user,
        limit=effective_limit,
        cursor_created_at=cursor_created_at,
        cursor_id=cursor_id,
    )
    page, next_cursor = build_cursor_page(
        rows,
        effective_limit,
        token_from_row=token_from_created_at_id,
    )
    return CursorPageResponse(
        items=[to_approval_list_item(item) for item in page],
        next_cursor=next_cursor,
    )


@router.post("/approvals/{approval_id}", response_model=ApprovalResponse)
async def decide_approval(
    approval_id: str,
    payload: ApprovalDecision,
    current_user: User = Depends(get_current_user),
    service: ApprovalsService = Depends(get_approvals_service),
):
    approval = await service.decide_approval(
        current_user,
        approval_id,
        payload.status,
        payload.reason,
    )
    return _approval_response(approval)


@router.patch("/approvals/{approval_id}/payload", response_model=ApprovalResponse)
async def edit_email_approval(
    approval_id: str,
    payload: EmailApprovalEditRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from backend.modules.workforce.integrations.approval_edit import (
        replace_email_approval_draft,
    )

    try:
        approval = await replace_email_approval_draft(
            db,
            owner_id=current_user.id,
            approval_id=approval_id,
            changes=payload.model_dump(),
        )
    except ValueError as exc:
        logger.warning(
            "email_approval_edit_rejected approval_id=%s user_id=%s detail=%s",
            approval_id,
            current_user.id,
            str(exc)[:300],
        )
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=error_payload(
                code="APPROVAL_EDIT_CONFLICT",
                message="Approval cannot be edited in its current state",
            ),
        ) from exc
    return _approval_response(approval)


@router.post("/approvals/{approval_id}/request-changes", response_model=ApprovalResponse)
async def request_approval_changes(
    approval_id: str,
    payload: ApprovalChangesRequest,
    current_user: User = Depends(get_current_user),
    service: ApprovalsService = Depends(get_approvals_service),
):
    approval = await service.decide_approval(
        current_user,
        approval_id,
        "rejected",
        f"Changes requested: {payload.reason.strip()}",
    )
    return _approval_response(approval)


@router.post("/approvals/{approval_id}/delegate", response_model=ApprovalResponse)
async def delegate_approval(
    approval_id: str,
    payload: ApprovalDelegateRequest,
    current_user: User = Depends(get_current_user),
    service: ApprovalsService = Depends(get_approvals_service),
):
    approval = await service.delegate_approval(
        current_user,
        approval_id,
        payload.to_user_id,
        payload.reason,
    )
    return _approval_response(approval)


@router.get("/approvals/pending-count")
async def pending_approvals_count(
    current_user: User = Depends(get_current_user),
    service: ApprovalsService = Depends(get_approvals_service),
):
    return {"count": await service.get_pending_approvals_count(current_user)}
