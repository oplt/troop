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
        return cls(max_retries=max(0, min(10, retries)))

    def should_retry(self, attempt: int) -> bool:
        return attempt < self.max_retries


def is_valid_task_transition(current: str, next_status: str) -> bool:
    """Return whether a state transition is allowed by the domain state machine."""

    return current == next_status or next_status in TASK_TRANSITIONS.get(current, set())


def next_retry_numbers(retry_count: int, attempt_number: int) -> tuple[int, int]:
    """Return the persisted counters for a newly queued retry."""

    return max(0, retry_count) + 1, max(0, attempt_number) + 1


__all__ = [
    "RetryPolicy",
    "is_valid_task_transition",
    "next_retry_numbers",
]
