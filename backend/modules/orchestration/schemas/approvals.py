from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.core.schemas import RequestModel
from backend.modules.orchestration.schemas.common import *  # noqa: F403


class ApprovalDecision(RequestModel):
    status: Literal["approved", "rejected"]
    reason: str | None = None


class ApprovalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str | None
    task_id: str | None
    run_id: str | None
    issue_link_id: str | None
    requested_by_user_id: str | None
    approved_by_user_id: str | None
    approval_type: str
    status: str
    reason: str | None
    payload: dict[str, Any]
    effect_hash: str | None = None
    effect_version: int = 1
    precondition_fingerprint: str | None = None
    expires_at: datetime | None = None
    proposed_effect: dict[str, Any] | None = None
    workspace_id: str | None = None
    eligible_approvers: list[dict[str, Any]] = Field(default_factory=list)
    routing_snapshot: dict[str, Any] = Field(default_factory=dict)
    decided_eligibility_reason: str | None = None
    due_at: datetime | None = None
    sla_policy: dict[str, Any] = Field(default_factory=dict)
    delegations: list[dict[str, Any]] = Field(default_factory=list)
    escalation_state: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    resolved_at: datetime | None


class HITLAuditLogResponse(BaseModel):
    id: str
    user_id: str | None
    action: str
    resource_type: str | None
    resource_id: str | None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
