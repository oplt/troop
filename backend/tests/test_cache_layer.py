from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from backend.core.cache import (
    embedding_cache_key,
    rag_retrieval_cache_key,
    session_cache_key,
)
from backend.modules.ai.providers import AiProviderRegistry
from backend.modules.rag.schemas import RagChunkMatch


def test_session_cache_key_is_scoped_to_user_and_session():
    assert session_cache_key("user-1", "sess-1") == "cache:session:user-1:sess-1"


def test_embedding_cache_key_hashes_text_and_includes_model():
    key_a = embedding_cache_key("hello world", "text-embedding-3-small")
    key_b = embedding_cache_key("hello world", "text-embedding-3-small")
    key_c = embedding_cache_key("other", "text-embedding-3-small")
    assert key_a == key_b
    assert key_a != key_c
    assert key_a.startswith("cache:emb:text-embedding-3-small:")


def test_rag_retrieval_cache_key_includes_filters():
    key = rag_retrieval_cache_key(
        "project-1",
        "How does pgvector work?",
        task_id="task-1",
        source_kind="upload",
        include_decisions=True,
        limit=5,
    )
    assert key.startswith("cache:rag:retrieve:project-1:")


@pytest.mark.asyncio
async def test_get_cached_session_valid_returns_none_on_miss():
    with patch("backend.core.cache.redis_client.get", new=AsyncMock(return_value=None)):
        from backend.core.cache import get_cached_session_valid

        assert await get_cached_session_valid("u1", "s1") is None


@pytest.mark.asyncio
async def test_ai_provider_registry_uses_embedding_cache():
    registry = AiProviderRegistry()
    provider = registry.get("local")
    with (
        patch.object(
            provider, "embed_texts", new=AsyncMock(return_value=[[0.1, 0.2]])
        ) as embed_mock,
        patch(
            "backend.modules.ai.providers.registry.get_cached_embeddings",
            new=AsyncMock(return_value=[None]),
        ),
        patch("backend.modules.ai.providers.registry.set_cached_embeddings", new=AsyncMock()) as set_mock,
    ):
        vectors = await registry.embed_texts(["cached text"])
    assert vectors == [[0.1, 0.2]]
    embed_mock.assert_awaited_once()
    set_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_rag_retrieval_cache_roundtrip_helpers():
    from backend.core.cache import get_cached_rag_retrieval, set_cached_rag_retrieval

    match = RagChunkMatch(
        chunk_id="c1",
        document_id="d1",
        title="README.md",
        content="Troop retrieval cache",
        chunk_index=0,
        score=0.88,
    )
    key = rag_retrieval_cache_key(
        "p1",
        "Troop",
        task_id=None,
        source_kind=None,
        include_decisions=False,
        limit=3,
    )
    stored: dict[str, str] = {}

    async def _setex(name, ttl, value):
        stored[name] = value

    async def _get(name):
        return stored.get(name)

    with (
        patch("backend.core.cache.redis_client.setex", side_effect=_setex),
        patch("backend.core.cache.redis_client.get", side_effect=_get),
    ):
        await set_cached_rag_retrieval(key, [match])
        payload = await get_cached_rag_retrieval(key)
    assert payload is not None
    assert payload[0]["chunk_id"] == "c1"
    assert payload[0]["content"] == "Troop retrieval cache"


@pytest.mark.asyncio
async def test_project_acl_cache_roundtrip():
    from backend.core.cache import get_cached_project_acl, set_cached_project_acl

    stored: dict[str, str] = {}

    async def _setex(name, ttl, value):
        stored[name] = value

    async def _get(name):
        return stored.get(name)

    with (
        patch("backend.core.cache.redis_client.setex", side_effect=_setex),
        patch("backend.core.cache.redis_client.get", side_effect=_get),
    ):
        assert await get_cached_project_acl("u1", "p1") is None
        await set_cached_project_acl("u1", "p1", allowed=True)
        assert await get_cached_project_acl("u1", "p1") is True
        await set_cached_project_acl("u1", "p1", allowed=False)
        assert await get_cached_project_acl("u1", "p1") is False


