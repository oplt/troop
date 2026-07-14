from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.api.deps.auth import get_current_user
from backend.api.deps.orchestration import get_approvals_service
from backend.modules.identity_access.models import User
from backend.modules.orchestration.hitl_policy import redact_approval_payload
from backend.modules.orchestration.schemas import ApprovalDecision, ApprovalResponse
from backend.modules.orchestration.services.approvals_domain import ApprovalsService

router = APIRouter()


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


@router.get("/approvals/pending-count")
async def pending_approvals_count(
    current_user: User = Depends(get_current_user),
    service: ApprovalsService = Depends(get_approvals_service),
):
    return {"count": await service.get_pending_approvals_count(current_user)}
