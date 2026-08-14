from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from backend.modules.observability.metrics import (
    DB_POOL_CHECKED_OUT,
    OLDEST_IN_PROGRESS_AGE,
    QUEUE_AGE,
    QUEUE_DEPTH,
    RUNS_ACTIVE,
    STALE_IN_PROGRESS_RUNS,
    metrics_registry,
    record_db_pool_state,
    record_run_status_snapshot,
)
from backend.modules.observability.queue import _age_seconds, refresh_db_pool_metrics


def test_queue_age_normalizes_naive_and_aware_timestamps() -> None:
    now = datetime.now(UTC)
    assert _age_seconds(now - timedelta(seconds=5)) >= 4
    assert _age_seconds((now - timedelta(seconds=5)).replace(tzinfo=None)) >= 4
    assert _age_seconds(None) is None


@pytest.mark.asyncio
async def test_queue_refresh_uses_bounded_queue_names_and_durable_age(monkeypatch) -> None:
    from backend.modules.observability import queue as queue_module

    class FakeRedis:
        async def llen(self, queue: str) -> int:
            return 3 if queue == queue_module.settings.CELERY_TASK_DEFAULT_QUEUE else 0

    class Result:
        def one(self):
            return 2, datetime.now(UTC) - timedelta(seconds=12)

    class FakeDb:
        async def execute(self, _statement):
            return Result()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

    monkeypatch.setattr(queue_module, "SessionLocal", lambda: FakeDb())
    with patch.object(queue_module, "record_queue_state") as record:
        await queue_module.refresh_queue_metrics(FakeRedis())

    assert record.call_count >= 1
    assert any(
        call.kwargs.get("depth") == 2 and call.kwargs.get("oldest_age_seconds")
        for call in record.call_args_list
    )
    assert QUEUE_DEPTH and QUEUE_AGE


@pytest.mark.asyncio
async def test_run_status_refresh_records_stuck_run_gauges(monkeypatch) -> None:
    from backend.modules.observability import queue as queue_module

    class CountResult:
        def all(self):
            return [("in_progress", 3), ("queued", 2)]

    class ScalarResult:
        def __init__(self, value):
            self._value = value

        def scalar_one(self):
            return self._value

    class FakeDb:
        def __init__(self):
            self.calls = 0

        async def execute(self, _statement):
            self.calls += 1
            if self.calls == 1:
                return CountResult()
            if self.calls == 2:
                return ScalarResult(1)
            return ScalarResult(datetime.now(UTC) - timedelta(minutes=90))

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

    monkeypatch.setattr(queue_module, "SessionLocal", lambda: FakeDb())
    metrics_registry.reset()
    await queue_module.refresh_run_status_metrics()
    rendered = metrics_registry.render_prometheus()
    assert f"# TYPE {RUNS_ACTIVE} gauge" in rendered
    assert 'status="in_progress"' in rendered
    assert f"# TYPE {STALE_IN_PROGRESS_RUNS} gauge" in rendered
    assert f"# TYPE {OLDEST_IN_PROGRESS_AGE} gauge" in rendered
    metrics_registry.reset()


def test_db_pool_metrics_render_saturation_gauges(monkeypatch) -> None:
    from backend.modules.observability import queue as queue_module

    class FakePool:
        def checkedout(self):
            return 4

        def overflow(self):
            return 2

        def size(self):
            return 5

    class FakeEngine:
        pool = FakePool()

    monkeypatch.setattr(queue_module.engine, "sync_engine", FakeEngine())
    metrics_registry.reset()
    refresh_db_pool_metrics()
    rendered = metrics_registry.render_prometheus()
    assert f"# TYPE {DB_POOL_CHECKED_OUT} gauge" in rendered
    assert "troop_db_pool_checked_out" in rendered and " 4" in rendered
    metrics_registry.reset()


def test_operational_metric_helpers_are_bounded() -> None:
    metrics_registry.reset()
    record_run_status_snapshot(
        {"in_progress": 2, "queued": 1},
        stale_in_progress=1,
        oldest_in_progress_age_seconds=120.0,
    )
    record_db_pool_state(role="api", checked_out=3, overflow=1, pool_size=10)
    rendered = metrics_registry.render_prometheus()
    assert STALE_IN_PROGRESS_RUNS in rendered
    assert DB_POOL_CHECKED_OUT in rendered
    metrics_registry.reset()
