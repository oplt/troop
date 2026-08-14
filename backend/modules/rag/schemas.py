from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

SourceType = Literal[
    "text",
    "markdown",
    "pdf",
    "html",
    "json",
    "csv",
    "code",
    "upload",
    "repository",
    "url",
]


@dataclass(slots=True)
class RagSearchFilters:
    user_id: str | None = None
    project_id: str | None = None
    workspace_id: str | None = None
    task_id: str | None = None
    source_type: str | None = None
    source_kind: str | None = None
    document_ids: list[str] = field(default_factory=list)
    include_decisions: bool = False
    actor_email: str | None = None


@dataclass(slots=True)
class RagDocument:
    document_id: str
    source_id: str
    source_type: SourceType
    title: str
    content: str
    owner_user_id: str
    project_id: str
    workspace_id: str | None = None
    visibility: str = "project"
    metadata: dict[str, Any] = field(default_factory=dict)
    checksum: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(slots=True)
class RagChunk:
    chunk_id: str
    document_id: str
    source_id: str
    source_type: SourceType
    title: str
    content: str
    chunk_index: int
    content_hash: str
    owner_user_id: str
    project_id: str
    workspace_id: str | None = None
    page_number: int | None = None
    section: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    score: float | None = None
    created_at: datetime | None = None


@dataclass(slots=True)
class RagChunkMatch:
    chunk_id: str
    document_id: str
    title: str
    content: str
    chunk_index: int
    score: float
    source_type: str = "text"
    metadata: dict[str, Any] = field(default_factory=dict)
    hit_kind: str = "chunk"

    @property
    def citation_label(self) -> str:
        return f"{self.title}#{self.chunk_index}"


@dataclass(slots=True)
class RagCitation:
    source_index: int
    chunk_id: str
    document_id: str
    title: str
    chunk_index: int
    score: float
    excerpt: str


@dataclass(slots=True)
class RagAnswer:
    query: str
    answer: str
    citations: list[RagCitation]
    grounded: bool
    context_found: bool
    model: str = ""
    provider: str = ""
