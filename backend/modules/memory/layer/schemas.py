from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

MemoryScope = Literal["company", "project", "agent", "task", "user"]
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


@dataclass(slots=True)
class MemoryFilters:
    user_id: str | None = None
    project_id: str | None = None
    agent_id: str | None = None
    session_id: str | None = None
    memory_type: str | None = None
    scope: MemoryScope | None = None
    source: str | None = None

    def as_metadata_filters(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.session_id:
            out["session_id"] = self.session_id
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
    agent_id: str | None = None
    session_id: str | None = None
    source: str = "api"
    confidence: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    score: float | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def display_line(self) -> str:
        label = self.memory_type or "note"
        title = (self.title or self.content[:80]).strip()
        body = (self.content or "")[:320].strip()
        if title and title != body[: len(title)]:
            return f"- [{label}] {title}: {body}"
        return f"- [{label}] {body}"
