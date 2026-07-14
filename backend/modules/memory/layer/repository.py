from __future__ import annotations

from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.memory.layer.schemas import MemoryFilters, MemoryRecord
from backend.modules.memory.models import SemanticMemoryEntry
from backend.modules.orchestration.repository import OrchestrationRepository


class MemoryRepository(Protocol):
    async def create(self, **kwargs: Any) -> SemanticMemoryEntry: ...

    async def get(self, owner_id: str, memory_id: str) -> SemanticMemoryEntry | None: ...

    async def update(self, entry: SemanticMemoryEntry) -> SemanticMemoryEntry: ...

    async def delete(self, entry: SemanticMemoryEntry) -> None: ...

    async def delete_for_user(self, owner_id: str) -> int: ...

    async def search_by_text(
        self,
        owner_id: str,
        query: str,
        *,
        filters: MemoryFilters,
        limit: int,
    ) -> list[SemanticMemoryEntry]: ...

    async def search_by_vector(
        self,
        owner_id: str,
        query_vec: list[float],
        *,
        filters: MemoryFilters,
        limit: int,
    ) -> list[SemanticMemoryEntry]: ...

    async def find_by_content_hash(
        self,
        owner_id: str,
        content_hash: str,
        *,
        filters: MemoryFilters,
    ) -> SemanticMemoryEntry | None: ...

    async def enqueue_embedding(
        self, owner_id: str, project_id: str | None, entry_id: str
    ) -> None: ...


def entry_to_record(entry: SemanticMemoryEntry, *, score: float | None = None) -> MemoryRecord:
    metadata = dict(entry.metadata_json or {})
    return MemoryRecord(
        id=entry.id,
        content=entry.body,
        title=entry.title,
        user_id=entry.owner_id,
        memory_type=str(metadata.get("memory_type") or entry.entry_type or "note"),
        scope=entry.scope,  # type: ignore[arg-type]
        project_id=entry.project_id,
        company_id=entry.company_id,
        agent_id=entry.agent_id,
        session_id=entry.source_run_id or metadata.get("session_id"),
        source=str(metadata.get("source") or entry.provenance_json.get("source") or "semantic"),
        confidence=metadata.get("confidence"),
        metadata=metadata,
        score=score,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
        ttl_days=entry.ttl_days,
        expires_at=entry.expires_at,
        deleted_at=entry.deleted_at,
        retention_policy=entry.retention_policy,
        memory_version=entry.memory_version,
        embedding_model=entry.embedding_model,
        embedding_version=entry.embedding_version,
    )


class SqlMemoryRepository:
    """Repository adapter over existing orchestration semantic memory storage."""

    def __init__(self, db: AsyncSession):
        self._repo = OrchestrationRepository(db)
        self._db = db

    async def create(self, **kwargs: Any) -> SemanticMemoryEntry:
        return await self._repo.create_semantic_memory_entry(**kwargs)

    async def get(self, owner_id: str, memory_id: str) -> SemanticMemoryEntry | None:
        return await self._repo.get_semantic_memory_entry(owner_id, memory_id)

    async def update(self, entry: SemanticMemoryEntry) -> SemanticMemoryEntry:
        await self._db.flush()
        await self._db.refresh(entry)
        return entry

    async def delete(self, entry: SemanticMemoryEntry) -> None:
        await self._db.delete(entry)
        await self._db.flush()

    async def delete_for_user(self, owner_id: str) -> int:
        result = await self._db.execute(
            select(SemanticMemoryEntry).where(SemanticMemoryEntry.owner_id == owner_id)
        )
        rows = list(result.scalars().all())
        for row in rows:
            await self._db.delete(row)
        await self._db.flush()
        return len(rows)

    async def search_by_text(
        self,
        owner_id: str,
        query: str,
        *,
        filters: MemoryFilters,
        limit: int,
    ) -> list[SemanticMemoryEntry]:
        project_id = filters.project_id
        if project_id:
            return await self._repo.list_semantic_memory_entries(
                owner_id,
                project_id=project_id,
                agent_id=filters.agent_id,
                source_task_id=filters.task_id,
                namespace_prefix=filters.namespace_prefix,
                scope=filters.scope,
                search=query,
                limit=limit,
                include_expired=filters.include_expired,
            )
        if filters.scope == "company" and filters.user_id:
            company_rows = await self._repo.list_semantic_memory_entries_for_company(
                owner_id,
                filters.user_id,
                search=query,
                limit=limit,
            )
            return company_rows
        return await self._repo.list_semantic_memory_entries(
            owner_id,
            project_id=None,
            agent_id=filters.agent_id,
            company_id=filters.company_id,
            source_task_id=filters.task_id,
            namespace_prefix=filters.namespace_prefix,
            scope=filters.scope,
            search=query,
            limit=limit,
            include_expired=filters.include_expired,
        )

    async def search_by_vector(
        self,
        owner_id: str,
        query_vec: list[float],
        *,
        filters: MemoryFilters,
        limit: int,
    ) -> list[SemanticMemoryEntry]:
        project_id = filters.project_id
        if not project_id:
            return []
        if filters.session_id:
            return await self._repo.search_semantic_memory_by_vector_scoped(
                owner_id,
                project_id,
                query_vec,
                source_task_id=None,
                limit=limit,
            )
        return await self._repo.search_semantic_memory_by_vector(
            owner_id,
            project_id,
            query_vec,
            limit=limit,
        )

    async def find_by_content_hash(
        self,
        owner_id: str,
        content_hash: str,
        *,
        filters: MemoryFilters,
    ) -> SemanticMemoryEntry | None:
        rows = await self._repo.list_semantic_memory_entries(
            owner_id,
            project_id=filters.project_id,
            agent_id=filters.agent_id,
            company_id=filters.company_id,
            source_task_id=filters.task_id,
            namespace_prefix=filters.namespace_prefix,
            scope=filters.scope,
            limit=200,
            include_expired=filters.include_expired,
        )
        for row in rows:
            meta = row.metadata_json or {}
            if meta.get("content_hash") == content_hash:
                return row
        return None

    async def enqueue_embedding(self, owner_id: str, project_id: str | None, entry_id: str) -> None:
        if not project_id:
            return
        await self._repo.create_memory_ingest_job(
            owner_id=owner_id,
            project_id=project_id,
            job_type="semantic_embed",
            payload_json={"entry_id": entry_id},
            status="pending",
        )
