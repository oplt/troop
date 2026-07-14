from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from backend.workers import orchestration as orch_workers
from backend.workers.celery_app import celery_app
from backend.workers.retry import CELERY_TRANSIENT_EXCEPTIONS


def test_orchestration_celery_tasks_use_transient_autoretry():
    tasks = [
        orch_workers.run_orchestration_task,
        orch_workers.process_memory_ingest_jobs,
        orch_workers.process_github_webhook_event,
        orch_workers.memory_expiration_sweep,
    ]
    for task in tasks:
        assert task.autoretry_for == CELERY_TRANSIENT_EXCEPTIONS


def test_code_execution_is_routed_to_cpu_queue():
    route = celery_app.conf.task_routes["backend.workers.orchestration.run_code_execution"]
    assert route["queue"] == orch_workers.settings.CELERY_QUEUE_CPU


def test_queue_orchestration_run_eager_executes_inline():
    runtime = MagicMock()
    runtime.execute = AsyncMock()

    with (
        patch.object(orch_workers.settings, "CELERY_TASK_ALWAYS_EAGER", True),
        patch.object(orch_workers, "OrchestrationWorkerRuntime", return_value=runtime),
        patch.object(orch_workers, "asyncio") as asyncio_mod,
    ):
        asyncio_mod.get_running_loop.side_effect = RuntimeError
        asyncio_mod.run = MagicMock()
        orch_workers.queue_orchestration_run("run-123")

    asyncio_mod.run.assert_called_once()


def test_queue_memory_ingest_jobs_eager_executes_inline():
    runtime = MagicMock()
    runtime.process_memory_ingest_jobs = AsyncMock()

    with (
        patch.object(orch_workers.settings, "CELERY_TASK_ALWAYS_EAGER", True),
        patch.object(orch_workers, "OrchestrationWorkerRuntime", return_value=runtime),
        patch.object(orch_workers, "asyncio") as asyncio_mod,
    ):
        asyncio_mod.get_running_loop.side_effect = RuntimeError
        asyncio_mod.run = MagicMock()
        orch_workers.queue_memory_ingest_jobs()

    asyncio_mod.run.assert_called_once()
