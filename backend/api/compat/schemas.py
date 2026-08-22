from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.modules.memory.layer.schemas import MemoryRecord
from backend.modules.projects.orchestration_models import TaskArtifact

MemoryScope = Literal["company", "project", "agent", "task"]
RiskLevel = Literal["low", "medium", "high"]


class MarkdownImportPayload(BaseModel):
    content: str
    project_id: str | None = None
    existing_agent_id: str | None = None


class ToolSpec(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    risk_level: RiskLevel = "low"
    requires_approval: bool = False


class ToolListResponse(BaseModel):
    tools: list[ToolSpec]


class MemoryCreate(BaseModel):
    scope: MemoryScope
    scope_id: str
    content: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemorySearch(BaseModel):
    scope: MemoryScope
    scope_id: str
    query: str = Field(min_length=1)
    limit: int = Field(default=20, ge=1, le=100)


class MemoryUpdate(BaseModel):
    content: str | None = Field(default=None, min_length=1)
    metadata: dict[str, Any] | None = None


class MemoryResponse(BaseModel):
    id: str
    scope: str
    scope_id: str
    title: str
    body: str
    metadata: dict[str, Any]
    created_at: datetime


class RunArtifactResponse(BaseModel):
    id: str
    run_id: str | None
    task_id: str
    type: str
    name: str
    path_or_url: str | None
    metadata: dict[str, Any]
    created_at: datetime


def memory_response(item: MemoryRecord) -> MemoryResponse:
    created_at = item.created_at
    if created_at is None:
        raise ValueError("Persisted memory is missing created_at")
    scope_id = (
        item.company_id
        or item.project_id
        or item.agent_id
        or item.task_id
        or str(item.metadata.get("task_id") or item.metadata.get("scope_id") or "")
    )
    return MemoryResponse(
        id=item.id,
        scope=item.scope,
        scope_id=scope_id,
        title=item.title,
        body=item.content,
        metadata=item.metadata,
        created_at=created_at,
    )


def artifact_response(item: TaskArtifact) -> RunArtifactResponse:
    return RunArtifactResponse(
        id=item.id,
        run_id=item.run_id,
        task_id=item.task_id,
        type=item.kind,
        name=item.title,
        path_or_url=(item.metadata_json or {}).get("path_or_url"),
        metadata=item.metadata_json or {},
        created_at=item.created_at,
    )


__all__ = [
    "MarkdownImportPayload",
    "MemoryCreate",
    "MemoryResponse",
    "MemoryScope",
    "MemorySearch",
    "MemoryUpdate",
    "RunArtifactResponse",
    "ToolListResponse",
    "ToolSpec",
    "artifact_response",
    "memory_response",
]
