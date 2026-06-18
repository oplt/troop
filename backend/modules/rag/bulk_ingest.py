"""Parallel bulk document ingest with per-item database sessions."""

from __future__ import annotations

import asyncio
from typing import Any

from backend.core.config import settings
from backend.db.session import SessionLocal
from backend.modules.identity_access.models import User
from backend.modules.orchestration.services.service import OrchestrationService
from backend.modules.rag.service import RagService


async def bulk_ingest_documents_parallel(
    user: User,
    project_id: str,
    *,
    documents: list[dict[str, Any]],
    task_id: str | None,
    queue_async: bool,
) -> list[Any]:
    """Ingest multiple documents concurrently using isolated AsyncSessions."""
    concurrency = max(1, settings.RAG_BULK_INGEST_CONCURRENCY)
    semaphore = asyncio.Semaphore(concurrency)

    async def ingest_one(item: dict[str, Any]):
        async with semaphore:
            async with SessionLocal() as session:
                orch = OrchestrationService(session)
                project = await orch.get_project(user, project_id)
                rag = RagService(session)
                return await rag.ingest_text(
                    user,
                    project,
                    title=item["title"],
                    content=item["content"],
                    task_id=task_id,
                    source_type=item.get("source_type"),
                    metadata=item.get("metadata") or {},
                    queue_async=queue_async,
                )

    return list(await asyncio.gather(*(ingest_one(item) for item in documents)))
