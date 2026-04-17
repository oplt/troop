from datetime import datetime
from uuid import uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base
from backend.modules.orchestration.model_utils import (
    EMBEDDING_VECTOR_DIMENSIONS,
    normalize_embedding_for_vector,
    utcnow,
)


class ProjectDocument(Base):
    __tablename__ = "project_documents"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(
        ForeignKey("orchestrator_projects.id", ondelete="CASCADE"),
        index=True,
    )
    task_id: Mapped[str | None] = mapped_column(
        ForeignKey("orchestrator_tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    uploaded_by_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(128), default="text/markdown")
    source_text: Mapped[str] = mapped_column(Text, default="")
    object_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    ingestion_status: Mapped[str] = mapped_column(String(32), default="pending")
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    ttl_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ProjectDocumentChunk(Base):
    __tablename__ = "project_document_chunks"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    project_document_id: Mapped[str] = mapped_column(
        ForeignKey("project_documents.id", ondelete="CASCADE"),
        index=True,
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("orchestrator_projects.id", ondelete="CASCADE"),
        index=True,
    )
    task_id: Mapped[str | None] = mapped_column(
        ForeignKey("orchestrator_tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    embedding_json: Mapped[list[float]] = mapped_column(JSON, default=list)
    embedding_vector: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_VECTOR_DIMENSIONS),
        nullable=True,
    )
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AgentMemoryEntry(Base):
    __tablename__ = "agent_memory_entries"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    agent_id: Mapped[str] = mapped_column(
        ForeignKey("agent_profiles.id", ondelete="CASCADE"),
        index=True,
    )
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("orchestrator_projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    source_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("task_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    key: Mapped[str] = mapped_column(String(128), index=True)
    value_text: Mapped[str] = mapped_column(Text)
    scope: Mapped[str] = mapped_column(String(32), default="project-only")
    status: Mapped[str] = mapped_column(String(32), default="approved", index=True)
    approved_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    ttl_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class SemanticMemoryEntry(Base):
    __tablename__ = "semantic_memory_entries"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    scope: Mapped[str] = mapped_column(String(32), index=True)
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("orchestrator_projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    agent_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    entry_type: Mapped[str] = mapped_column(String(64), index=True)
    namespace: Mapped[str] = mapped_column(String(512), index=True)
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    source_chunk_id: Mapped[str | None] = mapped_column(
        ForeignKey("project_document_chunks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_task_id: Mapped[str | None] = mapped_column(
        ForeignKey("orchestrator_tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("task_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    provenance_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    embedding_vector: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_VECTOR_DIMENSIONS),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ProceduralPlaybook(Base):
    __tablename__ = "procedural_playbooks"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("orchestrator_projects.id", ondelete="CASCADE"), index=True
    )
    slug: Mapped[str] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(String(255))
    body_md: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    tags_json: Mapped[list] = mapped_column(JSON, default=list)
    namespace: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class MemoryIngestJob(Base):
    __tablename__ = "memory_ingest_jobs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("orchestrator_projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    job_type: Mapped[str] = mapped_column(String(64), index=True)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EpisodicArchiveManifest(Base):
    __tablename__ = "episodic_archive_manifests"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("orchestrator_projects.id", ondelete="CASCADE"), index=True
    )
    object_key: Mapped[str] = mapped_column(String(1024))
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    record_count: Mapped[int] = mapped_column(Integer, default=0)
    byte_size: Mapped[int] = mapped_column(Integer, default=0)
    stats_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EpisodicSearchIndex(Base):
    __tablename__ = "episodic_search_index"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("orchestrator_projects.id", ondelete="CASCADE"), index=True
    )
    source_kind: Mapped[str] = mapped_column(String(32), index=True)
    source_id: Mapped[str] = mapped_column(String(64))
    text_content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    embedding_vector: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_VECTOR_DIMENSIONS),
        nullable=True,
    )


class SemanticMemoryLink(Base):
    __tablename__ = "semantic_memory_links"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("orchestrator_projects.id", ondelete="CASCADE"), index=True
    )
    from_entry_id: Mapped[str] = mapped_column(
        ForeignKey("semantic_memory_entries.id", ondelete="CASCADE"), index=True
    )
    to_entry_id: Mapped[str] = mapped_column(
        ForeignKey("semantic_memory_entries.id", ondelete="CASCADE"), index=True
    )
    relation_type: Mapped[str] = mapped_column(String(64))
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


__all__ = [
    "AgentMemoryEntry",
    "EMBEDDING_VECTOR_DIMENSIONS",
    "EpisodicArchiveManifest",
    "EpisodicSearchIndex",
    "MemoryIngestJob",
    "ProceduralPlaybook",
    "ProjectDocument",
    "ProjectDocumentChunk",
    "SemanticMemoryEntry",
    "SemanticMemoryLink",
    "normalize_embedding_for_vector",
]
