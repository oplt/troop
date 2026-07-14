from __future__ import annotations

from typing import Any

from backend.modules.memory.layer.provider import MemoryProvider
from backend.modules.memory.layer.schemas import MemoryFilters, MemoryRecord, MemoryScope


class SemanticMemoryLifecycle:
    """Provider-neutral semantic CRUD boundary used by ``MemoryService``."""

    def __init__(self, provider: MemoryProvider):
        self._provider = provider

    async def add(
        self,
        *,
        owner_id: str,
        content: str,
        scope: MemoryScope,
        project_id: str | None,
        metadata: dict[str, Any],
    ) -> MemoryRecord:
        return await self._provider.add(
            owner_id=owner_id,
            content=content,
            scope=scope,
            project_id=project_id,
            metadata=metadata,
        )

    async def search(
        self,
        owner_id: str,
        query: str,
        *,
        query_vec: list[float] | None,
        filters: MemoryFilters,
        limit: int,
    ) -> list[MemoryRecord]:
        return await self._provider.search(
            owner_id,
            query,
            query_vec=query_vec,
            filters=filters,
            limit=limit,
        )

    async def update(
        self,
        owner_id: str,
        memory_id: str,
        *,
        content: str | None,
        metadata: dict[str, Any] | None,
    ) -> MemoryRecord | None:
        return await self._provider.update(
            owner_id,
            memory_id,
            content=content,
            metadata=metadata,
        )

    async def delete(self, owner_id: str, memory_id: str) -> bool:
        return await self._provider.delete(owner_id, memory_id)

    async def delete_for_user(self, owner_id: str) -> int:
        return await self._provider.delete_for_user(owner_id)

    async def find_duplicate(
        self,
        owner_id: str,
        content_hash: str,
        filters: MemoryFilters,
    ) -> MemoryRecord | None:
        return await self._provider.find_duplicate(owner_id, content_hash, filters)
