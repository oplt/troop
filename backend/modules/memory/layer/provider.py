from __future__ import annotations

from typing import Any, Protocol

from backend.modules.memory.layer.entry_mapping import (
    default_metadata_for_entry_type,
    normalize_entry_type,
)
from backend.modules.memory.layer.repository import (
    MemoryRepository,
    entry_to_record,
)
from backend.modules.memory.layer.schemas import MemoryFilters, MemoryRecord, MemoryScope
from backend.modules.memory.models import SemanticMemoryEntry


class MemoryProvider(Protocol):
    async def add(
        self,
        *,
        owner_id: str,
        content: str,
        scope: MemoryScope,
        project_id: str | None,
        metadata: dict[str, Any],
    ) -> MemoryRecord: ...

    async def get(self, owner_id: str, memory_id: str) -> MemoryRecord | None: ...

    async def search(
        self,
        owner_id: str,
        query: str,
        *,
        query_vec: list[float] | None,
        filters: MemoryFilters,
        limit: int,
    ) -> list[MemoryRecord]: ...

    async def update(
        self,
        owner_id: str,
        memory_id: str,
        *,
        content: str | None,
        metadata: dict[str, Any] | None,
    ) -> MemoryRecord | None: ...

    async def delete(self, owner_id: str, memory_id: str) -> bool: ...

    async def delete_for_user(self, owner_id: str) -> int: ...

    async def find_duplicate(
        self,
        owner_id: str,
        content_hash: str,
        filters: MemoryFilters,
    ) -> MemoryRecord | None: ...


class SemanticMemoryProvider:
    """Provider backed by existing `semantic_memory_entries` + pgvector."""

    def __init__(self, repository: MemoryRepository):
        self._repository = repository

    async def add(
        self,
        *,
        owner_id: str,
        content: str,
        scope: MemoryScope,
        project_id: str | None,
        metadata: dict[str, Any],
    ) -> MemoryRecord:
        entry_type = normalize_entry_type(
            str(metadata.get("memory_type") or metadata.get("entry_type") or "note")
        )
        title = str(metadata.get("title") or content[:80] or "Memory")
        payload_meta = default_metadata_for_entry_type(entry_type, content, metadata)
        payload_meta["memory_type"] = entry_type
        entry = await self._repository.create(
            owner_id=owner_id,
            scope=scope if scope != "user" else "project",
            company_id=payload_meta.get("company_id"),
            project_id=project_id if scope != "company" else None,
            agent_id=payload_meta.get("agent_id"),
            entry_type=entry_type,
            namespace=str(payload_meta.get("namespace") or f"{scope}:{project_id or owner_id}"),
            title=title[:255],
            body=content,
            metadata_json=payload_meta,
            source_task_id=payload_meta.get("task_id") or payload_meta.get("source_task_id"),
            source_run_id=payload_meta.get("session_id") or payload_meta.get("source_run_id"),
            provenance_json={
                "source": payload_meta.get("source", "memory_layer"),
                "confidence": payload_meta.get("confidence"),
                "created_by_user_id": payload_meta.get("created_by_user_id"),
            },
            created_by_user_id=payload_meta.get("created_by_user_id"),
        )
        await self._repository.enqueue_embedding(owner_id, project_id, entry.id)
        return entry_to_record(entry)

    async def get(self, owner_id: str, memory_id: str) -> MemoryRecord | None:
        entry = await self._repository.get(owner_id, memory_id)
        return entry_to_record(entry) if entry else None

    async def search(
        self,
        owner_id: str,
        query: str,
        *,
        query_vec: list[float] | None,
        filters: MemoryFilters,
        limit: int,
    ) -> list[MemoryRecord]:
        entries: list[SemanticMemoryEntry] = []
        if query_vec is not None and filters.project_id:
            entries = await self._repository.search_by_vector(
                owner_id,
                query_vec,
                filters=filters,
                limit=limit,
            )
        if not entries:
            entries = await self._repository.search_by_text(
                owner_id,
                query,
                filters=filters,
                limit=limit,
            )
        return [entry_to_record(e) for e in entries[:limit]]

    async def update(
        self,
        owner_id: str,
        memory_id: str,
        *,
        content: str | None,
        metadata: dict[str, Any] | None,
    ) -> MemoryRecord | None:
        entry = await self._repository.get(owner_id, memory_id)
        if entry is None:
            return None
        if content is not None:
            entry.body = content.strip()
            if not entry.title or entry.title == entry.body[:80]:
                entry.title = content[:80][:255]
        if metadata:
            merged = dict(entry.metadata_json or {})
            merged.update(metadata)
            entry.metadata_json = merged
        updated = await self._repository.update(entry)
        if content is not None and entry.project_id:
            await self._repository.enqueue_embedding(owner_id, entry.project_id, entry.id)
        return entry_to_record(updated)

    async def delete(self, owner_id: str, memory_id: str) -> bool:
        entry = await self._repository.get(owner_id, memory_id)
        if entry is None:
            return False
        await self._repository.delete(entry)
        return True

    async def delete_for_user(self, owner_id: str) -> int:
        return await self._repository.delete_for_user(owner_id)

    async def find_duplicate(
        self,
        owner_id: str,
        content_hash: str,
        filters: MemoryFilters,
    ) -> MemoryRecord | None:
        entry = await self._repository.find_by_content_hash(owner_id, content_hash, filters=filters)
        return entry_to_record(entry) if entry else None
