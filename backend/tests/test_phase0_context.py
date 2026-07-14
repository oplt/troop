from __future__ import annotations

from types import SimpleNamespace

from backend.core.request_context import (
    bind_context,
    context_from_headers,
    get_request_context,
    sanitize_context_value,
    set_context,
)
from backend.tools.phase0_baseline import percentile, summarize_timings
from backend.workers.context import (
    _bind_task_context,
    _restore_task_context,
    task_context_headers,
)


def test_context_is_scoped_and_restored() -> None:
    set_context(user_id=None, run_id=None)
    assert get_request_context().user_id is None

    with bind_context(user_id="user-1", run_id="run-1"):
        context = get_request_context()
        assert context.user_id == "user-1"
        assert context.run_id == "run-1"
        assert context.as_task_headers() == {"user_id": "user-1", "run_id": "run-1"}

    assert get_request_context().user_id is None
    assert get_request_context().run_id is None


def test_context_values_are_allowlisted_and_sanitized() -> None:
    assert sanitize_context_value("  abc\n123  ") == "abc123"
    assert sanitize_context_value("x" * 200) == "x" * 128
    assert context_from_headers(
        {"run_id": "run-1", "secret": "must-not-cross", "user_id": "user-1"}
    ) == {"run_id": "run-1", "user_id": "user-1"}


def test_celery_context_uses_headers_and_restores_after_task() -> None:
    task = SimpleNamespace(
        name="backend.workers.orchestration.run_task",
        request=SimpleNamespace(headers={"run_id": "run-1", "project_id": "project-1"}),
    )
    _bind_task_context("celery-job-1", task)
    try:
        context = get_request_context()
        assert context.job_id == "celery-job-1"
        assert context.task_name == task.name
        assert context.run_id == "run-1"
        assert context.project_id == "project-1"
        assert task_context_headers()["run_id"] == "run-1"
    finally:
        _restore_task_context("celery-job-1")
    assert get_request_context().job_id is None


def test_percentiles_are_interpolated_and_empty_is_explicit() -> None:
    values = [10.0, 20.0, 30.0, 40.0, 50.0]
    assert percentile(values, 0.50) == 30.0
    assert percentile(values, 0.95) == 48.0
    assert percentile([], 0.95) is None
    assert summarize_timings(values)["p99_ms"] == 49.6
