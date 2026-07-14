from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from backend.core.http_clients import ExternalHttpClientPool
from backend.modules.orchestration.router import _live_snapshot_stream
from backend.modules.rag.bulk_ingest import bulk_ingest_documents_parallel
from backend.workers.celery_app import celery_app


@pytest.mark.asyncio
async def test_external_http_pool_reuses_clients_and_closes_them() -> None:
    pool = ExternalHttpClientPool(max_clients=2)
    first = await pool.get("provider", base_url="https://example.test", timeout_seconds=3)
    second = await pool.get("provider", base_url="https://example.test", timeout_seconds=3)

    assert first is second
    assert not first.is_closed
    await pool.aclose()
    assert first.is_closed


@pytest.mark.asyncio
async def test_bulk_ingest_never_exceeds_configured_concurrency() -> None:
    user = MagicMock(id="user-1")
    active = 0
    peak = 0

    async def fake_ingest(*_args, title: str, **_kwargs):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0)
        active -= 1
        return title

    with (
        patch("backend.modules.rag.bulk_ingest.settings.RAG_BULK_INGEST_CONCURRENCY", 2),
        patch("backend.modules.rag.bulk_ingest.settings.RAG_BULK_INGEST_BATCH_SIZE", 3),
        patch("backend.modules.rag.bulk_ingest.SessionLocal") as session_local,
        patch("backend.modules.rag.bulk_ingest.OrchestrationService") as orch_cls,
        patch("backend.modules.rag.bulk_ingest.RagService") as rag_cls,
    ):
        session_local.return_value.__aenter__.return_value = AsyncMock()
        orch_cls.return_value.get_project = AsyncMock(return_value=MagicMock(id="project-1"))
        rag_cls.return_value.ingest_text = AsyncMock(side_effect=fake_ingest)
        rows = await bulk_ingest_documents_parallel(
            user,
            "project-1",
            documents=[{"title": str(i), "content": "content"} for i in range(7)],
            task_id=None,
            queue_async=True,
        )

    assert rows == [str(i) for i in range(7)]
    assert peak <= 2


@pytest.mark.asyncio
async def test_bulk_ingest_cancellation_drains_child_tasks() -> None:
    started = asyncio.Event()
    user = MagicMock(id="user-1")

    async def blocking_ingest(*_args, **_kwargs):
        started.set()
        await asyncio.Event().wait()

    with (
        patch("backend.modules.rag.bulk_ingest.settings.RAG_BULK_INGEST_CONCURRENCY", 2),
        patch("backend.modules.rag.bulk_ingest.settings.RAG_BULK_INGEST_BATCH_SIZE", 2),
        patch("backend.modules.rag.bulk_ingest.SessionLocal") as session_local,
        patch("backend.modules.rag.bulk_ingest.OrchestrationService") as orch_cls,
        patch("backend.modules.rag.bulk_ingest.RagService") as rag_cls,
    ):
        session_local.return_value.__aenter__.return_value = AsyncMock()
        orch_cls.return_value.get_project = AsyncMock(return_value=MagicMock(id="project-1"))
        rag_cls.return_value.ingest_text = AsyncMock(side_effect=blocking_ingest)
        operation = asyncio.create_task(
            bulk_ingest_documents_parallel(
                user,
                "project-1",
                documents=[{"title": "a", "content": "A"}, {"title": "b", "content": "B"}],
                task_id=None,
                queue_async=True,
            )
        )
        await started.wait()
        operation.cancel()
        with pytest.raises(asyncio.CancelledError):
            await operation


@pytest.mark.asyncio
async def test_sse_stream_checks_disconnect_and_releases_capacity() -> None:
    request = MagicMock()
    request.is_disconnected = AsyncMock(side_effect=[False, True])

    response = await _live_snapshot_stream(
        lambda: _snapshot(),
        request=request,
        stream_name="test",
    )
    chunks = [chunk async for chunk in response.body_iterator]

    assert chunks == ['event: snapshot\ndata: {"value": 1}\n\n']
    assert response.headers["cache-control"] == "no-cache, no-transform"


def test_celery_delivery_settings_bound_prefetch_and_requeue() -> None:
    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.task_reject_on_worker_lost is True
    assert celery_app.conf.worker_prefetch_multiplier == 1
    assert celery_app.conf.broker_transport_options["visibility_timeout"] == 3600


async def _snapshot() -> dict[str, int]:
    return {"value": 1}
