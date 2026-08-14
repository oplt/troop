from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.core.schemas import RequestModel
from backend.modules.orchestration.schemas.common import *  # noqa: F403


class EvalRecordCreate(RequestModel):
    name: str = Field(min_length=1, max_length=255)
    task_id: str | None = None
    agent_a_id: str | None = None
    agent_b_id: str | None = None
    model_a: str | None = None
    model_b: str | None = None


class EvalRecordUpdate(RequestModel):
    winner: str | None = None
    score_a: float | None = None
    score_b: float | None = None
    criteria_met_a: bool | None = None
    criteria_met_b: bool | None = None
    notes: str | None = None


class EvalRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    task_id: str | None
    name: str
    run_a_id: str | None
    run_b_id: str | None
    agent_a_id: str | None
    agent_b_id: str | None
    model_a: str | None
    model_b: str | None
    winner: str | None
    score_a: float | None
    score_b: float | None
    criteria_met_a: bool | None
    criteria_met_b: bool | None
    notes: str | None
    metadata_json: dict
    created_at: datetime
    updated_at: datetime


class EvalLeaderboardEntryResponse(BaseModel):
    agent_id: str
    agent_name: str
    wins: int
    losses: int
    ties: int
    total: int
    win_rate: float
    avg_score: float
    avg_cost_usd: float
    avg_latency_ms: float


class ReplayRunRequest(RequestModel):
    from_event_index: int = Field(default=0, ge=0)
    model_name: str | None = None


class CostAggregationResponse(BaseModel):
    period: str
    by_project: list[dict[str, Any]]
    by_agent: list[dict[str, Any]]
    by_task: list[dict[str, Any]] = Field(default_factory=list)
    by_provider: list[dict[str, Any]]
    most_expensive_runs: list[dict[str, Any]]
    total_cost_usd: float
    total_tokens: int
