from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.core.schemas import RequestModel


class AgentPatternResponse(BaseModel):
    id: str
    name: str
    description: str
    category: str
    baseline_run_mode: str
    pattern_run_mode: str
    execution_overlay: dict[str, Any] = Field(default_factory=dict)


class AgentPatternStatusResponse(BaseModel):
    pattern_id: str
    status: Literal["disabled", "eval_pending", "released"]
    eval_ready: bool = False
    applied_at: datetime | None = None
    enabled_at: datetime | None = None
    last_eval_id: str | None = None
    last_advantage: dict[str, Any] | None = None


class AgentPatternProjectStatusResponse(BaseModel):
    project_id: str
    patterns: list[AgentPatternStatusResponse]


class AgentPatternApplyResponse(BaseModel):
    project_id: str
    pattern: AgentPatternResponse
    status: str
    applied_execution: dict[str, Any]


class AgentPatternBenchmarkRequest(RequestModel):
    task_id: str
    agent_id: str
    model_a: str | None = None
    model_b: str | None = None


class AgentPatternBenchmarkResponse(BaseModel):
    eval_id: str
    pattern_id: str
    task_id: str
    runs: list[dict[str, str]]


class AgentPatternEnableResponse(BaseModel):
    project_id: str
    pattern_id: str
    status: str
    enabled_at: datetime
