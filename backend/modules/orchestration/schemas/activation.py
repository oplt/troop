from __future__ import annotations

from pydantic import BaseModel


class ActivationMilestoneResponse(BaseModel):
    key: str
    label: str
    completed: bool
    completed_at: str | None = None
    seconds_from_baseline: int | None = None
    resource_type: str | None = None
    resource_id: str | None = None
    metadata: dict = {}


class ActivationNextStepResponse(BaseModel):
    key: str
    label: str
    cta: str
    path: str


class ActivationStatusResponse(BaseModel):
    workspace_id: str
    baseline_at: str
    milestones: list[ActivationMilestoneResponse]
    completed_count: int
    total_count: int
    activated: bool
    seconds_to_activate: int | None = None
    next_step: ActivationNextStepResponse | None = None
