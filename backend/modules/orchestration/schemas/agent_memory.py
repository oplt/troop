from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.core.schemas import RequestModel
from backend.modules.orchestration.schemas.common import *  # noqa: F403


class AgentMemoryEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    owner_id: str
    agent_id: str
    project_id: str | None
    source_run_id: str | None
    key: str
    value_text: str
    scope: str
    status: str
    approved_by_user_id: str | None
    ttl_days: int | None
    expires_at: datetime | None
    deleted_at: datetime | None
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class AgentMemoryEntryCreate(RequestModel):
    agent_id: str = Field(min_length=1, max_length=64)
    key: str = Field(min_length=1, max_length=128)
    value_text: str = Field(min_length=1, max_length=50000)
    scope: Literal["project-only", "long-term"] = "project-only"
    ttl_days: int | None = Field(default=None, ge=1, le=3650)
