"""Approval delegation helpers (HITL-002B)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from backend.modules.identity_access.workspace_permissions import (
    PERM_APPROVAL_DECIDE,
    role_has_permission,
)
from backend.modules.identity_access.workspace_repository import WorkspaceRepository
from backend.modules.orchestration.models import ApprovalRequest


class ApprovalDelegationError(PermissionError):
    """Raised when delegation preconditions fail."""


def active_delegations(delegations_json: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    rows = [dict(item) for item in (delegations_json or []) if isinstance(item, dict)]
    return [row for row in rows if row.get("active", True)]


def delegation_constraints(
    delegations_json: list[dict[str, Any]] | None,
) -> tuple[set[str], dict[str, str]]:
    """Return users who delegated away decision rights and active delegate targets."""
    delegated_away: set[str] = set()
    delegate_targets: dict[str, str] = {}
    for row in active_delegations(delegations_json):
        from_user_id = str(row.get("from_user_id") or "")
        to_user_id = str(row.get("to_user_id") or "")
        if not from_user_id or not to_user_id:
            continue
        delegated_away.add(from_user_id)
        delegate_targets[to_user_id] = from_user_id
    return delegated_away, delegate_targets


async def delegate_approval(
    db: AsyncSession,
    *,
    approval: ApprovalRequest,
    from_user_id: str,
    to_user_id: str,
    reason: str | None = None,
) -> ApprovalRequest:
    from backend.modules.orchestration.execution.hitl.approver_resolver import (
        recheck_user_eligible,
        snapshot_routing_on_approval,
    )

    if approval.status != "pending":
        raise ApprovalDelegationError(
            f"Only pending approvals can be delegated; status is {approval.status!r}"
        )
    if from_user_id == to_user_id:
        raise ApprovalDelegationError("Cannot delegate an approval to yourself")

    await recheck_user_eligible(db, approval=approval, user_id=from_user_id)

    workspace_id = approval.workspace_id
    if not workspace_id:
        raise ApprovalDelegationError("Approval has no workspace context for delegation")

    ws_repo = WorkspaceRepository(db)
    delegate_membership = await ws_repo.get_active_membership(workspace_id, to_user_id)
    if delegate_membership is None:
        raise ApprovalDelegationError("Delegate target is not an active workspace member")
    if not role_has_permission(delegate_membership.role, PERM_APPROVAL_DECIDE):
        raise ApprovalDelegationError(
            f"Delegate target role {delegate_membership.role!r} cannot decide approvals"
        )

    for row in active_delegations(approval.delegations_json):
        if str(row.get("from_user_id") or "") == from_user_id:
            raise ApprovalDelegationError("You have already delegated this approval")
        if str(row.get("to_user_id") or "") == to_user_id:
            raise ApprovalDelegationError("This user already has an active delegation")

    entry = {
        "from_user_id": from_user_id,
        "to_user_id": to_user_id,
        "reason": str(reason or "").strip() or None,
        "created_at": datetime.now(UTC).isoformat(),
        "active": True,
    }
    rows = list(approval.delegations_json or [])
    rows.append(entry)
    approval.delegations_json = rows
    flag_modified(approval, "delegations_json")
    await snapshot_routing_on_approval(db, approval)
    return approval
