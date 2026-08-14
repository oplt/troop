"""Tests for approval SLA, delegation, and escalation (HITL-002B)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy import delete

from backend.db.session import SessionLocal
from backend.modules.identity_access.models import User, WorkspaceMembership
from backend.modules.identity_access.workspace_authorization import WorkspaceAuthorizationService
from backend.modules.identity_access.workspace_roles import (
    WORKSPACE_ROLE_APPROVER,
    WORKSPACE_ROLE_OPERATOR,
)
from backend.modules.orchestration.execution.hitl.approval_delegation import (
    ApprovalDelegationError,
    delegate_approval,
    delegation_constraints,
)
from backend.modules.orchestration.execution.hitl.approval_sla import (
    compute_approval_due_at,
    normalize_approval_sla_policy,
    scan_pending_approval_sla,
)
from backend.modules.orchestration.execution.hitl.approver_resolver import (
    ApproverEligibilityError,
    recheck_user_eligible,
    resolve_eligible_approvers,
    snapshot_routing_on_approval,
)
from backend.modules.orchestration.execution.hitl.exact_effect import (
    apply_proposed_effect_to_approval,
    build_proposed_effect,
    is_approval_expired,
)
from backend.modules.orchestration.models import ApprovalRequest
from backend.modules.orchestration.repository import OrchestrationRepository
from backend.modules.orchestration.services.approvals_service import (
    OrchestrationApprovalsServiceMixin,
)
from backend.modules.projects.orchestration_models import OrchestratorProject


async def _ensure_workspace(user: User):
    async with SessionLocal() as db:
        auth = WorkspaceAuthorizationService(db)
        ctx = await auth.resolve_active_workspace(user)
        await db.commit()
        return ctx.workspace


async def _add_workspace_member(*, workspace_id: str, user_id: str, role: str) -> None:
    async with SessionLocal() as db:
        db.add(WorkspaceMembership(workspace_id=workspace_id, user_id=user_id, role=role))
        await db.commit()


async def _create_project(owner_id: str) -> OrchestratorProject:
    suffix = uuid.uuid4().hex[:8]
    async with SessionLocal() as db:
        repo = OrchestrationRepository(db)
        project = await repo.create_project(
            owner_id=owner_id,
            name=f"Approval SLA test {suffix}",
            slug=f"approval-sla-{suffix}",
        )
        await db.commit()
        await db.refresh(project)
        return project


async def _cleanup_project(project_id: str) -> None:
    async with SessionLocal() as db:
        await db.execute(delete(OrchestratorProject).where(OrchestratorProject.id == project_id))
        await db.commit()


def test_normalize_approval_sla_policy_defaults() -> None:
    policy = normalize_approval_sla_policy(None)
    assert policy["response_hours"] == 24
    assert policy["escalation_roles"] == ["admin", "owner"]


def test_compute_approval_due_at() -> None:
    created = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
    due = compute_approval_due_at(
        created_at=created,
        sla_policy=normalize_approval_sla_policy({"response_hours": 6}),
    )
    assert due == created + timedelta(hours=6)


def test_delegation_constraints_remove_delegator() -> None:
    delegated_away, targets = delegation_constraints(
        [
            {
                "from_user_id": "owner",
                "to_user_id": "delegate",
                "active": True,
            }
        ]
    )
    assert delegated_away == {"owner"}
    assert targets == {"delegate": "owner"}


@pytest.mark.asyncio
@pytest.mark.integration
async def test_delegate_approval_adds_delegatee_and_removes_delegator(
    tenant_pair: tuple[User, User],
) -> None:
    owner, delegate_user = tenant_pair
    workspace = await _ensure_workspace(owner)
    await _ensure_workspace(delegate_user)
    await _add_workspace_member(
        workspace_id=workspace.id,
        user_id=delegate_user.id,
        role=WORKSPACE_ROLE_APPROVER,
    )
    project = await _create_project(owner.id)

    try:
        async with SessionLocal() as db:
            approval = ApprovalRequest(
                id=str(uuid.uuid4()),
                project_id=project.id,
                requested_by_user_id=owner.id,
                approval_type="task_mark_complete",
                status="pending",
                payload_json={"to_status": "completed"},
                created_at=datetime.now(UTC),
            )
            await snapshot_routing_on_approval(db, approval)
            approval = await delegate_approval(
                db,
                approval=approval,
                from_user_id=owner.id,
                to_user_id=delegate_user.id,
                reason="Out of office",
            )

        eligible_ids = {row["user_id"] for row in (approval.eligible_approvers_json or [])}
        assert delegate_user.id in eligible_ids
        assert owner.id not in eligible_ids
        assert any(
            "delegated_from:" in reason
            for row in approval.eligible_approvers_json or []
            for reason in row.get("reasons") or []
            if row.get("user_id") == delegate_user.id
        )
    finally:
        await _cleanup_project(project.id)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_delegatee_blocked_after_role_removal(tenant_pair: tuple[User, User]) -> None:
    owner, delegate_user = tenant_pair
    workspace = await _ensure_workspace(owner)
    await _ensure_workspace(delegate_user)
    membership = WorkspaceMembership(
        workspace_id=workspace.id,
        user_id=delegate_user.id,
        role=WORKSPACE_ROLE_APPROVER,
    )
    async with SessionLocal() as db:
        db.add(membership)
        await db.commit()
        membership_id = membership.id

    project = await _create_project(owner.id)
    try:
        async with SessionLocal() as db:
            approval = ApprovalRequest(
                id=str(uuid.uuid4()),
                project_id=project.id,
                requested_by_user_id=owner.id,
                approval_type="workflow_tool",
                status="pending",
                payload_json={},
                created_at=datetime.now(UTC),
            )
            await snapshot_routing_on_approval(db, approval)
            approval = await delegate_approval(
                db,
                approval=approval,
                from_user_id=owner.id,
                to_user_id=delegate_user.id,
                reason="Covering",
            )

        async with SessionLocal() as db2:
            await db2.execute(
                delete(WorkspaceMembership).where(WorkspaceMembership.id == membership_id)
            )
            await db2.commit()

        async with SessionLocal() as db:
            with pytest.raises(ApproverEligibilityError):
                await recheck_user_eligible(
                    db,
                    approval=approval,
                    user_id=delegate_user.id,
                )
    finally:
        await _cleanup_project(project.id)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_escalation_expands_eligible_roles(tenant_pair: tuple[User, User]) -> None:
    owner, operator_user = tenant_pair
    workspace = await _ensure_workspace(owner)
    await _ensure_workspace(operator_user)
    await _add_workspace_member(
        workspace_id=workspace.id,
        user_id=operator_user.id,
        role=WORKSPACE_ROLE_OPERATOR,
    )
    project = await _create_project(owner.id)

    try:
        async with SessionLocal() as db:
            approval = ApprovalRequest(
                id=str(uuid.uuid4()),
                project_id=project.id,
                requested_by_user_id=owner.id,
                approval_type="gmail_send",
                status="pending",
                payload_json={"risk_level": "R2"},
                created_at=datetime.now(UTC),
            )
            await snapshot_routing_on_approval(db, approval)
            before_ids = {row["user_id"] for row in approval.eligible_approvers_json or []}
            assert operator_user.id not in before_ids

            approval.escalation_state_json = {
                "escalated_at": datetime.now(UTC).isoformat(),
                "escalation_roles": ["owner", "admin", "approver", "operator"],
            }
            eligible, _snapshot = await resolve_eligible_approvers(
                db,
                project_id=approval.project_id,
                requested_by_user_id=approval.requested_by_user_id,
                approval_type=approval.approval_type,
                payload=dict(approval.payload_json or {}),
                delegations_json=list(approval.delegations_json or []),
                escalation_state_json=dict(approval.escalation_state_json or {}),
                sla_policy_json=dict(approval.sla_policy_json or {}),
            )
            after_ids = {item.user_id for item in eligible}
            assert operator_user.id in after_ids
    finally:
        await _cleanup_project(project.id)


def test_is_approval_expired_blocks_stale_decide() -> None:
    arguments = {"body": "hello", "issue_link_id": "link-1", "close_issue": False}
    effect = build_proposed_effect(
        action_key="github_comment",
        raw_arguments=arguments,
        expires_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    approval = ApprovalRequest(
        id="approval-expired",
        approval_type="github_comment",
        status="pending",
        payload_json={"body": "hello"},
    )
    apply_proposed_effect_to_approval(approval, effect)
    assert is_approval_expired(approval) is True


@pytest.mark.asyncio
async def test_decide_approval_rejects_expired_effect() -> None:
    arguments = {"body": "hello", "issue_link_id": "link-1", "close_issue": False}
    effect = build_proposed_effect(
        action_key="github_comment",
        raw_arguments=arguments,
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    approval = ApprovalRequest(
        id="approval-expired",
        approval_type="github_comment",
        status="pending",
        payload_json={"body": "hello"},
    )
    apply_proposed_effect_to_approval(approval, effect)

    service = OrchestrationApprovalsServiceMixin()
    service.repo = MagicMock()
    service.repo.get_approval_for_update = AsyncMock(return_value=approval)
    service.db = MagicMock()
    service.db.commit = AsyncMock()
    user = User(id="owner", email="owner@example.com")

    with pytest.raises(HTTPException) as exc:
        await service.decide_approval(user, approval.id, "approved", "ok")
    assert exc.value.status_code == 409
    assert approval.status == "stale"


@pytest.mark.asyncio
async def test_scan_pending_approval_sla_escalates_due_rows(monkeypatch) -> None:
    approval = ApprovalRequest(
        id="approval-due",
        approval_type="workflow_tool",
        status="pending",
        created_at=datetime.now(UTC) - timedelta(hours=30),
        due_at=datetime.now(UTC) - timedelta(hours=1),
        sla_policy_json=normalize_approval_sla_policy({"escalate_hours_after_due": 0}),
        escalation_state_json={},
        eligible_approvers_json=[{"user_id": "owner-1", "role": "owner", "reasons": []}],
        delegations_json=[],
        payload_json={},
    )

    class _Result:
        def scalars(self):
            return self

        def all(self):
            return [approval]

    db = AsyncMock()
    db.execute = AsyncMock(return_value=_Result())
    db.commit = AsyncMock()

    notifications = AsyncMock()
    notifications.create = AsyncMock()
    monkeypatch.setattr(
        "backend.modules.orchestration.execution.hitl.approval_sla.NotificationsRepository",
        lambda _db: notifications,
    )
    monkeypatch.setattr(
        "backend.modules.orchestration.execution.hitl.approver_resolver.snapshot_routing_on_approval",
        AsyncMock(),
    )

    stats = await scan_pending_approval_sla(db)
    assert stats["escalated"] == 1
    assert approval.escalation_state_json.get("escalated_at")
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_delegate_rejects_operator_target(monkeypatch) -> None:
    approval = ApprovalRequest(
        id="approval-1",
        approval_type="task_mark_complete",
        status="pending",
        workspace_id="ws-1",
        eligible_approvers_json=[{"user_id": "owner", "role": "owner", "reasons": []}],
        payload_json={},
    )
    db = AsyncMock()
    ws_repo = AsyncMock()
    ws_repo.get_active_membership = AsyncMock(
        return_value=WorkspaceMembership(
            workspace_id="ws-1",
            user_id="operator",
            role=WORKSPACE_ROLE_OPERATOR,
        )
    )
    monkeypatch.setattr(
        "backend.modules.orchestration.execution.hitl.approval_delegation.WorkspaceRepository",
        lambda _db: ws_repo,
    )
    monkeypatch.setattr(
        "backend.modules.orchestration.execution.hitl.approver_resolver.recheck_user_eligible",
        AsyncMock(),
    )

    with pytest.raises(ApprovalDelegationError, match="cannot decide"):
        await delegate_approval(
            db,
            approval=approval,
            from_user_id="owner",
            to_user_id="operator",
            reason="test",
        )
