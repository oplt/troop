"""Pure execution policies shared by persistence and provider orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.modules.orchestration.constants import TASK_TRANSITIONS


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Bounded retry decision independent of provider or database code."""

    max_retries: int

    @classmethod
    def from_agent_policy(cls, policy: dict[str, Any] | None, agent_limit: int = 0) -> RetryPolicy:
        values = dict(policy or {})
        raw = values.get("retry_count") or values.get("retry_limit") or agent_limit
        try:
            retries = int(raw)
        except (TypeError, ValueError):
            retries = int(agent_limit or 0)
        return cls(max_retries=max(0, min(3, retries)))

    def should_retry(self, attempt: int) -> bool:
        return attempt < self.max_retries


def is_valid_task_transition(current: str, next_status: str) -> bool:
    """Return whether a state transition is allowed by the domain state machine."""

    return current == next_status or next_status in TASK_TRANSITIONS.get(current, set())


def next_retry_numbers(retry_count: int, attempt_number: int) -> tuple[int, int]:
    """Return the persisted counters for a newly queued retry."""

    return max(0, retry_count) + 1, max(0, attempt_number) + 1


def should_skip_agent_plan(
    *,
    plan_mode: str | None,
    allowed_tools: list[Any] | None,
    tool_calling_allowed: bool,
    purpose: str,
) -> bool:
    """Return True when planner LLM call should be skipped for this run/agent."""

    mode = str(plan_mode or "auto").strip().lower()
    is_manager_plan = "manager" in purpose.lower() or "delegation" in purpose.lower()
    if mode == "off":
        return True
    if not is_manager_plan and (not allowed_tools or not tool_calling_allowed):
        return True
    return False


__all__ = [
    "RetryPolicy",
    "is_valid_task_transition",
    "next_retry_numbers",
    "should_skip_agent_plan",
]
