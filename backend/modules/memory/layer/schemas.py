from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

MemoryScope = Literal["company", "project", "agent", "task", "user", "global"]
MemoryType = Literal[
    "note",
    "preference",
    "decision",
    "constraint",
    "fact",
    "policy",
    "convention",
    "runbook",
    "outcome",
]


@dataclass(frozen=True, slots=True)
class MemoryAccessContext:
    """Authenticated memory boundary; company is the current tenant boundary."""

    owner_id: str
    company_id: str | None = None
    project_id: str | None = None
    agent_id: str | None = None
    task_id: str | None = None
    session_id: str | None = None

    def filters(self, *, scope: MemoryScope | None = None) -> MemoryFilters:
        return MemoryFilters(
            user_id=self.owner_id,
            company_id=self.company_id,
            project_id=self.project_id,
            agent_id=self.agent_id,
            task_id=self.task_id,
            session_id=self.session_id,
            scope=scope,
        )


@dataclass(slots=True)
class MemoryFilters:
    user_id: str | None = None
    company_id: str | None = None
    project_id: str | None = None
    agent_id: str | None = None
    task_id: str | None = None
    session_id: str | None = None
    memory_type: str | None = None
    scope: MemoryScope | None = None
    source: str | None = None
    namespace_prefix: str | None = None
    include_expired: bool = False

    def as_metadata_filters(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.session_id:
            out["session_id"] = self.session_id
        if self.task_id:
            out["task_id"] = self.task_id
        if self.source:
            out["source"] = self.source
        if self.memory_type:
            out["memory_type"] = self.memory_type
        return out


@dataclass(slots=True)
class MemoryRecord:
    id: str
    content: str
    user_id: str
    title: str = ""
    memory_type: str = "note"
    scope: MemoryScope = "project"
    project_id: str | None = None
    company_id: str | None = None
    agent_id: str | None = None
    task_id: str | None = None
    session_id: str | None = None
    source: str = "api"
    confidence: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    score: float | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    ttl_days: int | None = None
    expires_at: datetime | None = None
    deleted_at: datetime | None = None
    retention_policy: str = "default"
    memory_version: int = 1
    canonical_key: str | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    status: str = "current"
    supersedes_memory_id: str | None = None
    embedding_model: str | None = None
    embedding_version: str | None = None

    @property
    def display_line(self) -> str:
        label = self.memory_type or "note"
        title = (self.title or self.content[:80]).strip()
        body = (self.content or "")[:320].strip()
        if title and title != body[: len(title)]:
            return f"- [{label}] {title}: {body}"
        return f"- [{label}] {body}"
