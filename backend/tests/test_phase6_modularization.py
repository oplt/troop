from __future__ import annotations

from backend.modules.orchestration.execution.policies import (
    RetryPolicy,
    is_valid_task_transition,
    next_retry_numbers,
)


def test_retry_policy_is_bounded_and_provider_independent() -> None:
    assert RetryPolicy.from_agent_policy({"retry_count": 99}, 2).max_retries == 3
    assert RetryPolicy.from_agent_policy({"retry_count": "invalid"}, 2).max_retries == 2
    assert RetryPolicy.from_agent_policy({}, 2).should_retry(1) is True
    assert RetryPolicy.from_agent_policy({}, 2).should_retry(2) is False


def test_task_state_machine_policy_is_explicit() -> None:
    assert is_valid_task_transition("queued", "planned")
    assert is_valid_task_transition("queued", "queued")
    assert not is_valid_task_transition("completed", "in_progress")


def test_retry_persistence_counters_are_monotonic() -> None:
    assert next_retry_numbers(2, 4) == (3, 5)
    assert next_retry_numbers(-1, -1) == (1, 1)


def test_agent_routes_use_public_presenters() -> None:
    from pathlib import Path

    backend_root = Path(__file__).resolve().parents[1]
    source = (backend_root / "app/agents/router.py").read_text()
    assert "from backend.modules.orchestration.router import" not in source
    assert "to_agent_response" in source