@pytest.mark.asyncio
async def test_memory_settings_cache_roundtrip():
    from backend.core.cache import get_cached_memory_settings, set_cached_memory_settings

    stored: dict[str, str] = {}

    async def _setex(name, ttl, value):
        stored[name] = value

    async def _get(name):
        return stored.get(name)

    payload = {"deep_recall_mode": True}
    with (
        patch("backend.core.cache.redis_client.setex", side_effect=_setex),
        patch("backend.core.cache.redis_client.get", side_effect=_get),
    ):
        await set_cached_memory_settings("p1", payload)
        assert await get_cached_memory_settings("p1") == payload


@pytest.mark.asyncio
async def test_singleflight_coalesces_concurrent_cache_fills():
    from backend.core.cache import CachePolicy, cache_get_or_set_json

    stored: dict[str, str] = {}
    fills = 0

    async def _get(name):
        return stored.get(name)

    async def _setex(name, _ttl, value):
        stored[name] = value

    async def _fill():
        nonlocal fills
        fills += 1
        await asyncio.sleep(0)
        return {"value": "filled"}

    policy = CachePolicy("test_fill", ttl_seconds=60, jitter_ratio=0)
    with (
        patch("backend.core.cache.redis_client.get", side_effect=_get),
        patch("backend.core.cache.redis_client.setex", side_effect=_setex),
    ):
        values = await asyncio.gather(
            *(cache_get_or_set_json("shared", _fill, policy=policy) for _ in range(100))
        )
    assert fills == 1
    assert values == [{"value": "filled"}] * 100


@pytest.mark.asyncio
async def test_singleflight_bounds_map_after_many_unique_keys() -> None:
    from backend.core.cache import AsyncSingleFlight

    flight = AsyncSingleFlight(max_keys=128)
    for index in range(5001):
        assert await flight.run(f"key-{index}", AsyncMock(return_value=index)) == index
    assert len(flight._locks) <= 128


@pytest.mark.asyncio
async def test_singleflight_never_evicts_active_locked_key() -> None:
    from backend.core.cache import AsyncSingleFlight

    flight = AsyncSingleFlight(max_keys=8)
    started = asyncio.Event()
    release = asyncio.Event()

    async def pinned_loader() -> str:
        started.set()
        await release.wait()
        return "pinned"

    pinned_task = asyncio.create_task(flight.run("pinned", pinned_loader))
    await started.wait()

    for index in range(200):
        await flight.run(f"filler-{index}", AsyncMock(return_value=index))

    assert "pinned" in flight._locks
    release.set()
    assert await pinned_task == "pinned"
    assert len(flight._locks) <= 8


@pytest.mark.asyncio
async def test_read_through_policy_stores_negative_result_with_short_policy():
    from backend.core.cache import CachePolicy, cache_get_or_set_json

    stored: dict[str, tuple[int, str]] = {}
    fills = 0

    async def _get(name):
        entry = stored.get(name)
        return entry[1] if entry else None

    async def _setex(name, ttl, value):
        stored[name] = (ttl, value)

    async def _fill():
        nonlocal fills
        fills += 1
        return None

    policy = CachePolicy("negative_test", ttl_seconds=100, negative_ttl_seconds=7, jitter_ratio=0)
    with (
        patch("backend.core.cache.redis_client.get", side_effect=_get),
        patch("backend.core.cache.redis_client.setex", side_effect=_setex),
    ):
        assert await cache_get_or_set_json("missing", _fill, policy=policy) is None
        assert await cache_get_or_set_json("missing", _fill, policy=policy) is None
    assert fills == 1
    assert stored["missing"][0] == 7


