from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_current_user
from backend.api.deps.orchestration import get_approvals_service
from backend.core.schemas import RequestModel
from backend.db.session import get_db
from backend.modules.identity_access.models import User
from backend.modules.orchestration.hitl_policy import redact_approval_payload
from backend.modules.orchestration.schemas import ApprovalDecision, ApprovalResponse
from backend.modules.orchestration.services.approvals_domain import ApprovalsService

router = APIRouter()


class EmailApprovalEditRequest(RequestModel):
    subject: str = Field(max_length=998)
    body_text: str = Field(min_length=1, max_length=100_000)
    to: list[str] = Field(default_factory=list, max_length=100)
    cc: list[str] = Field(default_factory=list, max_length=100)
    bcc: list[str] = Field(default_factory=list, max_length=100)


class ApprovalChangesRequest(RequestModel):
    reason: str = Field(min_length=1, max_length=2_000)


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
        created_at=item.created_at,
        resolved_at=item.resolved_at,
    )


@router.get("/approvals", response_model=list[ApprovalResponse])
async def list_approvals(
    current_user: User = Depends(get_current_user),
    service: ApprovalsService = Depends(get_approvals_service),
):
    return [_approval_response(item) for item in await service.list_approvals(current_user)]


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
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
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


@router.get("/approvals/pending-count")
async def pending_approvals_count(
    current_user: User = Depends(get_current_user),
    service: ApprovalsService = Depends(get_approvals_service),
):
    return {"count": await service.get_pending_approvals_count(current_user)}
