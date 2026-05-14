from __future__ import annotations

from typing import Any, Literal

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.identity_access.models import User
from backend.modules.memory.models import SemanticMemoryEntry

MemoryScope = Literal["company", "project", "agent", "task"]


class SqlMemoryStore:
    def __init__(self, db: AsyncSession, user: User):
        self.db = db
        self.user = user

    async def add_memory(
        self,
        scope: MemoryScope,
        scope_id: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> SemanticMemoryEntry:
        metadata = dict(metadata or {})
        entry = SemanticMemoryEntry(
            owner_id=self.user.id,
            scope=scope,
            company_id=scope_id if scope == "company" else None,
            project_id=scope_id if scope == "project" else metadata.get("project_id"),
            agent_id=scope_id if scope == "agent" else metadata.get("agent_id"),
            source_task_id=scope_id if scope == "task" else metadata.get("task_id"),
            entry_type=str(metadata.get("entry_type") or "note"),
            namespace=f"{scope}:{scope_id}",
            title=str(metadata.get("title") or content[:80] or "Memory"),
            body=content,
            metadata_json=metadata,
            provenance_json={"source": "agent_memory_api"},
            created_by_user_id=self.user.id,
        )
        self.db.add(entry)
        await self.db.commit()
        await self.db.refresh(entry)
        return entry

    async def list_memory(
        self,
        scope: MemoryScope,
        scope_id: str,
        limit: int = 50,
    ) -> list[SemanticMemoryEntry]:
        stmt = self._scope_stmt(scope, scope_id).order_by(SemanticMemoryEntry.created_at.desc()).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def search_memory(
        self,
        scope: MemoryScope,
        scope_id: str,
        query: str,
        limit: int = 20,
    ) -> list[SemanticMemoryEntry]:
        pattern = f"%{query.strip()}%"
        stmt = (
            self._scope_stmt(scope, scope_id)
            .where(or_(SemanticMemoryEntry.title.ilike(pattern), SemanticMemoryEntry.body.ilike(pattern)))
            .order_by(SemanticMemoryEntry.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    def _scope_stmt(self, scope: MemoryScope, scope_id: str):
        stmt = select(SemanticMemoryEntry).where(
            SemanticMemoryEntry.owner_id == self.user.id,
            SemanticMemoryEntry.scope == scope,
        )
        if scope == "company":
            return stmt.where(SemanticMemoryEntry.company_id == scope_id)
        if scope == "project":
            return stmt.where(SemanticMemoryEntry.project_id == scope_id)
        if scope == "agent":
            return stmt.where(SemanticMemoryEntry.agent_id == scope_id)
        return stmt.where(SemanticMemoryEntry.source_task_id == scope_id)
