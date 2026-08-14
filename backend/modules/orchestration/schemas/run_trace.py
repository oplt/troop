"""Safe run-trace span schemas (OBS-002A)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RunTraceSpanKind(StrEnum):
    TRIGGER = "trigger"
    NODE = "node"
    MODEL_ATTEMPT = "model_attempt"
    TOOL_AUTH = "tool_auth"
    APPROVAL = "approval"
    TOOL_EFFECT = "tool_effect"
    RETRY_CHECKPOINT = "retry_checkpoint"


class RunTraceRestrictedRef(BaseModel):
    """Indicates restricted/raw payload exists but is omitted from the safe view."""

    has_restricted: bool = False
    restricted_fields: list[str] = Field(default_factory=list)


class RunTraceSpanSafe(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    run_id: str
    kind: RunTraceSpanKind
    title: str
    status: str
    message: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
    safe_payload: dict[str, Any] = Field(default_factory=dict)
    restricted: RunTraceRestrictedRef = Field(default_factory=RunTraceRestrictedRef)
    source_event_id: str | None = None
    source_event_type: str | None = None
    parent_span_id: str | None = None
    tokens_input: int = 0
    tokens_output: int = 0
    cost_usd_micros: int = 0


class RunTracePageMeta(BaseModel):
    run_id: str
    span_kinds_present: list[str] = Field(default_factory=list)
    truncated: bool = False


class RunTracePageResponse(BaseModel):
    items: list[RunTraceSpanSafe]
    next_cursor: object | None = None
    meta: RunTracePageMeta
