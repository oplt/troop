"""P5.4 behavioral tests for routing + execution hot paths."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.modules.orchestration.execution.durable_execution import (
    is_run_execution_claimable,
    durable_backend_status,
)
from backend.modules.orchestration.execution.policies import should_skip_agent_plan
from backend.workers import orchestration as orch_workers


class SoftTimeLimitExceeded(Exception):
    pass


def test_should_skip_agent_plan_off_mode():
    assert should_skip_agent_plan(
        plan_mode="off",
        allowed_tools=["search"],
        tool_calling_allowed=True,
        purpose="agent_plan",
    )


def test_should_skip_agent_plan_empty_tools_non_manager():
    assert should_skip_agent_plan(
        plan_mode="auto",
        allowed_tools=[],
        tool_calling_allowed=True,
        purpose="agent_plan",
    )


def test_should_skip_agent_plan_manager_keeps_planner_without_tools():
    assert not should_skip_agent_plan(
        plan_mode="auto",
        allowed_tools=[],
        tool_calling_allowed=False,
        purpose="manager_delegation",
    )


def test_should_skip_agent_plan_runs_when_tools_and_calling_enabled():
    assert not should_skip_agent_plan(
        plan_mode="auto",
        allowed_tools=["grep"],
        tool_calling_allowed=True,
        purpose="agent_plan",
    )


def test_claimable_statuses_match_durable_execution_policy():
    for status in ("queued", "failed", "pending"):
        assert is_run_execution_claimable(status) is True
    for status in ("in_progress", "completed", "cancelled", "awaiting_approval"):
        assert is_run_execution_claimable(status) is False


def test_durable_backend_status_reports_celery():
    status = durable_backend_status()
    assert status["configured"] == "celery"
    assert status["available"] is True
    assert status["checkpointed"] is True


@pytest.mark.asyncio
async def test_worker_execute_marks_in_progress_failed_on_soft_time_limit():
    run = SimpleNamespace(status="in_progress", error_message=None)
    service = MagicMock()
    service.execute_run = AsyncMock(side_effect=SoftTimeLimitExceeded())
    service.repo.get_run_for_worker = AsyncMock(return_value=run)
    service.db.commit = AsyncMock()

    db_ctx = AsyncMock()
    db_ctx.__aenter__ = AsyncMock(return_value=db_ctx)
    db_ctx.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("backend.db.session.SessionLocal", return_value=db_ctx),
        patch("backend.workers.orchestration.OrchestrationService", return_value=service),
        patch.object(orch_workers, "record_run_outcome"),
    ):
        runtime = orch_workers.OrchestrationWorkerRuntime()
        with pytest.raises(SoftTimeLimitExceeded):
            await runtime.execute("run-1", expected_owner_id="owner-1")

    assert run.status == "failed"
    assert run.error_message == "Celery soft time limit exceeded"
    service.db.commit.assert_awaited_once()
