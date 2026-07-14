from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.modules.orchestration.execution.cpu_executor import execute_code_job
from backend.workers.celery_async import await_celery_result


def test_execute_code_job_requires_docker_in_production_when_unavailable() -> None:
    with (
        patch("backend.modules.orchestration.execution.cpu_executor.settings.ORCHESTRATION_CPU_REQUIRE_DOCKER", True),
        patch("backend.modules.orchestration.execution.cpu_executor.docker_available", return_value=False),
    ):
        result = execute_code_job(
            shell_cmd="echo hi",
            cwd="/tmp",
            timeout=5,
            use_shell_wrap=True,
        )

    assert result["error"] == "docker_required_unavailable"
    assert result["sandbox"] == "unavailable"
    assert result["returncode"] == 127


def test_execute_code_job_allows_host_fallback_when_docker_not_required() -> None:
    with (
        patch("backend.modules.orchestration.execution.cpu_executor.settings.ORCHESTRATION_CPU_REQUIRE_DOCKER", False),
        patch("backend.modules.orchestration.execution.cpu_executor.docker_available", return_value=False),
        patch(
            "backend.modules.orchestration.execution.cpu_executor.subprocess.run",
            return_value=MagicMock(returncode=0, stdout="ok", stderr=""),
        ) as run_mock,
    ):
        result = execute_code_job(
            shell_cmd="echo hi",
            cwd="/tmp",
            timeout=5,
            use_shell_wrap=True,
        )

    assert result["sandbox"] == "host"
    assert result["stdout"] == "ok"
    run_mock.assert_called_once()


def test_project_sandbox_policy_requires_docker_before_host_execution() -> None:
    with (
        patch("backend.modules.orchestration.execution.cpu_executor.settings.ORCHESTRATION_CPU_REQUIRE_DOCKER", False),
        patch("backend.modules.orchestration.execution.cpu_executor.docker_available", return_value=False),
        patch("backend.modules.orchestration.execution.cpu_executor.subprocess.run") as run_mock,
    ):
        result = execute_code_job(
            shell_cmd="echo should-not-run",
            cwd="/tmp",
            timeout=5,
            use_shell_wrap=True,
            require_docker=True,
        )

    assert result["error"] == "docker_required_unavailable"
    run_mock.assert_not_called()


@pytest.mark.asyncio
async def test_await_celery_result_polls_until_ready() -> None:
    async_result = MagicMock()
    async_result.id = "task-1"
    async_result.ready.side_effect = [False, False, True]
    async_result.get.return_value = {"ok": True}

    result = await await_celery_result(async_result, timeout_seconds=2, poll_interval=0.01)

    assert result == {"ok": True}
    assert async_result.get.call_count == 1
    assert async_result.ready.call_count == 3


@pytest.mark.asyncio
async def test_await_celery_result_times_out() -> None:
    async_result = MagicMock()
    async_result.id = "task-2"
    async_result.ready.return_value = False

    with pytest.raises(TimeoutError, match="did not finish within"):
        await await_celery_result(async_result, timeout_seconds=0.05, poll_interval=0.01)
