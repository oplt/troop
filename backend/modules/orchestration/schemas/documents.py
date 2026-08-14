from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.core.schemas import RequestModel
from backend.modules.github.schemas import GithubSyncEventResponse

from backend.modules.orchestration.schemas.common import *  # noqa: F403

class ProjectDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    task_id: str | None
    uploaded_by_user_id: str
    filename: str
    content_type: str
    source_text: str
    object_key: str | None
    size_bytes: int
    summary_text: str | None
    ingestion_status: str
    chunk_count: int
    ttl_days: int | None
    expires_at: datetime | None
    deleted_at: datetime | None
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class KnowledgeSearchResultResponse(BaseModel):
    hit_kind: Literal["chunk", "decision"] = "chunk"
    document_id: str
    chunk_id: str
    filename: str
    chunk_index: int
    score: float
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    decision_id: str | None = None

