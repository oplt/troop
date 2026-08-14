from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.modules.orchestration.schemas.common import *  # noqa: F403


class BrainstormDiscourseInsightsResponse(BaseModel):
    message_count: int
    same_agent_streak_ratio: float
    top_repeated_terms: list[str]
    rounds_with_messages: int
    last_round_repetition_score: float | None = None
    last_round_pairwise_min_similarity: float | None = None
    consensus_kind: str | None = None
    conflict_signal: bool | None = None


class TaskTimelineEntry(BaseModel):
    kind: Literal["comment", "github_sync", "approval"]
    id: str
    created_at: datetime
    title: str
    body: str | None = None
    detail: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class WorkflowTemplateResponse(BaseModel):
    id: str
    name: str
    description: str
    suggested_execution: dict[str, Any] = Field(default_factory=dict)


class WorkflowTemplateApplyResponse(BaseModel):
    project_id: str
    template: WorkflowTemplateResponse
    applied_execution: dict[str, Any] = Field(default_factory=dict)
    applied_at: datetime
