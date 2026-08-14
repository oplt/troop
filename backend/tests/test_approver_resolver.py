"""Tests for role-based approver resolution (HITL-002A)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import delete

from backend.db.session import SessionLocal
from backend.modules.identity_access.models import User, WorkspaceMembership
from backend.modules.identity_access.workspace_authorization import WorkspaceAuthorizationService
from backend.modules.identity_access.workspace_roles import (
    WORKSPACE_ROLE_APPROVER,
    WORKSPACE_ROLE_OPERATOR,
    WORKSPACE_ROLE_OWNER,
)
from backend.modules.orchestration.execution.hitl.approver_resolver import (
    ApproverEligibilityError,
    eligible_approver_to_dict,
    recheck_user_eligible,
    resolve_eligible_approvers,
    snapshot_routing_on_approval,
)
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
from backend.modules.orchestration.repository import OrchestrationRepository
from backend.modules.projects.orchestration_models import OrchestratorProject
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


async def _ensure_workspace(user: User):
    async with SessionLocal() as db:
        auth = WorkspaceAuthorizationService(db)
        ctx = await auth.resolve_active_workspace(user)
        await db.commit()
        return ctx.workspace


async def _add_workspace_member(
    *,
    workspace_id: str,
    user_id: str,
    role: str,
) -> None:
    async with SessionLocal() as db:
        db.add(
            WorkspaceMembership(
                workspace_id=workspace_id,
                user_id=user_id,
                role=role,
            )
        )
        await db.commit()


async def _create_project(owner_id: str) -> OrchestratorProject:
    suffix = uuid.uuid4().hex[:8]
    async with SessionLocal() as db:
        repo = OrchestrationRepository(db)
        project = await repo.create_project(
            owner_id=owner_id,
            name=f"Approver resolver test {suffix}",
            slug=f"approver-{suffix}",
        )
        await db.commit()
        await db.refresh(project)
        return project



async def _cleanup_project(project_id: str) -> None:
    async with SessionLocal() as db:
        await db.execute(delete(OrchestratorProject).where(OrchestratorProject.id == project_id))
        await db.commit()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_resolve_eligible_approvers_includes_workspace_roles(
    tenant_pair: tuple[User, User],
) -> None:
    owner, approver_user = tenant_pair
    workspace = await _ensure_workspace(owner)
    await _ensure_workspace(approver_user)
    await _add_workspace_member(
        workspace_id=workspace.id,
        user_id=approver_user.id,
        role=WORKSPACE_ROLE_APPROVER,
    )
    project = await _create_project(owner.id)

    try:
        async with SessionLocal() as db:
            eligible, snapshot = await resolve_eligible_approvers(
                db,
                project_id=project.id,
                requested_by_user_id=owner.id,
                approval_type="workflow_tool",
                action_key="gmail_read",
                payload={},
            )
        eligible_ids = {item.user_id for item in eligible}
        assert owner.id in eligible_ids
        assert approver_user.id in eligible_ids
        assert snapshot.workspace_id == workspace.id
        assert WORKSPACE_ROLE_APPROVER in snapshot.matched_roles
        approver_entry = next(item for item in eligible if item.user_id == approver_user.id)
        assert "workspace_role:approver" in approver_entry.reasons
    finally:
        await _cleanup_project(project.id)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_snapshot_routing_on_approval_populates_fields(
    tenant_pair: tuple[User, User],
) -> None:
    owner, approver_user = tenant_pair
    workspace = await _ensure_workspace(owner)
    await _ensure_workspace(approver_user)
    await _add_workspace_member(
        workspace_id=workspace.id,
        user_id=approver_user.id,
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
            )
            await snapshot_routing_on_approval(db, approval)

        assert approval.workspace_id == workspace.id
        assert any(
            row.get("user_id") == owner.id for row in (approval.eligible_approvers_json or [])
        )
        assert any(
            row.get("user_id") == approver_user.id
            for row in (approval.eligible_approvers_json or [])
        )
        assert approval.routing_snapshot_json.get("approval_type") == "task_mark_complete"
    finally:
        await _cleanup_project(project.id)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_user_can_access_approval_for_workspace_approver(
    tenant_pair: tuple[User, User],
) -> None:
    from backend.modules.orchestration.execution.hitl.approver_resolver import (
        user_can_access_approval,
    )

    owner, approver_user = tenant_pair
    workspace = await _ensure_workspace(owner)
    await _ensure_workspace(approver_user)
    await _add_workspace_member(
        workspace_id=workspace.id,
        user_id=approver_user.id,
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
            )
            await snapshot_routing_on_approval(db, approval)
            assert await user_can_access_approval(db, approver_user.id, approval)
            assert not await user_can_access_approval(db, uuid.uuid4().hex, approval)
    finally:
        await _cleanup_project(project.id)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_recheck_rejects_operator_without_decide_permission(
    tenant_pair: tuple[User, User],
) -> None:
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
                approval_type="task_mark_complete",
                status="pending",
                payload_json={"to_status": "completed"},
            )
            await snapshot_routing_on_approval(db, approval)
            with pytest.raises(ApproverEligibilityError):
                await recheck_user_eligible(
                    db,
                    approval=approval,
                    user_id=operator_user.id,
                )
    finally:
        await _cleanup_project(project.id)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_recheck_user_eligible_rejects_after_role_removal(
    tenant_pair: tuple[User, User],
) -> None:
    owner, approver_user = tenant_pair
    workspace = await _ensure_workspace(owner)
    await _ensure_workspace(approver_user)
    membership = WorkspaceMembership(
        workspace_id=workspace.id,
        user_id=approver_user.id,
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
            )
            await snapshot_routing_on_approval(db, approval)
            await db.flush()
            assert any(
                row["user_id"] == approver_user.id
                for row in (approval.eligible_approvers_json or [])
            )

            async with SessionLocal() as db2:
                await db2.execute(
                    delete(WorkspaceMembership).where(WorkspaceMembership.id == membership_id)
                )
                await db2.commit()

            with pytest.raises(ApproverEligibilityError):
                await recheck_user_eligible(
                    db,
                    approval=approval,
                    user_id=approver_user.id,
                )
    finally:
        await _cleanup_project(project.id)


def test_high_risk_policy_limits_roles() -> None:
    from backend.modules.orchestration.execution.hitl.approver_resolver import (
        _policy_required_roles,
    )

    roles = _policy_required_roles(
        {"risk_level": "R2"},
        approval_type="gmail_send",
        action_key="gmail_send_message",
    )
    assert roles == frozenset({"owner", "admin"})


@pytest.mark.asyncio
async def test_authorize_and_claim_rechecks_approver_eligibility(monkeypatch) -> None:
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

    async def _reject_recheck(*_args, **_kwargs):
        raise ApproverEligibilityError("Approver no longer eligible")

    monkeypatch.setattr(
        "backend.modules.orchestration.execution.hitl.commit_authorization.recheck_decided_approver_at_commit",
        AsyncMock(side_effect=_reject_recheck),
    )

    with pytest.raises(CommitAuthorizationError, match="no longer eligible"):
        await authorize_and_claim_execution(
            db,
            owner_id="owner",
            action_key="github_comment",
            raw_arguments=arguments,
            approval_id=approval.id,
            idempotency_key=build_idempotency_key("github_comment", approval.id, "link-1"),
            arguments_hash=effect.effect_hash,
            require_approver=True,
        )


def test_eligible_approver_roundtrip() -> None:
    from backend.modules.orchestration.execution.hitl.approver_resolver import (
        EligibleApprover,
        eligible_approver_from_dict,
    )

    original = EligibleApprover(
        user_id="user-1",
        role="approver",
        reasons=("workspace_role:approver", "project_owner"),
    )
    restored = eligible_approver_from_dict(eligible_approver_to_dict(original))
    assert restored.user_id == original.user_id
    assert restored.role == original.role
    assert restored.reasons == original.reasons
