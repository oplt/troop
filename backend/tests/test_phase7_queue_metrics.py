from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from backend.modules.observability.metrics import QUEUE_AGE, QUEUE_DEPTH
from backend.modules.observability.queue import _age_seconds


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
