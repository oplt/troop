"""Lifecycle-managed async HTTP clients for external integrations."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx

from backend.core.config import settings
from backend.core.external_http import external_timeout


class ExternalHttpClientPool:
    """Reuse bounded connection pools without sharing mutable auth headers."""

    def __init__(self, *, max_clients: int | None = None) -> None:
        self._clients: dict[tuple[str, str, float], httpx.AsyncClient] = {}
        self._lock = asyncio.Lock()
        self._max_clients = max_clients or settings.EXTERNAL_HTTP_MAX_CLIENTS

    async def get(
        self,
        purpose: str,
        *,
        base_url: str = "",
        timeout_seconds: float | int | None = None,
    ) -> httpx.AsyncClient:
        timeout_value = float(timeout_seconds or settings.EXTERNAL_HTTP_TIMEOUT_SECONDS)
        timeout_value = max(0.1, min(timeout_value, settings.EXTERNAL_HTTP_MAX_TIMEOUT_SECONDS))
        key = (str(purpose), str(base_url or ""), timeout_value)
        async with self._lock:
            client = self._clients.get(key)
            if client is not None:
                return client
            if len(self._clients) >= self._max_clients:
                raise RuntimeError("External HTTP client pool capacity exhausted")
            client_kwargs: dict[str, object] = {
                "timeout": external_timeout(timeout_value),
                "limits": httpx.Limits(
                    max_connections=settings.EXTERNAL_HTTP_MAX_CONNECTIONS,
                    max_keepalive_connections=settings.EXTERNAL_HTTP_MAX_KEEPALIVE_CONNECTIONS,
                ),
            }
            if base_url:
                client_kwargs["base_url"] = base_url
            client = httpx.AsyncClient(**client_kwargs)
            self._clients[key] = client
            return client

    async def aclose(self) -> None:
        async with self._lock:
            clients = list(self._clients.values())
            self._clients.clear()
        if clients:
            await asyncio.gather(*(client.aclose() for client in clients))


external_http_clients = ExternalHttpClientPool()


@asynccontextmanager
async def managed_http_client(
    purpose: str,
    *,
    base_url: str = "",
    timeout_seconds: float | int | None = None,
) -> AsyncIterator[httpx.AsyncClient]:
    """Yield a shared client; the application/worker lifecycle closes it."""
    yield await external_http_clients.get(
        purpose,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
    )


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
