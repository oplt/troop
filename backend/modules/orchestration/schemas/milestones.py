from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.core.schemas import RequestModel
from backend.modules.github.schemas import GithubSyncEventResponse

from backend.modules.orchestration.schemas.common import *  # noqa: F403

class ProjectMilestoneCreate(RequestModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    due_date: datetime | None = None
    status: str = "open"
    position: int = 0


class ProjectMilestoneUpdate(RequestModel):
    title: str | None = None
    description: str | None = None
    due_date: datetime | None = None
    status: str | None = None
    position: int | None = None


class ProjectMilestoneResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    title: str
    description: str | None
    due_date: datetime | None
    status: str
    position: int
    created_at: datetime
    updated_at: datetime


class ProjectDecisionCreate(RequestModel):
    title: str = Field(min_length=1, max_length=255)
    decision: str = Field(min_length=1)
    rationale: str | None = None
    author_label: str | None = None
    task_id: str | None = None
    brainstorm_id: str | None = None


class ProjectDecisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    task_id: str | None
    brainstorm_id: str | None
    title: str
    decision: str
    rationale: str | None
    author_label: str | None
    created_at: datetime
