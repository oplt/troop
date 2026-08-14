"""Lifecycle-managed async HTTP clients for external integrations."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

import httpx

from backend.core.config import settings
from backend.core.external_http import external_timeout


@dataclass(slots=True)
class _PooledClient:
    client: httpx.AsyncClient
    last_used_at: float = field(default_factory=time.monotonic)
    in_use: int = 0


class _RequestTimeoutClient:
    """Apply a default request timeout without creating a separate pooled client."""

    __slots__ = ("_client", "_timeout")

    def __init__(self, client: httpx.AsyncClient, timeout: httpx.Timeout) -> None:
        self._client = client
        self._timeout = timeout

    async def request(self, method: str, url: httpx.URL | str, **kwargs: object) -> httpx.Response:
        if kwargs.get("timeout") is None:
            kwargs["timeout"] = self._timeout
        return await self._client.request(method, url, **kwargs)

    async def get(self, url: httpx.URL | str, **kwargs: object) -> httpx.Response:
        if kwargs.get("timeout") is None:
            kwargs["timeout"] = self._timeout
        return await self._client.get(url, **kwargs)

    async def post(self, url: httpx.URL | str, **kwargs: object) -> httpx.Response:
        if kwargs.get("timeout") is None:
            kwargs["timeout"] = self._timeout
        return await self._client.post(url, **kwargs)

    async def put(self, url: httpx.URL | str, **kwargs: object) -> httpx.Response:
        if kwargs.get("timeout") is None:
            kwargs["timeout"] = self._timeout
        return await self._client.put(url, **kwargs)

    async def patch(self, url: httpx.URL | str, **kwargs: object) -> httpx.Response:
        if kwargs.get("timeout") is None:
            kwargs["timeout"] = self._timeout
        return await self._client.patch(url, **kwargs)

    async def delete(self, url: httpx.URL | str, **kwargs: object) -> httpx.Response:
        if kwargs.get("timeout") is None:
            kwargs["timeout"] = self._timeout
        return await self._client.delete(url, **kwargs)

    async def head(self, url: httpx.URL | str, **kwargs: object) -> httpx.Response:
        if kwargs.get("timeout") is None:
            kwargs["timeout"] = self._timeout
        return await self._client.head(url, **kwargs)

    async def options(self, url: httpx.URL | str, **kwargs: object) -> httpx.Response:
        if kwargs.get("timeout") is None:
            kwargs["timeout"] = self._timeout
        return await self._client.options(url, **kwargs)

    def __getattr__(self, name: str) -> object:
        return getattr(self._client, name)


class ExternalHttpClientPool:
    """Reuse bounded connection pools without sharing mutable auth headers."""

    def __init__(self, *, max_clients: int | None = None) -> None:
        self._entries: dict[tuple[str, str], _PooledClient] = {}
        self._lock = asyncio.Lock()
        self._max_clients = max_clients or settings.EXTERNAL_HTTP_MAX_CLIENTS
        self._clients_created = 0
        self._clients_closed = 0
        self._capacity_rejections = 0

    @staticmethod
    def _client_key(purpose: str, *, base_url: str = "") -> tuple[str, str]:
        return (str(purpose), str(base_url or ""))

    @staticmethod
    def _create_client(*, base_url: str = "") -> httpx.AsyncClient:
        client_kwargs: dict[str, object] = {
            "timeout": external_timeout(settings.EXTERNAL_HTTP_MAX_TIMEOUT_SECONDS),
            "limits": httpx.Limits(
                max_connections=settings.EXTERNAL_HTTP_MAX_CONNECTIONS,
                max_keepalive_connections=settings.EXTERNAL_HTTP_MAX_KEEPALIVE_CONNECTIONS,
            ),
        }
        if base_url:
            client_kwargs["base_url"] = base_url
        return httpx.AsyncClient(**client_kwargs)

    def _record_metrics(self) -> None:
        from backend.modules.observability.metrics import record_external_http_pool_state

        record_external_http_pool_state(
            client_count=len(self._entries),
            clients_created=self._clients_created,
            clients_closed=self._clients_closed,
            capacity_rejections=self._capacity_rejections,
        )

    async def _evict_idle_lru(self) -> bool:
        idle = [(key, entry) for key, entry in self._entries.items() if entry.in_use == 0]
        if not idle:
            return False
        key, entry = min(idle, key=lambda item: item[1].last_used_at)
        await entry.client.aclose()
        del self._entries[key]
        self._clients_closed += 1
        return True

    async def acquire(
        self,
        purpose: str,
        *,
        base_url: str = "",
    ) -> tuple[httpx.AsyncClient, tuple[str, str]]:
        key = self._client_key(purpose, base_url=base_url)
        async with self._lock:
            entry = self._entries.get(key)
            if entry is not None:
                entry.in_use += 1
                entry.last_used_at = time.monotonic()
                self._record_metrics()
                return entry.client, key

            while len(self._entries) >= self._max_clients:
                if not await self._evict_idle_lru():
                    self._capacity_rejections += 1
                    self._record_metrics()
                    raise RuntimeError("External HTTP client pool capacity exhausted")
            client = self._create_client(base_url=base_url)
            self._entries[key] = _PooledClient(client=client, in_use=1)
            self._clients_created += 1
            self._record_metrics()
            return client, key

    async def release(self, key: tuple[str, str]) -> None:
        async with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return
            entry.in_use = max(0, entry.in_use - 1)
            entry.last_used_at = time.monotonic()
            self._record_metrics()

    async def aclose(self) -> None:
        async with self._lock:
            clients = [entry.client for entry in self._entries.values()]
            closed_count = len(clients)
            self._entries.clear()
            self._clients_closed += closed_count
        if clients:
            await asyncio.gather(*(client.aclose() for client in clients))
        self._record_metrics()

    def stats(self) -> dict[str, int]:
        return {
            "client_count": len(self._entries),
            "clients_created": self._clients_created,
            "clients_closed": self._clients_closed,
            "capacity_rejections": self._capacity_rejections,
        }


external_http_clients = ExternalHttpClientPool()


@asynccontextmanager
async def managed_http_client(
    purpose: str,
    *,
    base_url: str = "",
    timeout_seconds: float | int | None = None,
) -> AsyncIterator[httpx.AsyncClient]:
    """Yield a shared client scoped to ``purpose`` and optional ``base_url``.

    ``timeout_seconds`` applies at request time and does not affect pool identity.
    """
    client, key = await external_http_clients.acquire(purpose, base_url=base_url)
    try:
        if timeout_seconds is None:
            yield client
        else:
            timeout_value = float(timeout_seconds)
            timeout_value = max(0.1, min(timeout_value, settings.EXTERNAL_HTTP_MAX_TIMEOUT_SECONDS))
            yield _RequestTimeoutClient(client, external_timeout(timeout_value))
    finally:
        await external_http_clients.release(key)


def register_worker_http_shutdown() -> None:
    """Close pooled clients and dispose DB engine when a Celery child process exits."""
    from celery.signals import worker_shutdown

    def _run_async(coro) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(coro)
        else:
            loop.create_task(coro)

    async def _shutdown() -> None:
        await external_http_clients.aclose()
        from backend.db.session import engine

        await engine.dispose()

    def close_resources(**_: object) -> None:
        _run_async(_shutdown())

    worker_shutdown.connect(
        close_resources,
        weak=False,
        dispatch_uid="troop.http_clients.worker_shutdown",
    )


__all__ = [
    "ExternalHttpClientPool",
    "external_http_clients",
    "managed_http_client",
    "register_worker_http_shutdown",
]
