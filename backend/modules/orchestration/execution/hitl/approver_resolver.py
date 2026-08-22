"""Role-based approver resolution (HITL-002A)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.identity_access.workspace_permissions import (
    PERM_APPROVAL_DECIDE,
    role_has_permission,
)
from backend.modules.identity_access.workspace_repository import WorkspaceRepository
from backend.modules.identity_access.workspace_roles import WORKSPACE_ROLES
from backend.modules.orchestration.execution.hitl.approval_delegation import delegation_constraints
from backend.modules.orchestration.execution.hitl.approval_sla import (
    apply_sla_on_approval,
    escalation_state,
    normalize_approval_sla_policy,
)
from backend.modules.orchestration.models import ApprovalRequest
from backend.modules.projects.orchestration_models import OrchestratorProject

ROLES_WITH_DECIDE = frozenset({"owner", "admin", "approver"})
HIGH_RISK_ROLES = frozenset({"owner", "admin"})


class ApproverEligibilityError(PermissionError):
    """Raised when a user is not eligible to decide or commit an approval."""


@dataclass(frozen=True)
class EligibleApprover:
    user_id: str
    role: str
    reasons: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ApprovalRoutingSnapshot:
    workspace_id: str | None
    company_id: str | None
    project_id: str | None
    approval_type: str
    action_key: str | None
    matched_roles: list[str]
    explicit_approver_ids: list[str]
    policy_conditions: dict[str, Any]
    resolved_at: str


def eligible_approver_to_dict(item: EligibleApprover) -> dict[str, Any]:
    return {
        "user_id": item.user_id,
        "role": item.role,
        "reasons": list(item.reasons),
    }


def eligible_approver_from_dict(raw: dict[str, Any]) -> EligibleApprover:
    return EligibleApprover(
        user_id=str(raw.get("user_id") or ""),
        role=str(raw.get("role") or ""),
        reasons=tuple(str(reason) for reason in (raw.get("reasons") or [])),
    )


def routing_snapshot_from_dict(raw: dict[str, Any] | None) -> ApprovalRoutingSnapshot | None:
    if not raw:
        return None
    return ApprovalRoutingSnapshot(
        workspace_id=raw.get("workspace_id"),
        company_id=raw.get("company_id"),
        project_id=raw.get("project_id"),
        approval_type=str(raw.get("approval_type") or ""),
        action_key=raw.get("action_key"),
        matched_roles=[str(role) for role in (raw.get("matched_roles") or [])],
        explicit_approver_ids=[
            str(user_id) for user_id in (raw.get("explicit_approver_ids") or [])
        ],
        policy_conditions=dict(raw.get("policy_conditions") or {}),
        resolved_at=str(raw.get("resolved_at") or ""),
    )


def _extract_explicit_approver_ids(payload: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for key in ("approver_ids", "approvers"):
        raw = payload.get(key)
        if not isinstance(raw, list):
            continue
        for item in raw:
            if isinstance(item, str) and item.strip():
                ids.append(item.strip())
            elif isinstance(item, dict):
                user_id = item.get("user_id") or item.get("id")
                if user_id:
                    ids.append(str(user_id))
    seen: set[str] = set()
    ordered: list[str] = []
    for user_id in ids:
        if user_id in seen:
            continue
        seen.add(user_id)
        ordered.append(user_id)
    return ordered


def _extract_explicit_roles(payload: dict[str, Any]) -> list[str] | None:
    raw = payload.get("approver_roles")
    if not isinstance(raw, list) or not raw:
        return None
    roles = [str(role).strip() for role in raw if str(role).strip() in WORKSPACE_ROLES]
    return roles or None


def _policy_required_roles(
    payload: dict[str, Any],
    *,
    approval_type: str,
    action_key: str | None,
) -> frozenset[str] | None:
    risk = str(payload.get("risk_level") or payload.get("tool_risk_level") or "").upper()
    if risk in {"R2", "R3", "HIGH", "CRITICAL"}:
        return HIGH_RISK_ROLES
    if approval_type.startswith("gmail_") and "send" in approval_type:
        return HIGH_RISK_ROLES
    if action_key:
        lowered = action_key.lower()
        if lowered.startswith(("gmail_send", "telegram_send")):
            return HIGH_RISK_ROLES
    return None


async def resolve_workspace_id_for_approval(
    db: AsyncSession,
    *,
    project_id: str | None,
    requested_by_user_id: str | None,
) -> str | None:
    ws_repo = WorkspaceRepository(db)
    if project_id:
        project = await db.get(OrchestratorProject, project_id)
        if project is not None:
            workspace = await ws_repo.get_default_workspace_for_user(project.owner_id)
            if workspace is not None:
                return workspace.id
    if requested_by_user_id:
        workspace = await ws_repo.get_default_workspace_for_user(requested_by_user_id)
        if workspace is not None:
            return workspace.id
    return None


async def resolve_eligible_approvers(
    db: AsyncSession,
    *,
    project_id: str | None,
    requested_by_user_id: str | None,
    approval_type: str,
    action_key: str | None = None,
    payload: dict[str, Any] | None = None,
    delegations_json: list[dict[str, Any]] | None = None,
    escalation_state_json: dict[str, Any] | None = None,
    sla_policy_json: dict[str, Any] | None = None,
) -> tuple[list[EligibleApprover], ApprovalRoutingSnapshot]:
    payload_data = dict(payload or {})
    workspace_id = await resolve_workspace_id_for_approval(
        db,
        project_id=project_id,
        requested_by_user_id=requested_by_user_id,
    )
    company_id: str | None = None
    project_owner_id: str | None = None
    if project_id:
        project = await db.get(OrchestratorProject, project_id)
        if project is not None:
            company_id = project.company_id
            project_owner_id = project.owner_id

    explicit_ids = _extract_explicit_approver_ids(payload_data)
    explicit_roles = _extract_explicit_roles(payload_data)
    policy_roles = _policy_required_roles(
        payload_data,
        approval_type=approval_type,
        action_key=action_key,
    )

    if explicit_ids:
        matched_roles = explicit_roles or sorted(ROLES_WITH_DECIDE)
    elif explicit_roles:
        matched_roles = list(explicit_roles)
    elif is_escalated_from_state(escalation_state_json):
        state = escalation_state(escalation_state_json)
        sla_policy = normalize_approval_sla_policy(sla_policy_json)
        matched_roles = list(
            state.get("escalation_roles")
            or sla_policy.get("escalation_roles")
            or sorted(HIGH_RISK_ROLES)
        )
    elif policy_roles:
        matched_roles = sorted(policy_roles)
    else:
        matched_roles = sorted(ROLES_WITH_DECIDE)

    eligible: dict[str, EligibleApprover] = {}
    ws_repo = WorkspaceRepository(db)

    if workspace_id:
        memberships = await ws_repo.list_active_memberships_by_roles(workspace_id, matched_roles)
        for membership in memberships:
            reasons: list[str] = [f"workspace_role:{membership.role}"]
            if project_owner_id and membership.user_id == project_owner_id:
                reasons.append("project_owner")
            if company_id:
                reasons.append(f"company_context:{company_id}")
            eligible[membership.user_id] = EligibleApprover(
                user_id=membership.user_id,
                role=membership.role,
                reasons=tuple(reasons),
            )

        if explicit_ids:
            for user_id in explicit_ids:
                membership = await ws_repo.get_active_membership(workspace_id, user_id)
                if membership is None:
                    continue
                if not role_has_permission(membership.role, PERM_APPROVAL_DECIDE):
                    continue
                reasons = ["explicit_approver_id", f"workspace_role:{membership.role}"]
                if project_owner_id and user_id == project_owner_id:
                    reasons.append("project_owner")
                eligible[user_id] = EligibleApprover(
                    user_id=user_id,
                    role=membership.role,
                    reasons=tuple(reasons),
                )

    if project_owner_id and project_owner_id not in eligible:
        eligible[project_owner_id] = EligibleApprover(
            user_id=project_owner_id,
            role="owner",
            reasons=("project_owner", "legacy_owner_fallback"),
        )

    delegated_away, delegate_targets = delegation_constraints(delegations_json)
    for user_id in list(eligible):
        if user_id in delegated_away:
            del eligible[user_id]

    if workspace_id and delegate_targets:
        for to_user_id, from_user_id in delegate_targets.items():
            membership = await ws_repo.get_active_membership(workspace_id, to_user_id)
            if membership is None:
                continue
            if not role_has_permission(membership.role, PERM_APPROVAL_DECIDE):
                continue
            eligible[to_user_id] = EligibleApprover(
                user_id=to_user_id,
                role=membership.role,
                reasons=(
                    f"delegated_from:{from_user_id}",
                    f"workspace_role:{membership.role}",
                ),
            )

    state = escalation_state(escalation_state_json)
    snapshot = ApprovalRoutingSnapshot(
        workspace_id=workspace_id,
        company_id=company_id,
        project_id=project_id,
        approval_type=approval_type,
        action_key=action_key,
        matched_roles=matched_roles,
        explicit_approver_ids=explicit_ids,
        policy_conditions={
            "required_roles": sorted(policy_roles) if policy_roles else None,
            "explicit_roles": explicit_roles,
            "escalated": bool(state.get("escalated_at")),
            "escalation_roles": state.get("escalation_roles"),
        },
        resolved_at=datetime.now(UTC).isoformat(),
    )
    return list(eligible.values()), snapshot


def is_escalated_from_state(raw: dict[str, Any] | None) -> bool:
    return bool(escalation_state(raw).get("escalated_at"))


async def snapshot_routing_on_approval(db: AsyncSession, approval: ApprovalRequest) -> None:
    await apply_sla_on_approval(db, approval)
    payload = dict(approval.payload_json or {})
    action_key = payload.get("action_key") or payload.get("tool_slug")
    eligible, snapshot = await resolve_eligible_approvers(
        db,
        project_id=approval.project_id,
        requested_by_user_id=approval.requested_by_user_id,
        approval_type=approval.approval_type,
        action_key=str(action_key) if action_key else None,
        payload=payload,
        delegations_json=list(approval.delegations_json or []),
        escalation_state_json=dict(approval.escalation_state_json or {}),
        sla_policy_json=dict(approval.sla_policy_json or {}),
    )
    approval.workspace_id = snapshot.workspace_id
    approval.eligible_approvers_json = [eligible_approver_to_dict(item) for item in eligible]
    approval.routing_snapshot_json = asdict(snapshot)


async def recheck_user_eligible(
    db: AsyncSession,
    *,
    approval: ApprovalRequest,
    user_id: str,
) -> EligibleApprover:
    payload = dict(approval.payload_json or {})
    action_key = payload.get("action_key") or payload.get("tool_slug")
    eligible, _snapshot = await resolve_eligible_approvers(
        db,
        project_id=approval.project_id,
        requested_by_user_id=approval.requested_by_user_id,
        approval_type=approval.approval_type,
        action_key=str(action_key) if action_key else None,
        payload=payload,
        delegations_json=list(approval.delegations_json or []),
        escalation_state_json=dict(approval.escalation_state_json or {}),
        sla_policy_json=dict(approval.sla_policy_json or {}),
    )
    for item in eligible:
        if item.user_id == user_id:
            return item
    raise ApproverEligibilityError(
        f"User {user_id!r} is not an eligible approver for approval {approval.id!r}"
    )


def format_eligibility_reason(item: EligibleApprover) -> str:
    return "; ".join(item.reasons)


async def user_can_access_approval(
    db: AsyncSession,
    user_id: str,
    approval: ApprovalRequest,
) -> bool:
    if approval.project_id:
        project = await db.get(OrchestratorProject, approval.project_id)
        if project is not None and project.owner_id == user_id:
            return True
    elif approval.requested_by_user_id == user_id:
        return True
    try:
        await recheck_user_eligible(db, approval=approval, user_id=user_id)
    except ApproverEligibilityError:
        return False
    return True


async def recheck_decided_approver_at_commit(
    db: AsyncSession,
    *,
    approval: ApprovalRequest,
) -> EligibleApprover:
    if not approval.approved_by_user_id:
        raise ApproverEligibilityError("Approval requires an eligible approver decision")
    return await recheck_user_eligible(
        db,
        approval=approval,
        user_id=approval.approved_by_user_id,
    )
