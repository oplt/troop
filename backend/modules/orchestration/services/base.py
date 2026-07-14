"""Shared orchestration service base, constants, and cross-domain query helpers."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.ai.providers import AiProviderRegistry
from backend.modules.audit.repository import AuditRepository
from backend.modules.identity_access.models import User
from backend.modules.memory.entry_types import (
    SEMANTIC_ENTRY_TYPES as _CANONICAL_SEMANTIC_ENTRY_TYPES,
)
from backend.modules.orchestration.constants import (  # noqa: F401
    GITHUB_WEBHOOK_EVENT_ALLOWLIST,
    TASK_TRANSITIONS,
)
from backend.modules.orchestration.repository import OrchestrationRepository

SEMANTIC_ENTRY_TYPES = frozenset(_CANONICAL_SEMANTIC_ENTRY_TYPES)


class OrchestrationServiceBase:
    """Session-scoped dependencies shared by orchestration domain services."""

    _TOOL_MIN_PERMISSION: dict[str, str] = {
        "fs_read": "read-only",
        "repo_search": "read-only",
        "knowledge_search": "read-only",
        "web_fetch": "read-only",
        "web_search": "read-only",
        "github_comment": "comment-only",
        "github_label_issue": "code-write",
        "github_create_pr": "code-write",
        "fs_write": "code-write",
        "code_execute": "code-write",
        "db_query": "code-write",
    }
    _PERMISSION_RANK: dict[str, int] = {
        "read-only": 1,
        "comment-only": 2,
        "code-write": 3,
        "merge-blocked": 3,
    }
    _MERGE_BLOCKED_TOOLS: frozenset[str] = frozenset({"github_create_pr", "github_label_issue"})

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = OrchestrationRepository(db)
        self.audit_repo = AuditRepository(db)
        self.ai_providers = AiProviderRegistry()


class OrchestrationRunQueryMixin:
    """Minimal run read access without pulling in the execution domain."""

    async def list_task_runs(
        self, user: User, project_id: str | None = None, *, limit: int | None = None
    ):
        return await self.repo.list_runs(user.id, project_id, limit=limit)

    async def get_run(self, user: User, run_id: str):
        run = await self.repo.get_run(user.id, run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        return run

    def _run_event_tail_payloads(self, events: list[Any], *, limit: int = 12) -> list[dict[str, Any]]:
        tail = events[-limit:] if len(events) > limit else events
        out: list[dict[str, Any]] = []
        for e in tail:
            msg = e.message or ""
            if len(msg) > 400:
                msg = msg[:400] + "…"
            out.append(
                {
                    "event_type": e.event_type,
                    "level": e.level,
                    "message": msg,
                    "created_at": e.created_at,
                }
            )
        return out
