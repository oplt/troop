"""Approval SLA, warn, and escalation (HITL-002B)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from backend.modules.notifications.repository import NotificationsRepository
from backend.modules.orchestration.models import ApprovalRequest
from backend.modules.projects.orchestration_models import OrchestratorProject

DEFAULT_APPROVAL_SLA: dict[str, Any] = {
    "enabled": True,
    "response_hours": 24,
    "warn_hours_before_due": 4,
    "escalate_hours_after_due": 0,
    "escalation_roles": ["admin", "owner"],
}


def normalize_approval_sla_policy(raw: dict[str, Any] | None) -> dict[str, Any]:
    policy = dict(DEFAULT_APPROVAL_SLA)
    if isinstance(raw, dict):
        policy.update({key: raw[key] for key in raw if key in policy or key == "enabled"})
    if not isinstance(policy.get("escalation_roles"), list):
        policy["escalation_roles"] = list(DEFAULT_APPROVAL_SLA["escalation_roles"])
    policy["escalation_roles"] = [
        str(role).strip() for role in policy["escalation_roles"] if str(role).strip()
    ] or list(DEFAULT_APPROVAL_SLA["escalation_roles"])
    policy["response_hours"] = max(1.0, float(policy.get("response_hours") or 24))
    policy["warn_hours_before_due"] = max(0.0, float(policy.get("warn_hours_before_due") or 0))
    policy["escalate_hours_after_due"] = max(
        0.0, float(policy.get("escalate_hours_after_due") or 0)
    )
    policy["enabled"] = bool(policy.get("enabled", True))
    return policy


def compute_approval_due_at(
    *,
    created_at: datetime,
    sla_policy: dict[str, Any],
) -> datetime | None:
    if not sla_policy.get("enabled", True):
        return None
    anchor = created_at
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=UTC)
    return anchor + timedelta(hours=float(sla_policy["response_hours"]))


async def resolve_sla_policy_for_approval(
    db: AsyncSession,
    approval: ApprovalRequest,
) -> dict[str, Any]:
    payload = dict(approval.payload_json or {})
    if isinstance(payload.get("approval_sla"), dict):
        return normalize_approval_sla_policy(payload["approval_sla"])

    if approval.project_id:
        project = await db.get(OrchestratorProject, approval.project_id)
        if project is not None:
            settings = dict(project.settings_json or {})
            execution = dict(settings.get("execution") or {})
            hitl = dict(settings.get("hitl") or {})
            project_sla = dict(execution.get("sla") or {})
            approval_sla = dict(hitl.get("approval_sla") or {})
            merged = {
                **project_sla,
                **approval_sla,
            }
            if merged:
                return normalize_approval_sla_policy(merged)

    return normalize_approval_sla_policy(None)


async def apply_sla_on_approval(db: AsyncSession, approval: ApprovalRequest) -> None:
    sla_policy = await resolve_sla_policy_for_approval(db, approval)
    approval.sla_policy_json = sla_policy
    approval.due_at = compute_approval_due_at(
        created_at=approval.created_at or datetime.now(UTC),
        sla_policy=sla_policy,
    )
    if approval.escalation_state_json is None:
        approval.escalation_state_json = {}


def escalation_state(raw: dict[str, Any] | None) -> dict[str, Any]:
    return dict(raw or {})


def is_escalated(approval: ApprovalRequest) -> bool:
    return bool(escalation_state(approval.escalation_state_json).get("escalated_at"))


async def scan_pending_approval_sla(db: AsyncSession) -> dict[str, int]:
    """Warn and escalate pending approvals past SLA thresholds."""
    now = datetime.now(UTC)
    result = await db.execute(
        select(ApprovalRequest)
        .where(
            ApprovalRequest.status == "pending",
            ApprovalRequest.due_at.is_not(None),
        )
        .with_for_update(skip_locked=True)
    )
    rows = list(result.scalars().all())
    warned = 0
    escalated = 0
    notifications = NotificationsRepository(db)

    for approval in rows:
        sla_policy = normalize_approval_sla_policy(approval.sla_policy_json)
        if not sla_policy.get("enabled", True):
            continue
        due_at = approval.due_at
        if due_at is None:
            continue
        if due_at.tzinfo is None:
            due_at = due_at.replace(tzinfo=UTC)

        state = escalation_state(approval.escalation_state_json)
        warn_hours = float(sla_policy["warn_hours_before_due"])
        warn_at = due_at - timedelta(hours=warn_hours)
        if warn_hours > 0 and now >= warn_at and now < due_at and not state.get("warn_sent_at"):
            state["warn_sent_at"] = now.isoformat()
            approval.escalation_state_json = state
            flag_modified(approval, "escalation_state_json")
            for row in approval.eligible_approvers_json or []:
                user_id = str(row.get("user_id") or "")
                if not user_id:
                    continue
                await notifications.create(
                    user_id,
                    type="approval_sla_warn",
                    title="Approval nearing SLA deadline",
                    body=(
                        f"Approval {approval.approval_type} is due by "
                        f"{due_at.isoformat(timespec='minutes')}"
                    ),
                )
            warned += 1

        breach_at = due_at + timedelta(hours=float(sla_policy["escalate_hours_after_due"]))
        if now < breach_at or state.get("escalated_at"):
            continue

        state["escalated_at"] = now.isoformat()
        state["escalation_roles"] = list(sla_policy["escalation_roles"])
        approval.escalation_state_json = state
        flag_modified(approval, "escalation_state_json")
        from backend.modules.orchestration.execution.hitl.approver_resolver import (
            snapshot_routing_on_approval,
        )

        await snapshot_routing_on_approval(db, approval)

        for row in approval.eligible_approvers_json or []:
            user_id = str(row.get("user_id") or "")
            if not user_id:
                continue
            await notifications.create(
                user_id,
                type="approval_sla_escalated",
                title="Approval escalated",
                body=(
                    f"Approval {approval.approval_type} breached SLA and was escalated "
                    f"to {', '.join(sla_policy['escalation_roles'])}"
                ),
            )
        escalated += 1

    if warned or escalated:
        await db.commit()

    return {"checked": len(rows), "warned": warned, "escalated": escalated}
