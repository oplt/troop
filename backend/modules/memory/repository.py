from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import delete, or_, select, text

from backend.modules.memory.models import (
    AgentMemoryEntry,
    EpisodicArchiveManifest,
    EpisodicSearchIndex,
    MemoryIngestJob,
    ProceduralPlaybook,
    ProjectDocument,
    ProjectDocumentChunk,
    SemanticMemoryEntry,
    SemanticMemoryLink,
    normalize_embedding_for_vector,
)
from backend.modules.orchestration.models import (
    Brainstorm,
    BrainstormMessage,
    OrchestratorTask,
    RunEvent,
    TaskComment,
    TaskRun,
)


class MemoryRepositoryMixin:
    async def create_document(self, **kwargs) -> ProjectDocument:
        item = ProjectDocument(**kwargs)
        self.db.add(item)
        await self.db.flush()
        return item

    async def list_documents(self, project_id: str, task_id: str | None = None) -> list[ProjectDocument]:
        stmt = select(ProjectDocument).where(
            ProjectDocument.project_id == project_id,
            ProjectDocument.deleted_at.is_(None),
        )
        if task_id is not None:
            stmt = stmt.where(or_(ProjectDocument.task_id == task_id, ProjectDocument.task_id.is_(None)))
        result = await self.db.execute(stmt.order_by(ProjectDocument.created_at.desc()))
        return list(result.scalars().all())

    async def get_document(self, project_id: str, document_id: str) -> ProjectDocument | None:
        result = await self.db.execute(
            select(ProjectDocument).where(
                ProjectDocument.project_id == project_id,
                ProjectDocument.id == document_id,
            )
        )
        return result.scalar_one_or_none()

    async def replace_document_chunks(
        self,
        document: ProjectDocument,
        chunks: list[tuple[int, str, int, list[float], dict]],
    ) -> None:
        result = await self.db.execute(
            select(ProjectDocumentChunk).where(ProjectDocumentChunk.project_document_id == document.id)
        )
        for item in result.scalars().all():
            await self.db.delete(item)
        await self.db.flush()
        for chunk_index, content, token_count, embedding, metadata in chunks:
            self.db.add(
                ProjectDocumentChunk(
                    project_document_id=document.id,
                    project_id=document.project_id,
                    task_id=document.task_id,
                    chunk_index=chunk_index,
                    content=content,
                    token_count=token_count,
                    embedding_json=embedding,
                    embedding_vector=normalize_embedding_for_vector(embedding),
                    metadata_json=metadata,
                )
            )
        await self.db.flush()

    async def search_document_chunks_by_vector(
        self,
        project_id: str,
        query_vec: list[float],
        *,
        task_id: str | None,
        source_kind: str | None,
        top_k: int,
    ) -> list[dict]:
        qv = normalize_embedding_for_vector(query_vec)
        literal = "[" + ",".join(str(float(x)) for x in qv) + "]"
        clauses = [
            "c.project_id = :pid",
            "c.deleted_at IS NULL",
            "d.deleted_at IS NULL",
            "c.embedding_vector IS NOT NULL",
        ]
        params: dict[str, str | int] = {"pid": project_id, "qv": literal, "lim": max(1, min(top_k, 20))}
        if task_id is not None:
            clauses.append("(c.task_id = :tid OR c.task_id IS NULL)")
            params["tid"] = task_id
        if source_kind:
            clauses.append("c.metadata_json->>'source_kind' = :sk")
            params["sk"] = source_kind
        where_sql = " AND ".join(clauses)
        sql = text(
            f"""
            SELECT c.id AS chunk_id, c.project_document_id, c.chunk_index, c.content, c.metadata_json,
                   d.filename,
                   1 - (c.embedding_vector <=> CAST(:qv AS vector)) AS score
            FROM project_document_chunks c
            INNER JOIN project_documents d ON d.id = c.project_document_id
            WHERE {where_sql}
            ORDER BY c.embedding_vector <=> CAST(:qv AS vector)
            LIMIT :lim
            """
        )
        result = await self.db.execute(sql, params)
        return [dict(r) for r in result.mappings().all()]

    async def list_document_chunks(
        self,
        project_id: str,
        *,
        task_id: str | None = None,
        source_kind: str | None = None,
    ) -> list[ProjectDocumentChunk]:
        stmt = (
            select(ProjectDocumentChunk)
            .join(ProjectDocument, ProjectDocumentChunk.project_document_id == ProjectDocument.id)
            .where(
                ProjectDocumentChunk.project_id == project_id,
                ProjectDocumentChunk.deleted_at.is_(None),
                ProjectDocument.deleted_at.is_(None),
            )
        )
        if task_id is not None:
            stmt = stmt.where(
                or_(ProjectDocumentChunk.task_id == task_id, ProjectDocumentChunk.task_id.is_(None))
            )
        if source_kind:
            stmt = stmt.where(ProjectDocumentChunk.metadata_json["source_kind"].as_string() == source_kind)
        result = await self.db.execute(
            stmt.order_by(ProjectDocumentChunk.project_document_id.asc(), ProjectDocumentChunk.chunk_index.asc())
        )
        return list(result.scalars().all())

    async def create_agent_memory(self, **kwargs) -> AgentMemoryEntry:
        item = AgentMemoryEntry(**kwargs)
        self.db.add(item)
        await self.db.flush()
        return item

    async def list_agent_memory(
        self,
        owner_id: str,
        *,
        project_id: str | None = None,
        agent_id: str | None = None,
        status: str | None = None,
    ) -> list[AgentMemoryEntry]:
        stmt = select(AgentMemoryEntry).where(
            AgentMemoryEntry.owner_id == owner_id,
            AgentMemoryEntry.deleted_at.is_(None),
        )
        if project_id is not None:
            stmt = stmt.where(AgentMemoryEntry.project_id == project_id)
        if agent_id is not None:
            stmt = stmt.where(AgentMemoryEntry.agent_id == agent_id)
        if status is not None:
            stmt = stmt.where(AgentMemoryEntry.status == status)
        result = await self.db.execute(stmt.order_by(AgentMemoryEntry.updated_at.desc()))
        return list(result.scalars().all())

    async def get_agent_memory(self, owner_id: str, memory_id: str) -> AgentMemoryEntry | None:
        result = await self.db.execute(
            select(AgentMemoryEntry).where(
                AgentMemoryEntry.owner_id == owner_id,
                AgentMemoryEntry.id == memory_id,
            )
        )
        return result.scalar_one_or_none()

    async def create_semantic_memory_entry(self, **kwargs: Any) -> SemanticMemoryEntry:
        item = SemanticMemoryEntry(**kwargs)
        self.db.add(item)
        await self.db.flush()
        return item

    async def get_semantic_memory_entry(self, owner_id: str, entry_id: str) -> SemanticMemoryEntry | None:
        result = await self.db.execute(
            select(SemanticMemoryEntry).where(
                SemanticMemoryEntry.id == entry_id,
                SemanticMemoryEntry.owner_id == owner_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_semantic_memory_entries(
        self,
        owner_id: str,
        *,
        project_id: str | None = None,
        entry_type: str | None = None,
        namespace_prefix: str | None = None,
        search: str | None = None,
        limit: int = 100,
    ) -> list[SemanticMemoryEntry]:
        stmt = select(SemanticMemoryEntry).where(SemanticMemoryEntry.owner_id == owner_id)
        if project_id is not None:
            stmt = stmt.where(SemanticMemoryEntry.project_id == project_id)
        if entry_type:
            stmt = stmt.where(SemanticMemoryEntry.entry_type == entry_type)
        if namespace_prefix:
            stmt = stmt.where(SemanticMemoryEntry.namespace.startswith(namespace_prefix))
        if search:
            q = f"%{search}%"
            stmt = stmt.where(or_(SemanticMemoryEntry.title.ilike(q), SemanticMemoryEntry.body.ilike(q)))
        cap = max(1, min(limit, 500))
        result = await self.db.execute(stmt.order_by(SemanticMemoryEntry.updated_at.desc()).limit(cap))
        return list(result.scalars().all())

    async def find_semantic_by_decision_id(
        self, owner_id: str, project_id: str, decision_id: str
    ) -> SemanticMemoryEntry | None:
        r = await self.db.execute(
            select(SemanticMemoryEntry).where(
                SemanticMemoryEntry.owner_id == owner_id,
                SemanticMemoryEntry.project_id == project_id,
                SemanticMemoryEntry.provenance_json["decision_id"].as_string() == decision_id,
            )
        )
        return r.scalar_one_or_none()

    async def find_semantic_by_agent_memory_id(
        self, owner_id: str, project_id: str, memory_id: str
    ) -> SemanticMemoryEntry | None:
        r = await self.db.execute(
            select(SemanticMemoryEntry).where(
                SemanticMemoryEntry.owner_id == owner_id,
                SemanticMemoryEntry.project_id == project_id,
                SemanticMemoryEntry.provenance_json["agent_memory_id"].as_string() == memory_id,
            )
        )
        return r.scalar_one_or_none()

    async def find_semantic_by_task_close(
        self, owner_id: str, project_id: str, task_id: str
    ) -> SemanticMemoryEntry | None:
        r = await self.db.execute(
            select(SemanticMemoryEntry)
            .where(
                SemanticMemoryEntry.owner_id == owner_id,
                SemanticMemoryEntry.project_id == project_id,
                SemanticMemoryEntry.provenance_json["source"].as_string() == "task_close",
                SemanticMemoryEntry.provenance_json["task_id"].as_string() == task_id,
            )
            .limit(1)
        )
        return r.scalars().first()

    async def search_semantic_memory_by_vector(
        self,
        owner_id: str,
        project_id: str,
        query_vec: list[float],
        *,
        limit: int = 12,
    ) -> list[SemanticMemoryEntry]:
        cap = max(1, min(limit, 50))
        qv = normalize_embedding_for_vector(query_vec)
        literal = "[" + ",".join(str(float(x)) for x in qv) + "]"
        sql = text(
            """
            SELECT id FROM semantic_memory_entries
            WHERE owner_id = :oid
              AND project_id = :pid
              AND embedding_vector IS NOT NULL
            ORDER BY embedding_vector <=> CAST(:qv AS vector)
            LIMIT :lim
            """
        )
        result = await self.db.execute(sql, {"oid": owner_id, "pid": project_id, "qv": literal, "lim": cap})
        ids = [row[0] for row in result.all()]
        if not ids:
            return []
        r2 = await self.db.execute(select(SemanticMemoryEntry).where(SemanticMemoryEntry.id.in_(ids)))
        by_id = {x.id: x for x in r2.scalars().all()}
        return [by_id[i] for i in ids if i in by_id]

    async def list_procedural_playbooks(self, owner_id: str, project_id: str) -> list[ProceduralPlaybook]:
        res = await self.db.execute(
            select(ProceduralPlaybook)
            .where(
                ProceduralPlaybook.owner_id == owner_id,
                ProceduralPlaybook.project_id == project_id,
            )
            .order_by(ProceduralPlaybook.updated_at.desc())
        )
        return list(res.scalars().all())

    async def get_procedural_playbook(
        self, owner_id: str, project_id: str, playbook_id: str
    ) -> ProceduralPlaybook | None:
        r = await self.db.execute(
            select(ProceduralPlaybook).where(
                ProceduralPlaybook.id == playbook_id,
                ProceduralPlaybook.owner_id == owner_id,
                ProceduralPlaybook.project_id == project_id,
            )
        )
        return r.scalar_one_or_none()

    async def create_procedural_playbook(self, **kwargs: Any) -> ProceduralPlaybook:
        row = ProceduralPlaybook(**kwargs)
        self.db.add(row)
        await self.db.flush()
        return row

    async def create_memory_ingest_job(self, **kwargs: Any) -> MemoryIngestJob:
        row = MemoryIngestJob(**kwargs)
        self.db.add(row)
        await self.db.flush()
        return row

    async def list_pending_memory_ingest_jobs(self, *, limit: int = 20) -> list[MemoryIngestJob]:
        res = await self.db.execute(
            select(MemoryIngestJob)
            .where(MemoryIngestJob.status == "pending")
            .order_by(MemoryIngestJob.created_at.asc())
            .limit(max(1, min(limit, 100)))
        )
        return list(res.scalars().all())

    async def list_memory_ingest_jobs_for_project(
        self, owner_id: str, project_id: str, *, limit: int = 80
    ) -> list[MemoryIngestJob]:
        res = await self.db.execute(
            select(MemoryIngestJob)
            .where(
                MemoryIngestJob.owner_id == owner_id,
                MemoryIngestJob.project_id == project_id,
            )
            .order_by(MemoryIngestJob.created_at.desc())
            .limit(max(1, min(limit, 300)))
        )
        return list(res.scalars().all())

    async def search_episodic_for_project(
        self,
        project_id: str,
        *,
        query: str | None = None,
        limit: int = 45,
        since: datetime | None = None,
        until: datetime | None = None,
        task_id: str | None = None,
        kinds: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        cap = max(1, min(limit, 200))
        kind_set = set(kinds) if kinds else None
        valid = ("run_event", "task_comment", "brainstorm_message")
        active = [k for k in valid if kind_set is None or k in kind_set]
        n_active = max(1, len(active))
        per_source = max(5, cap // n_active)
        hits: list[dict[str, Any]] = []
        qpat = f"%{query}%" if query else None

        if "run_event" in active:
            stmt = (
                select(RunEvent)
                .join(TaskRun, RunEvent.run_id == TaskRun.id)
                .where(TaskRun.project_id == project_id)
            )
            if qpat:
                stmt = stmt.where(RunEvent.message.ilike(qpat))
            if since:
                stmt = stmt.where(RunEvent.created_at >= since)
            if until:
                stmt = stmt.where(RunEvent.created_at <= until)
            if task_id:
                stmt = stmt.where(RunEvent.task_id == task_id)
            stmt = stmt.order_by(RunEvent.created_at.desc()).limit(per_source)
            ev_rows = await self.db.execute(stmt)
            for ev in ev_rows.scalars().all():
                hits.append(
                    {
                        "kind": "run_event",
                        "id": ev.id,
                        "run_id": ev.run_id,
                        "task_id": ev.task_id,
                        "event_type": ev.event_type,
                        "snippet": (ev.message or "")[:500],
                        "created_at": ev.created_at.isoformat(),
                    }
                )

        if "task_comment" in active:
            stmt = (
                select(TaskComment)
                .join(OrchestratorTask, TaskComment.task_id == OrchestratorTask.id)
                .where(OrchestratorTask.project_id == project_id)
            )
            if qpat:
                stmt = stmt.where(TaskComment.body.ilike(qpat))
            if since:
                stmt = stmt.where(TaskComment.created_at >= since)
            if until:
                stmt = stmt.where(TaskComment.created_at <= until)
            if task_id:
                stmt = stmt.where(TaskComment.task_id == task_id)
            stmt = stmt.order_by(TaskComment.created_at.desc()).limit(per_source)
            cm_rows = await self.db.execute(stmt)
            for comment in cm_rows.scalars().all():
                hits.append(
                    {
                        "kind": "task_comment",
                        "id": comment.id,
                        "task_id": comment.task_id,
                        "snippet": (comment.body or "")[:500],
                        "created_at": comment.created_at.isoformat(),
                    }
                )

        if "brainstorm_message" in active:
            stmt = (
                select(BrainstormMessage)
                .join(Brainstorm, BrainstormMessage.brainstorm_id == Brainstorm.id)
                .where(Brainstorm.project_id == project_id)
            )
            if qpat:
                stmt = stmt.where(BrainstormMessage.content.ilike(qpat))
            if since:
                stmt = stmt.where(BrainstormMessage.created_at >= since)
            if until:
                stmt = stmt.where(BrainstormMessage.created_at <= until)
            stmt = stmt.order_by(BrainstormMessage.created_at.desc()).limit(per_source)
            msg_rows = await self.db.execute(stmt)
            for msg in msg_rows.scalars().all():
                hits.append(
                    {
                        "kind": "brainstorm_message",
                        "id": msg.id,
                        "brainstorm_id": msg.brainstorm_id,
                        "snippet": (msg.content or "")[:500],
                        "created_at": msg.created_at.isoformat(),
                    }
                )

        hits.sort(key=lambda x: x["created_at"], reverse=True)
        return hits[:cap]

    async def create_episodic_archive_manifest(self, **kwargs: Any) -> EpisodicArchiveManifest:
        row = EpisodicArchiveManifest(**kwargs)
        self.db.add(row)
        await self.db.flush()
        return row

    async def list_episodic_archive_manifests(
        self, owner_id: str, project_id: str, *, limit: int = 50
    ) -> list[EpisodicArchiveManifest]:
        res = await self.db.execute(
            select(EpisodicArchiveManifest)
            .where(
                EpisodicArchiveManifest.owner_id == owner_id,
                EpisodicArchiveManifest.project_id == project_id,
            )
            .order_by(EpisodicArchiveManifest.created_at.desc())
            .limit(max(1, min(limit, 200)))
        )
        return list(res.scalars().all())

    async def get_episodic_index_row(
        self, project_id: str, source_kind: str, source_id: str
    ) -> EpisodicSearchIndex | None:
        r = await self.db.execute(
            select(EpisodicSearchIndex).where(
                EpisodicSearchIndex.project_id == project_id,
                EpisodicSearchIndex.source_kind == source_kind,
                EpisodicSearchIndex.source_id == source_id,
            )
        )
        return r.scalar_one_or_none()

    async def create_episodic_search_index_row(self, **kwargs: Any) -> EpisodicSearchIndex:
        row = EpisodicSearchIndex(**kwargs)
        self.db.add(row)
        await self.db.flush()
        return row

    async def search_episodic_index_by_vector(
        self,
        owner_id: str,
        project_id: str,
        query_vec: list[float],
        *,
        limit: int = 16,
        require_not_archived: bool = True,
    ) -> list[EpisodicSearchIndex]:
        cap = max(1, min(limit, 80))
        qv = normalize_embedding_for_vector(query_vec)
        literal = "[" + ",".join(str(float(x)) for x in qv) + "]"
        archived_clause = " AND archived_at IS NULL" if require_not_archived else ""
        sql = text(
            f"""
            SELECT id FROM episodic_search_index
            WHERE owner_id = :oid AND project_id = :pid
              AND embedding_vector IS NOT NULL
              {archived_clause}
            ORDER BY embedding_vector <=> CAST(:qv AS vector)
            LIMIT :lim
            """
        )
        result = await self.db.execute(sql, {"oid": owner_id, "pid": project_id, "qv": literal, "lim": cap})
        ids = [row[0] for row in result.all()]
        if not ids:
            return []
        r2 = await self.db.execute(select(EpisodicSearchIndex).where(EpisodicSearchIndex.id.in_(ids)))
        by_id = {x.id: x for x in r2.scalars().all()}
        return [by_id[i] for i in ids if i in by_id]

    async def list_episodic_index_missing_embedding(
        self, project_id: str, *, limit: int = 40
    ) -> list[EpisodicSearchIndex]:
        res = await self.db.execute(
            select(EpisodicSearchIndex)
            .where(
                EpisodicSearchIndex.project_id == project_id,
                EpisodicSearchIndex.archived_at.is_(None),
                EpisodicSearchIndex.embedding_vector.is_(None),
            )
            .order_by(EpisodicSearchIndex.created_at.asc())
            .limit(max(1, min(limit, 200)))
        )
        return list(res.scalars().all())

    async def delete_episodic_index_rows_before(self, project_id: str, before: datetime) -> int:
        res = await self.db.execute(
            delete(EpisodicSearchIndex).where(
                EpisodicSearchIndex.project_id == project_id,
                EpisodicSearchIndex.created_at < before,
            )
        )
        return int(res.rowcount or 0)

    async def list_run_events_for_project_before(
        self, project_id: str, before: datetime, *, limit: int = 3000
    ) -> list[RunEvent]:
        res = await self.db.execute(
            select(RunEvent)
            .join(TaskRun, RunEvent.run_id == TaskRun.id)
            .where(TaskRun.project_id == project_id, RunEvent.created_at < before)
            .order_by(RunEvent.created_at.asc())
            .limit(max(1, min(limit, 10_000)))
        )
        return list(res.scalars().all())

    async def create_semantic_memory_link(self, **kwargs: Any) -> SemanticMemoryLink:
        row = SemanticMemoryLink(**kwargs)
        self.db.add(row)
        await self.db.flush()
        return row

    async def list_semantic_memory_links(
        self, owner_id: str, project_id: str, entry_id: str
    ) -> list[SemanticMemoryLink]:
        res = await self.db.execute(
            select(SemanticMemoryLink)
            .where(
                SemanticMemoryLink.owner_id == owner_id,
                SemanticMemoryLink.project_id == project_id,
                or_(
                    SemanticMemoryLink.from_entry_id == entry_id,
                    SemanticMemoryLink.to_entry_id == entry_id,
                ),
            )
            .order_by(SemanticMemoryLink.created_at.desc())
        )
        return list(res.scalars().all())

    async def delete_semantic_memory_link(
        self, owner_id: str, project_id: str, link_id: str
    ) -> bool:
        r = await self.db.execute(
            select(SemanticMemoryLink).where(
                SemanticMemoryLink.id == link_id,
                SemanticMemoryLink.owner_id == owner_id,
                SemanticMemoryLink.project_id == project_id,
            )
        )
        row = r.scalar_one_or_none()
        if row is None:
            return False
        await self.db.delete(row)
        return True

    async def update_memory_ingest_job(
        self,
        job_id: str,
        *,
        status: str | None = None,
        error_text: str | None = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
    ) -> None:
        from sqlalchemy import update as sa_update

        vals: dict[str, Any] = {}
        if status is not None:
            vals["status"] = status
        if error_text is not None:
            vals["error_text"] = error_text
        if started_at is not None:
            vals["started_at"] = started_at
        if finished_at is not None:
            vals["finished_at"] = finished_at
        if vals:
            await self.db.execute(sa_update(MemoryIngestJob).where(MemoryIngestJob.id == job_id).values(**vals))