@pytest.mark.asyncio
async def test_project_acl_generation_invalidation_does_not_scan_keys():
    from backend.core.cache import (
        get_cached_project_acl,
        invalidate_project_acl_cache_for_project,
        set_cached_project_acl,
    )

    stored: dict[str, str] = {}
    generations: dict[str, int] = {}

    async def _get(name):
        if name.startswith("cache:generation:"):
            return str(generations.get(name, 1))
        return stored.get(name)

    async def _setex(name, _ttl, value):
        stored[name] = value

    async def _incr(name):
        generations[name] = generations.get(name, 1) + 1
        return generations[name]

    with (
        patch("backend.core.cache.redis_client.get", side_effect=_get),
        patch("backend.core.cache.redis_client.setex", side_effect=_setex),
        patch("backend.core.cache.redis_client.incr", side_effect=_incr),
    ):
        await set_cached_project_acl("u1", "p1", allowed=True)
        assert await get_cached_project_acl("u1", "p1") is True
        await invalidate_project_acl_cache_for_project("p1")
        assert await get_cached_project_acl("u1", "p1") is None


@pytest.mark.asyncio
async def test_versioned_rag_invalidation_uses_generation_bump():
    from backend.core.cache import (
        get_cached_rag_retrieval,
        invalidate_project_rag_retrieval_cache,
        rag_retrieval_cache_key,
        set_cached_rag_retrieval,
    )

    stored: dict[str, str] = {}
    generations: dict[str, int] = {}

    async def _get(name):
        if name.startswith("cache:generation:"):
            return str(generations.get(name, 1))
        return stored.get(name)

    async def _setex(name, _ttl, value):
        stored[name] = value

    async def _incr(name):
        generations[name] = generations.get(name, 1) + 1
        return generations[name]

    key = rag_retrieval_cache_key(
        "p1", "query", task_id=None, source_kind=None, include_decisions=False, limit=3
    )
    with (
        patch("backend.core.cache.redis_client.get", side_effect=_get),
        patch("backend.core.cache.redis_client.setex", side_effect=_setex),
        patch("backend.core.cache.redis_client.incr", side_effect=_incr),
    ):
        await set_cached_rag_retrieval(key, [])
        assert await get_cached_rag_retrieval(key) == []
        await invalidate_project_rag_retrieval_cache("p1")
        assert await get_cached_rag_retrieval(key) is None


@pytest.mark.asyncio
async def test_memory_context_cache_roundtrip_and_generation_invalidate():
    from backend.core.cache import (
        get_cached_memory_context,
        invalidate_project_memory_context_cache,
        set_cached_memory_context,
    )

    stored: dict[str, str] = {}
    generations: dict[str, int] = {}

    async def _get(name):
        if name.startswith("cache:generation:"):
            return str(generations.get(name, 1))
        return stored.get(name)

    async def _setex(name, _ttl, value):
        stored[name] = value

    async def _incr(name):
        generations[name] = generations.get(name, 1) + 1
        return generations[name]

    with (
        patch("backend.core.cache.redis_client.get", side_effect=_get),
        patch("backend.core.cache.redis_client.setex", side_effect=_setex),
        patch("backend.core.cache.redis_client.incr", side_effect=_incr),
    ):
        await set_cached_memory_context("p1", "fp1", {"knowledge": "docs"})
        assert await get_cached_memory_context("p1", "fp1") == {"knowledge": "docs"}
        await invalidate_project_memory_context_cache("p1")
        assert await get_cached_memory_context("p1", "fp1") is None


def test_compute_documents_etag_changes_when_rows_change():
    from types import SimpleNamespace

    from backend.core.http_cache import compute_documents_etag

    row_a = SimpleNamespace(
        id="d1", updated_at=None, created_at=None, chunk_count=1, ingestion_status="completed"
    )
    row_b = SimpleNamespace(
        id="d1", updated_at=None, created_at=None, chunk_count=2, ingestion_status="completed"
    )
    assert compute_documents_etag([row_a]) != compute_documents_etag([row_b])
