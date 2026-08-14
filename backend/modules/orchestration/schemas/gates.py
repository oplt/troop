from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from backend.core.schemas import RequestModel
from backend.modules.orchestration.schemas.common import *  # noqa: F403

VALID_GATE_ACTIONS = frozenset(
    [
        "post_to_github",
        "open_pr",
        "mark_complete",
        "change_task_ownership",
        "write_memory",
        "use_expensive_model",
        "run_tool",
    ]
)

VALID_AUTONOMY_LEVELS = frozenset(
    ["autonomous", "semi-autonomous", "semi_autonomous", "assisted", "supervised"]
)


class GateConfigResponse(BaseModel):
    autonomy_level: str
    approval_gates: list[str]
    mandatory_approval_gates: list[str] = Field(default_factory=list)


class GateConfigUpdate(RequestModel):
    autonomy_level: str | None = None
    approval_gates: list[str] | None = None

    @field_validator("autonomy_level")
    @classmethod
    def _validate_autonomy(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_AUTONOMY_LEVELS:
            raise ValueError(f"autonomy_level must be one of {sorted(VALID_AUTONOMY_LEVELS)}")
        return v

    @field_validator("approval_gates")
    @classmethod
    def _validate_gates(cls, v: list[str] | None) -> list[str] | None:
        if v is not None:
            invalid = [g for g in v if g not in VALID_GATE_ACTIONS]
            if invalid:
                raise ValueError(
                    f"Invalid gate actions: {invalid}. Valid: {sorted(VALID_GATE_ACTIONS)}"
                )
        return v
