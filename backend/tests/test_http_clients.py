from __future__ import annotations

import asyncio
from unittest.mock import patch

import httpx
import pytest
from backend.core.external_http import external_timeout
from backend.core.http_clients import (
    ExternalHttpClientPool,
    _RequestTimeoutClient,
    managed_http_client,
)


@pytest.mark.asyncio
async def test_external_http_pool_reuses_clients_and_closes_them() -> None:
    pool = ExternalHttpClientPool(max_clients=2)
    first, first_key = await pool.acquire("provider", base_url="https://example.test")
    second, second_key = await pool.acquire("provider", base_url="https://example.test")

    assert first is second
    assert first_key == second_key
    assert not first.is_closed
    await pool.release(first_key)
    await pool.release(second_key)
    await pool.aclose()
    assert first.is_closed


@pytest.mark.asyncio
async def test_varied_request_timeouts_share_one_pooled_client() -> None:
    pool = ExternalHttpClientPool(max_clients=4)
    seen: set[int] = set()

    with patch("backend.core.http_clients.external_http_clients", pool):
        for timeout in range(1, 1001):
            async with managed_http_client("web-tools", timeout_seconds=float(timeout)) as client:
                underlying = client._client if isinstance(client, _RequestTimeoutClient) else client
                seen.add(id(underlying))

    assert len(seen) == 1
    assert len(pool._entries) == 1
    await pool.aclose()


@pytest.mark.asyncio
async def test_different_purposes_create_distinct_clients() -> None:
    pool = ExternalHttpClientPool(max_clients=4)
    first, first_key = await pool.acquire("alpha")
    second, second_key = await pool.acquire("beta")

    assert first is not second
    assert len(pool._entries) == 2

    await pool.release(first_key)
    await pool.release(second_key)
    await pool.aclose()


@pytest.mark.asyncio
async def test_pool_evicts_idle_client_when_at_capacity() -> None:
    pool = ExternalHttpClientPool(max_clients=2)
    first, first_key = await pool.acquire("purpose-a")
    await pool.release(first_key)
    second, second_key = await pool.acquire("purpose-b")
    await pool.release(second_key)

    third, third_key = await pool.acquire("purpose-c")
    assert len(pool._entries) == 2
    assert third_key not in {first_key, second_key}

    await pool.release(third_key)
    await pool.aclose()
    assert pool.stats()["clients_closed"] >= 2


@pytest.mark.asyncio
async def test_pool_rejects_when_all_clients_are_in_use() -> None:
    pool = ExternalHttpClientPool(max_clients=1)
    _client, key = await pool.acquire("only")

    with pytest.raises(RuntimeError, match="capacity exhausted"):
        await pool.acquire("another")

    assert pool.stats()["capacity_rejections"] == 1
    await pool.release(key)
    await pool.aclose()


@pytest.mark.asyncio
async def test_request_timeout_wrapper_applies_per_request_timeout() -> None:
    pool = ExternalHttpClientPool(max_clients=2)
    captured: list[object] = []

    class RecordingTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            captured.append(request.extensions.get("timeout"))
            return httpx.Response(200, request=request)

    client, key = await pool.acquire("timed")
    client._transport = RecordingTransport()
    timeout_client = _RequestTimeoutClient(client, external_timeout(12.0))
    await timeout_client.get("https://example.test/resource")

    assert captured
    timeout = captured[0]
    assert isinstance(timeout, dict)
    assert timeout["read"] == 12.0

    await pool.release(key)
    await pool.aclose()


@pytest.mark.asyncio
async def test_concurrent_acquires_for_same_key_share_one_client() -> None:
    pool = ExternalHttpClientPool(max_clients=4)
    barrier = asyncio.Barrier(10)
    clients: list[httpx.AsyncClient] = []

    async def worker() -> None:
        client, key = await pool.acquire("shared")
        await barrier.wait()
        clients.append(client)
        await pool.release(key)

    await asyncio.gather(*(worker() for _ in range(10)))
    assert len({id(client) for client in clients}) == 1
    assert pool._entries[("shared", "")].in_use == 0
    await pool.aclose()
