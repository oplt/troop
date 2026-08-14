"""Canonical exact-effect approval primitives.

An approval authorizes one normalized proposed effect (hash + version), optional
resource precondition fingerprint, and expiry — not a broad permission to mutate
similar payloads later. Edit-and-approve creates a replacement approval row.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from backend.modules.orchestration.models import ApprovalRequest
from backend.modules.orchestration.tool_execution_context import arguments_hash
from backend.modules.workforce.integrations.email import (
    canonical_email_action_arguments,
    canonical_outlook_email_action_arguments,
    email_action_arguments_hash,
    outlook_email_action_arguments_hash,
)
from backend.modules.workforce.integrations.crm_records import (
    canonical_hubspot_crm_arguments,
    canonical_salesforce_crm_arguments,
    hubspot_crm_arguments_hash,
    salesforce_crm_arguments_hash,
)
from backend.modules.workforce.integrations.issue_tracking import (
    canonical_jira_issue_arguments,
    canonical_linear_issue_arguments,
    jira_issue_arguments_hash,
    linear_issue_arguments_hash,
)

DEFAULT_APPROVAL_TTL_HOURS = int(os.getenv("APPROVAL_EFFECT_TTL_HOURS", "168"))

_GMAIL_ACTIONS = frozenset({"gmail.send_draft", "gmail.create_draft", "gmail.update_draft"})
_OUTLOOK_ACTIONS = frozenset({"outlook.send_draft", "outlook.create_draft", "outlook.update_draft"})
_GITHUB_COMMENT_ACTIONS = frozenset(
    {
        "github_comment",
        "github_progress_comment",
        "github_manager_closure",
    }
)
_JIRA_MUTATION_ACTIONS = frozenset(
    {"jira.create_issue", "jira.update_issue", "jira.add_comment"}
)
_LINEAR_MUTATION_ACTIONS = frozenset(
    {"linear.create_issue", "linear.update_issue", "linear.add_comment"}
)
_HUBSPOT_MUTATION_ACTIONS = frozenset(
    {"hubspot.update_contact", "hubspot.create_note", "hubspot.send_email"}
)
_SALESFORCE_MUTATION_ACTIONS = frozenset(
    {"salesforce.update_contact", "salesforce.create_task", "salesforce.send_email"}
)


def normalize_github_comment_effect(arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "issue_link_id": str(arguments.get("issue_link_id") or ""),
        "repository_id": str(arguments.get("repository_id") or ""),
        "issue_number": int(arguments.get("issue_number") or 0),
        "body": str(arguments.get("body") or arguments.get("draft_comment") or "").strip(),
        "close_issue": bool(arguments.get("close_issue", False)),
    }


class ExactEffectError(ValueError):
    """Raised when a commit-time effect does not match the approved binding."""


@dataclass(frozen=True)
class ProposedEffect:
    action_key: str
    normalized_effect: dict[str, Any]
    effect_hash: str
    precondition_fingerprint: str | None = None
    effect_version: int = 1
    expires_at: datetime | None = None
    replaces_approval_id: str | None = None


def _strip_tool_prefix(action_key: str) -> str:
    key = str(action_key or "").strip()
    for prefix in ("tool:", "execute:", "tool_execution:"):
        if key.startswith(prefix):
            return key[len(prefix) :]
    return key


def normalize_proposed_effect(
    action_key: str, raw_arguments: dict[str, Any] | None
) -> dict[str, Any]:
    """Return a deterministic normalized effect payload for hashing."""
    arguments = dict(raw_arguments or {})
    canonical_key = _strip_tool_prefix(action_key)
    if canonical_key in _GMAIL_ACTIONS or str(arguments.get("provider") or "") == "gmail":
        return canonical_email_action_arguments(arguments)
    if canonical_key in _OUTLOOK_ACTIONS or str(arguments.get("provider") or "") == "outlook":
        return canonical_outlook_email_action_arguments(arguments)
    if canonical_key in _GITHUB_COMMENT_ACTIONS:
        return normalize_github_comment_effect(arguments)
    if canonical_key in _JIRA_MUTATION_ACTIONS or str(arguments.get("provider") or "") == "jira":
        if canonical_key.startswith("jira."):
            return canonical_jira_issue_arguments(arguments)
    if canonical_key in _LINEAR_MUTATION_ACTIONS or str(arguments.get("provider") or "") == "linear":
        if canonical_key.startswith("linear."):
            return canonical_linear_issue_arguments(arguments)
    if canonical_key in _HUBSPOT_MUTATION_ACTIONS or str(arguments.get("provider") or "") == "hubspot":
        if canonical_key.startswith("hubspot."):
            return canonical_hubspot_crm_arguments(arguments)
    if canonical_key in _SALESFORCE_MUTATION_ACTIONS or str(arguments.get("provider") or "") == "salesforce":
        if canonical_key.startswith("salesforce."):
            return canonical_salesforce_crm_arguments(arguments)
    binding_keys = (
        "connector_installation_id",
        "resource_id",
        "repository_id",
        "issue_link_id",
        "thread_id",
        "gmail_draft_id",
        "outlook_draft_id",
        "draft_id",
        "path",
    )
    normalized = {key: arguments[key] for key in binding_keys if key in arguments}
    for key, value in arguments.items():
        if key not in normalized:
            normalized[key] = value
    return normalized


def compute_effect_hash(normalized_effect: dict[str, Any], *, action_key: str = "") -> str:
    canonical_key = _strip_tool_prefix(action_key)
    if canonical_key in _GMAIL_ACTIONS or str(normalized_effect.get("provider") or "") == "gmail":
        return email_action_arguments_hash(normalized_effect)
    if canonical_key in _OUTLOOK_ACTIONS or str(normalized_effect.get("provider") or "") == "outlook":
        return outlook_email_action_arguments_hash(normalized_effect)
    if canonical_key in _JIRA_MUTATION_ACTIONS or str(normalized_effect.get("provider") or "") == "jira":
        return jira_issue_arguments_hash(normalized_effect)
    if canonical_key in _LINEAR_MUTATION_ACTIONS or str(normalized_effect.get("provider") or "") == "linear":
        return linear_issue_arguments_hash(normalized_effect)
    if canonical_key in _HUBSPOT_MUTATION_ACTIONS or str(normalized_effect.get("provider") or "") == "hubspot":
        return hubspot_crm_arguments_hash(normalized_effect)
    if canonical_key in _SALESFORCE_MUTATION_ACTIONS or str(normalized_effect.get("provider") or "") == "salesforce":
        return salesforce_crm_arguments_hash(normalized_effect)
    return arguments_hash(normalized_effect)


def default_effect_expiry(*, now: datetime | None = None) -> datetime:
    base = now or datetime.now(UTC)
    return base + timedelta(hours=DEFAULT_APPROVAL_TTL_HOURS)


def build_proposed_effect(
    *,
    action_key: str,
    raw_arguments: dict[str, Any] | None,
    precondition_fingerprint: str | None = None,
    effect_version: int = 1,
    expires_at: datetime | None = None,
    replaces_approval_id: str | None = None,
    now: datetime | None = None,
) -> ProposedEffect:
    normalized = normalize_proposed_effect(action_key, raw_arguments)
    return ProposedEffect(
        action_key=_strip_tool_prefix(action_key),
        normalized_effect=normalized,
        effect_hash=compute_effect_hash(normalized, action_key=action_key),
        precondition_fingerprint=precondition_fingerprint,
        effect_version=max(1, int(effect_version)),
        expires_at=expires_at or default_effect_expiry(now=now),
        replaces_approval_id=replaces_approval_id,
    )


def apply_proposed_effect_to_approval(approval: ApprovalRequest, effect: ProposedEffect) -> None:
    """Persist canonical effect binding on the approval row and payload."""
    approval.effect_hash = effect.effect_hash
    approval.effect_version = effect.effect_version
    approval.precondition_fingerprint = effect.precondition_fingerprint
    approval.expires_at = effect.expires_at
    approval.proposed_effect_json = dict(effect.normalized_effect)

    payload = dict(approval.payload_json or {})
    payload["action_key"] = effect.action_key
    payload["arguments_hash"] = effect.effect_hash
    payload["effect_hash"] = effect.effect_hash
    payload["effect_version"] = effect.effect_version
    payload["precondition_fingerprint"] = effect.precondition_fingerprint
    if effect.expires_at is not None:
        payload["expires_at"] = effect.expires_at.isoformat()
    if effect.replaces_approval_id:
        payload["replaces_approval_request_id"] = effect.replaces_approval_id
    payload["proposed_effect"] = dict(effect.normalized_effect)
    approval.payload_json = payload
    flag_modified(approval, "payload_json")


def read_proposed_effect(approval: ApprovalRequest) -> ProposedEffect | None:
    """Read canonical binding from columns, falling back to legacy payload_json."""
    payload = dict(approval.payload_json or {})
    action_key = str(
        payload.get("action_key") or payload.get("action") or approval.approval_type or ""
    )
    if not action_key:
        return None

    normalized = dict(approval.proposed_effect_json or {})
    if not normalized:
        normalized = dict(payload.get("proposed_effect") or payload.get("draft_arguments") or {})
    if not normalized and payload.get("body") is not None:
        normalized = normalize_github_comment_effect(
            {
                **payload,
                "issue_link_id": approval.issue_link_id,
                "repository_id": payload.get("repository_id"),
                "issue_number": payload.get("issue_number"),
            }
        )
    if not normalized and payload.get("arguments"):
        normalized = dict(payload["arguments"])

    if normalized:
        effect_hash = compute_effect_hash(normalized, action_key=action_key)
    else:
        effect_hash = str(
            approval.effect_hash
            or payload.get("effect_hash")
            or payload.get("arguments_hash")
            or ""
        )
    if not effect_hash:
        return None

    expires_raw = approval.expires_at or payload.get("expires_at")
    expires_at: datetime | None
    if isinstance(expires_raw, datetime):
        expires_at = expires_raw
    elif expires_raw:
        try:
            expires_at = datetime.fromisoformat(str(expires_raw))
        except ValueError:
            expires_at = None
    else:
        expires_at = None

    return ProposedEffect(
        action_key=_strip_tool_prefix(action_key),
        normalized_effect=normalized,
        effect_hash=effect_hash,
        precondition_fingerprint=(
            approval.precondition_fingerprint
            or payload.get("precondition_fingerprint")
            or None
        ),
        effect_version=int(approval.effect_version or payload.get("effect_version") or 1),
        expires_at=expires_at,
        replaces_approval_id=str(payload.get("replaces_approval_request_id") or "") or None,
    )


def is_approval_expired(approval: ApprovalRequest, *, now: datetime | None = None) -> bool:
    effect = read_proposed_effect(approval)
    if effect is None or effect.expires_at is None:
        return False
    current = now or datetime.now(UTC)
    expires_at = effect.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return current >= expires_at


def validate_committed_effect(
    approval: ApprovalRequest,
    *,
    action_key: str,
    raw_arguments: dict[str, Any] | None,
    precondition_fingerprint: str | None = None,
    require_consumed: bool = False,
    owner_id: str | None = None,
    workflow_run_id: str | None = None,
    now: datetime | None = None,
) -> ProposedEffect:
    """Verify an approved grant still authorizes the exact commit-time effect."""
    if approval.status not in {"approved", "stale"}:
        raise ExactEffectError(f"Approval status {approval.status!r} is not committable")
    if approval.status == "stale":
        raise ExactEffectError(approval.reason or "Approval is stale")

    payload = dict(approval.payload_json or {})
    if require_consumed and not (payload.get("_consumed_at") or payload.get("consumed_at")):
        raise ExactEffectError("Approval grant has not been consumed")

    if owner_id:
        payload_owner = str(
            payload.get("owner_id")
            or approval.requested_by_user_id
            or approval.approved_by_user_id
            or ""
        )
        if payload_owner and payload_owner != owner_id:
            raise ExactEffectError("Approval owner does not match commit context")

    if workflow_run_id and str(payload.get("workflow_run_id") or "") not in {"", workflow_run_id}:
        raise ExactEffectError("Approval workflow_run_id does not match commit context")

    if is_approval_expired(approval, now=now):
        raise ExactEffectError("Approval expired before commit")

    bound = read_proposed_effect(approval)
    if bound is None:
        raise ExactEffectError("Approval is missing canonical effect binding")

    canonical_key = _strip_tool_prefix(action_key)
    if bound.action_key != canonical_key:
        raise ExactEffectError(
            f"Approval action {bound.action_key!r} does not match commit action {canonical_key!r}"
        )

    normalized = normalize_proposed_effect(action_key, raw_arguments)
    commit_hash = compute_effect_hash(normalized, action_key=action_key)
    if commit_hash != bound.effect_hash:
        raise ExactEffectError("Commit effect hash does not match approved effect")

    if (
        precondition_fingerprint is not None
        and bound.precondition_fingerprint
        and precondition_fingerprint != bound.precondition_fingerprint
    ):
        raise ExactEffectError("Resource precondition fingerprint changed since approval")

    return bound


def invalidate_approval_for_edit(approval: ApprovalRequest, *, reason: str) -> None:
    """Mark a pending approval invalid when an edit creates a replacement version."""
    now = datetime.now(UTC)
    approval.status = "invalidated"
    approval.reason = reason
    approval.resolved_at = now
    payload = dict(approval.payload_json or {})
    payload["invalidated_by_edit"] = True
    approval.payload_json = payload
    flag_modified(approval, "payload_json")


def create_replacement_approval(
    db: AsyncSession,
    *,
    approval: ApprovalRequest,
    effect: ProposedEffect,
    owner_id: str,
    reason: str | None = None,
) -> ApprovalRequest:
    """Create a new pending approval for a revised effect; never mutate an approved payload."""
    if approval.status != "pending":
        raise ExactEffectError("Only pending approvals can be replaced by an edited effect")

    invalidate_approval_for_edit(
        approval,
        reason="Draft edited; replacement approval created",
    )

    replacement = ApprovalRequest(
        id=str(uuid4()),
        project_id=approval.project_id,
        task_id=approval.task_id,
        run_id=approval.run_id,
        issue_link_id=approval.issue_link_id,
        requested_by_user_id=owner_id,
        approval_type=approval.approval_type,
        status="pending",
        reason=reason or "Approve the revised effect",
        payload_json=dict(approval.payload_json or {}),
    )
    replacement_effect = ProposedEffect(
        action_key=effect.action_key,
        normalized_effect=effect.normalized_effect,
        effect_hash=effect.effect_hash,
        precondition_fingerprint=effect.precondition_fingerprint,
        effect_version=effect.effect_version,
        expires_at=effect.expires_at,
        replaces_approval_id=approval.id,
    )
    apply_proposed_effect_to_approval(replacement, replacement_effect)
    payload = dict(replacement.payload_json or {})
    if "draft_arguments" in payload or effect.action_key.startswith(("gmail.", "outlook.")):
        payload["draft_arguments"] = dict(effect.normalized_effect)
    replacement.payload_json = payload
    flag_modified(replacement, "payload_json")
    db.add(replacement)
    return replacement
