from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from backend.core.schemas import RequestModel
from backend.modules.orchestration.schemas.common import *  # noqa: F403


class TaskDecomposeRequest(RequestModel):
    max_subtasks: int = Field(default=5, ge=1, le=10)
    context: str | None = None


class TaskDecomposeResponse(BaseModel):
    parent_task_id: str
    subtasks: list[dict[str, Any]]


class TaskAcceptanceCheckResponse(BaseModel):
    task_id: str
    passed: bool
    config: dict[str, Any] = Field(default_factory=dict)
    checks: list[dict[str, Any]]  # [{name, passed, detail}]


class TaskArtifactCreate(RequestModel):
    kind: str = "summary"
    title: str = Field(min_length=1, max_length=255)
    content: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
