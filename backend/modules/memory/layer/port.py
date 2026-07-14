"""Provider-neutral memory contracts used by application code and adapters."""

from __future__ import annotations

from typing import Any, Protocol


class MemoryStore(Protocol):
    """Minimal durable namespace contract.

    Concrete providers may use PostgreSQL, Redis, or a vector database. Domain
    services must depend on this shape rather than on a provider SDK.
    """

    async def get(self, namespace: str, key: str) -> Any | None: ...

    async def set(
        self,
        namespace: str,
        key: str,
        value: Any,
        *,
        ttl: int | None = None,
    ) -> None: ...

    async def delete(self, namespace: str, key: str) -> None: ...

    async def search(
        self,
        namespace: str,
        query: str,
        *,
        filters: dict[str, Any] | None = None,
        limit: int = 20,
    ) -> list[Any]: ...


__all__ = ["MemoryStore"]
