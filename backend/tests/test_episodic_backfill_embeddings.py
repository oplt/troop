"""PERF-002: episodic backfill embedding batching."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from backend.modules.memory.episodic_jobs import embed_episodic_index_rows_batched
from backend.modules.memory.models import normalize_embedding_for_vector
from backend.modules.memory.service import OrchestrationMemoryServiceMixin


class _MemoryHarness(OrchestrationMemoryServiceMixin):
    def __init__(self, db: MagicMock, repo: MagicMock) -> None:
        self.db = db
        self.repo = repo
        self.ai_providers = MagicMock()


def _rows_and_texts(count: int) -> tuple[list[SimpleNamespace], list[str]]:
    rows = [
        SimpleNamespace(source_id=f"row-{index}", embedding_vector=None)
        for index in range(count)
    ]
    texts = [f"t{index}" for index in range(count)]
    return rows, texts


@pytest.mark.asyncio
async def test_embed_episodic_index_rows_batched_chunks_provider_calls() -> None:
    embed = AsyncMock(
        side_effect=lambda texts: [[float(len(text))] for text in texts],
    )
    rows, texts = _rows_and_texts(200)

    embedded = await embed_episodic_index_rows_batched(
        SimpleNamespace(embed_texts=embed),
        rows,
        texts,
        batch_size=50,
    )

    assert embedded == 200
    assert embed.await_count == 4
    assert rows[0].embedding_vector == normalize_embedding_for_vector([2.0])
    assert rows[199].embedding_vector == normalize_embedding_for_vector([4.0])


@pytest.mark.asyncio
async def test_embed_episodic_index_rows_batched_scales_to_two_thousand_rows() -> None:
    embed = AsyncMock(
        side_effect=lambda texts: [[1.0, 0.0] for _ in texts],
    )
    rows, texts = _rows_and_texts(2000)

    embedded = await embed_episodic_index_rows_batched(
        SimpleNamespace(embed_texts=embed),
        rows,
        texts,
        batch_size=64,
    )

    assert embedded == 2000
    assert embed.await_count == 32


@pytest.mark.asyncio
async def test_embed_episodic_index_rows_batched_falls_back_per_row_on_batch_failure() -> None:
    async def embed_texts(texts: list[str]) -> list[list[float]]:
        if len(texts) > 1:
            raise RuntimeError("batch unavailable")
        return [[0.5, 0.25]]

    rows, texts = _rows_and_texts(3)
    embedded = await embed_episodic_index_rows_batched(
        SimpleNamespace(embed_texts=embed_texts),
        rows,
        texts,
        batch_size=10,
    )

    assert embedded == 3
    assert all(row.embedding_vector is not None for row in rows)


@pytest.mark.asyncio
async def test_embed_episodic_index_rows_batched_skips_failed_rows_in_batch() -> None:
    async def embed_texts(texts: list[str]) -> list[list[float]]:
        if len(texts) > 1:
            raise ValueError("batch failed")
        if texts[0] == "bad":
            raise ValueError("invalid text")
        return [[1.0]]

    rows = [
        SimpleNamespace(source_id="good-1", embedding_vector=None),
        SimpleNamespace(source_id="bad", embedding_vector=None),
        SimpleNamespace(source_id="good-2", embedding_vector=None),
    ]
    texts = ["good one", "bad", "good two"]

    embedded = await embed_episodic_index_rows_batched(
        SimpleNamespace(embed_texts=embed_texts),
        rows,
        texts,
        batch_size=3,
    )

    assert embedded == 2
    assert rows[0].embedding_vector is not None
    assert rows[1].embedding_vector is None
    assert rows[2].embedding_vector is not None


@pytest.mark.asyncio
async def test_backfill_episodic_search_index_batches_embedding_calls() -> None:
    from backend.modules.identity_access.models import User
    from backend.modules.orchestration.models import RunEvent

    db = MagicMock()
    repo = MagicMock()
    harness = _MemoryHarness(db, repo)
    harness.get_project = AsyncMock(
        return_value=SimpleNamespace(owner_id="owner-1", settings_json={})
    )

    events = [
        RunEvent(
            id=f"ev-{index}",
            run_id="run-1",
            message=f"message {index}",
            created_at=MagicMock(),
        )
        for index in range(120)
    ]
    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = events
    db.execute = AsyncMock(return_value=execute_result)
    db.commit = AsyncMock()
    repo.list_episodic_index_rows_for_sources = AsyncMock(return_value=[])

    created_rows: list[SimpleNamespace] = []

    async def create_row(**kwargs):
        row = SimpleNamespace(
            source_id=kwargs["source_id"],
            embedding_vector=None,
        )
        created_rows.append(row)
        return row

    repo.create_episodic_search_index_row = AsyncMock(side_effect=create_row)
    embed = AsyncMock(side_effect=lambda texts: [[1.0, 0.0] for _ in texts])
    harness.ai_providers.embed_texts = embed

    user = User(id="owner-1", email="owner@example.com")
    count = await harness.backfill_episodic_search_index(user, "project-1", limit=120)

    assert count == 120
    assert embed.await_count == 2
    assert all(row.embedding_vector is not None for row in created_rows)
