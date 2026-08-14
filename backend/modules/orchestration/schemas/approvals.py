from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.core.schemas import RequestModel
from backend.modules.github.schemas import GithubSyncEventResponse

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


