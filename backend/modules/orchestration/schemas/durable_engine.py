from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DurableEngineReviewResponse(BaseModel):
    generated_at: str
    owner_id: str
    window_days: int
    evidence: dict[str, Any]
    evaluation: dict[str, Any]
    recovery_benchmark: dict[str, Any] | None = None
    policy: dict[str, Any] = Field(default_factory=dict)


class DurableRecoveryBenchmarkResponse(BaseModel):
    interpretation: str
    current_path: dict[str, Any]
    hypothetical_durable_engine: dict[str, Any]
    comparison: dict[str, Any]
