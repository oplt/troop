from __future__ import annotations

from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.identity_access.models import User
from backend.modules.memory.layer.config import resolve_memory_config
from backend.modules.memory.layer.repository import SqlMemoryRepository
from backend.modules.memory.layer.schemas import MemoryFilters
from backend.modules.memory.layer.service import MemoryService
from backend.modules.memory.models import SemanticMemoryEntry

MemoryScope = Literal["company", "project", "agent", "task"]


class SqlMemoryStore:
    """Agent-facing memory API — delegates to the unified MemoryService."""

    def __init__(self, db: AsyncSession, user: User):
        self.db = db
        self.user = user
        self._repo = SqlMemoryRepository(db)
        self._service = MemoryService(db, config=resolve_memory_config())

    async def add_memory(
        self,
        scope: MemoryScope,
        scope_id: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> SemanticMemoryEntry:
        meta = dict(metadata or {})
        meta.setdefault("entry_type", meta.get("entry_type") or "note")
        project_id = scope_id if scope == "project" else meta.get("project_id")
        if scope == "agent":
            meta["agent_id"] = scope_id
        if scope == "task":
            meta["task_id"] = scope_id
        record = await self._service.add_memory(
            self.user.id,
            content,
            meta,
            scope=scope,
            project_id=project_id,
        )
        if record is None:
            raise ValueError(
                "Memory was blocked by privacy filters or the memory layer is disabled."
            )
        row = await self._repo.get(self.user.id, record.id)
        if row is None:
            raise ValueError("Memory row missing after write.")
        return row

    async def list_memory(
        self,
        scope: MemoryScope,
        scope_id: str,
        limit: int = 50,
    ) -> list[SemanticMemoryEntry]:
        filters = self._scope_filters(scope, scope_id)
        records = await self._service.search_memories(
            self.user.id,
            query="",
            limit=limit,
            filters=filters,
        )
        rows: list[SemanticMemoryEntry] = []
        for record in records:
            row = await self._repo.get(self.user.id, record.id)
            if row is not None:
                rows.append(row)
        return rows

    async def search_memory(
        self,
        scope: MemoryScope,
        scope_id: str,
        query: str,
        limit: int = 20,
    ) -> list[SemanticMemoryEntry]:
        filters = self._scope_filters(scope, scope_id)
        records = await self._service.search_memories(
            self.user.id,
            query,
            limit=limit,
            filters=filters,
        )
        rows: list[SemanticMemoryEntry] = []
        for record in records:
            row = await self._repo.get(self.user.id, record.id)
            if row is not None:
                rows.append(row)
        return rows

    async def update_memory(
        self,
        memory_id: str,
        *,
        content: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SemanticMemoryEntry | None:
        record = await self._service.update_memory(
            memory_id,
            user_id=self.user.id,
            content=content,
            metadata=metadata,
        )
        if record is None:
            return None
        return await self._repo.get(self.user.id, record.id)

    async def delete_memory(self, memory_id: str) -> bool:
        return await self._service.delete_memory(memory_id, user_id=self.user.id)

    def _scope_filters(self, scope: MemoryScope, scope_id: str) -> MemoryFilters:
        filters = MemoryFilters(user_id=self.user.id, scope=scope)
        if scope == "project":
            filters.project_id = scope_id
        elif scope == "agent":
            filters.agent_id = scope_id
        return filters
