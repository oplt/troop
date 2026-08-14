from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.core.schemas import RequestModel
from backend.modules.orchestration.schemas.common import *  # noqa: F403


class WorkingMemoryResponse(BaseModel):
    """Run-scoped structured working set (Layer 2); persisted in ``checkpoint_json``."""

    schema_version: str = "1.0"
    objective: str = ""
    accepted_plan: str = ""
    latest_findings: str = ""
    temp_notes: str = ""
    open_questions: str = ""
    discussion_summary: str = ""
    artifact_refs: list[str] = Field(default_factory=list)
    updated_at: str


class WorkingMemoryPatch(RequestModel):
    objective: str | None = None
    accepted_plan: str | None = None
    latest_findings: str | None = None
    temp_notes: str | None = None
    open_questions: str | None = None
    discussion_summary: str | None = None
    artifact_refs: list[str] | None = None


class SemanticMemoryEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    owner_id: str
    scope: str
    company_id: str | None = None
    project_id: str | None
    agent_id: str | None
    entry_type: str
    namespace: str
    title: str
    body: str
    metadata: dict[str, Any]
    source_chunk_id: str | None
    source_task_id: str | None
    source_run_id: str | None
    provenance: dict[str, Any]
    created_by_user_id: str | None
    ttl_days: int | None = None
    expires_at: datetime | None = None
    deleted_at: datetime | None = None
    retention_policy: str = "default"
    memory_version: int = 1
    embedding_model: str | None = None
    embedding_version: str | None = None
    created_at: datetime
    updated_at: datetime


class SemanticMemoryEntryCreate(RequestModel):
    entry_type: str
    title: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1)
    scope: str = "project"
    namespace: str | None = None
    agent_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    source_chunk_id: str | None = None
    source_task_id: str | None = None
    source_run_id: str | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    ttl_days: int | None = Field(default=None, ge=1, le=3650)
    retention_policy: str = Field(default="default", min_length=1, max_length=64)


class SemanticMemoryEntryUpdate(RequestModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    body: str | None = None
    entry_type: str | None = None
    namespace: str | None = None
    metadata: dict[str, Any] | None = None
    ttl_days: int | None = Field(default=None, ge=1, le=3650)
    retention_policy: str | None = Field(default=None, min_length=1, max_length=64)


class PromoteWorkingMemoryRequest(RequestModel):
    run_id: str
    entry_type: str = "note"
    title: str | None = Field(default=None, max_length=255)


class EpisodicSearchResponse(BaseModel):
    hits: list[dict[str, Any]]


class MemorySettingsResponse(BaseModel):
    auto_promote_decisions: bool
    auto_promote_approved_agent_memory: bool
    auto_ingest_bypasses_semantic_approval: bool
    second_stage_rag: bool
    semantic_write_requires_approval: bool
    episodic_retrieval_depth: int
    episodic_retention_days: int
    episodic_archive_enabled: bool
    episodic_delete_index_after_archive: bool
    task_close_auto_promote_working_memory: bool
    enable_semantic_vector_search: bool
    enable_episodic_vector_search: bool
    deep_recall_mode: bool
    deep_recall_episodic_candidates: int
    classifier_worker_enabled: bool
    compaction_on_task_close_enabled: bool
    task_close_archive_unpromoted_memory: bool
    task_close_low_value_archive_days: int
    default_ttl_days: int
    max_ttl_days: int
    context_max_tokens: int


class MemorySettingsPatch(RequestModel):
    auto_promote_decisions: bool | None = None
    auto_promote_approved_agent_memory: bool | None = None
    auto_ingest_bypasses_semantic_approval: bool | None = None
    second_stage_rag: bool | None = None
    semantic_write_requires_approval: bool | None = None
    episodic_retrieval_depth: int | None = Field(default=None, ge=1, le=200)
    episodic_retention_days: int | None = Field(default=None, ge=1, le=3650)
    episodic_archive_enabled: bool | None = None
    episodic_delete_index_after_archive: bool | None = None
    task_close_auto_promote_working_memory: bool | None = None
    enable_semantic_vector_search: bool | None = None
    enable_episodic_vector_search: bool | None = None
    deep_recall_mode: bool | None = None
    deep_recall_episodic_candidates: int | None = Field(default=None, ge=4, le=200)
    classifier_worker_enabled: bool | None = None
    compaction_on_task_close_enabled: bool | None = None
    task_close_archive_unpromoted_memory: bool | None = None
    task_close_low_value_archive_days: int | None = Field(default=None, ge=1, le=3650)
    default_ttl_days: int | None = Field(default=None, ge=0, le=3650)
    max_ttl_days: int | None = Field(default=None, ge=1, le=3650)
    context_max_tokens: int | None = Field(default=None, ge=64, le=12000)


class PendingSemanticWriteResponse(BaseModel):
    pending: bool = True
    approval_id: str
    approval_type: str = "semantic_memory_write"


class MemoryIngestJobResponse(BaseModel):
    id: str
    project_id: str | None
    job_type: str
    status: str
    error_text: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class SemanticMergeRequest(RequestModel):
    canonical_entry_id: str
    merge_entry_ids: list[str] = Field(min_length=1)
    link_relation: str = "supersedes"


class SemanticMemoryLinkCreate(RequestModel):
    from_entry_id: str
    to_entry_id: str
    relation_type: str = Field(min_length=1, max_length=64)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SemanticMemoryLinkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    owner_id: str
    project_id: str
    from_entry_id: str
    to_entry_id: str
    relation_type: str
    metadata: dict[str, Any]
    created_at: datetime


class KnowledgeGraphEdgeCreate(RequestModel):
    source_kind: str = Field(min_length=1, max_length=64)
    source_id: str = Field(min_length=1, max_length=64)
    target_kind: str = Field(min_length=1, max_length=64)
    target_id: str = Field(min_length=1, max_length=64)
    relation_type: str = Field(min_length=1, max_length=64)
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeGraphEdgeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    owner_id: str
    project_id: str
    source_kind: str
    source_id: str
    target_kind: str
    target_id: str
    relation_type: str
    metadata: dict[str, Any]
    created_at: datetime


class EpisodicArchiveManifestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    object_key: str
    period_start: datetime
    period_end: datetime
    record_count: int
    byte_size: int
    stats_json: dict[str, Any]
    created_at: datetime


class ProceduralPlaybookResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    owner_id: str
    project_id: str
    slug: str
    title: str
    body_md: str
    version: int
    tags: list[Any]
    namespace: str
    created_at: datetime
    updated_at: datetime


class ProceduralPlaybookCreate(RequestModel):
    slug: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=255)
    body_md: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    namespace: str | None = None


class ProceduralPlaybookUpdate(RequestModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    body_md: str | None = None
    tags: list[str] | None = None
    namespace: str | None = None
    version: int | None = None


class TaskMemoryCoordinationResponse(BaseModel):
    shared: str
    private: dict[str, str]


class TaskMemoryCoordinationPatch(RequestModel):
    shared: str | None = None
    private: dict[str, str] | None = None


class SemanticConflictGroupResponse(BaseModel):
    group_key: str
    entries: list[dict[str, Any]]
