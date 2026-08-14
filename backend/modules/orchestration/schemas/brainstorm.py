from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.core.schemas import RequestModel
from backend.modules.orchestration.schemas.common import BrainstormMode, BrainstormOutputType


class BrainstormCreate(RequestModel):
    project_id: str
    task_id: str | None = None
    moderator_agent_id: str | None = None
    topic: str = Field(min_length=3, max_length=255)
    participant_agent_ids: list[str] = Field(default_factory=list)
    mode: BrainstormMode = "exploration"
    output_type: BrainstormOutputType = "implementation_plan"
    max_rounds: int = Field(default=3, ge=1, le=10)
    max_cost_usd: float = Field(default=10, ge=0.1, le=1000)
    max_repetition_score: float = Field(default=0.92, ge=0.1, le=1.0)
    stop_conditions: dict[str, Any] = Field(default_factory=dict)


class BrainstormParticipantCreate(RequestModel):
    agent_id: str
    stance: str | None = Field(default=None, max_length=2000)


class BrainstormParticipantUpdate(RequestModel):
    stance: str | None = Field(default=None, max_length=2000)


class BrainstormArtifactResponse(BaseModel):
    artifact_kind: Literal["task_artifact", "project_document", "project_decision"]
    artifact_id: str
    output_type: str
    title: str
    content: str
    created_at: datetime


class BrainstormResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    task_id: str | None
    initiator_user_id: str
    moderator_agent_id: str | None
    topic: str
    status: str
    mode: str
    output_type: str
    max_rounds: int
    stop_conditions: dict[str, Any]
    participant_count: int = 0
    current_round: int = 0
    consensus_status: str = "open"
    latest_round_summary: str | None = None
    summary: str | None
    final_recommendation: str | None
    decision_log: list[dict[str, Any]]
    created_at: datetime
    updated_at: datetime


class BrainstormParticipantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    brainstorm_id: str
    agent_id: str
    order_index: int
    stance: str | None
    created_at: datetime


class BrainstormMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    brainstorm_id: str
    agent_id: str | None
    round_number: int
    message_type: str
    content: str
    metadata: dict[str, Any]
    created_at: datetime
