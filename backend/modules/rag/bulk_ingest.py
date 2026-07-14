"""Parallel bulk document ingest with per-item database sessions."""

from __future__ import annotations

import asyncio
from typing import Any

from backend.core.config import settings
from backend.db.session import SessionLocal
from backend.modules.identity_access.models import User
from backend.modules.orchestration.services.service import OrchestrationService
from backend.modules.rag.observability import log_rag_event
from backend.modules.rag.service import RagService


async def bulk_ingest_documents_parallel(
    user: User,
    project_id: str,
    *,
    documents: list[dict[str, Any]],
    task_id: str | None,
    queue_async: bool,
) -> list[Any]:
    """Ingest documents in bounded batches using isolated AsyncSessions."""
    if len(documents) > max(1, settings.RAG_BULK_INGEST_MAX_DOCUMENTS):
        raise ValueError(
            f"Bulk ingest accepts at most {settings.RAG_BULK_INGEST_MAX_DOCUMENTS} documents"
        )
    concurrency = max(1, settings.RAG_BULK_INGEST_CONCURRENCY)
    batch_size = max(1, settings.RAG_BULK_INGEST_BATCH_SIZE)
    semaphore = asyncio.Semaphore(concurrency)

    async def ingest_one(item: dict[str, Any]):
        async with semaphore, SessionLocal() as session:
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

    async def run_batch(batch: list[dict[str, Any]]) -> list[Any]:
        tasks = [asyncio.create_task(ingest_one(item)) for item in batch]
        try:
            return list(await asyncio.gather(*tasks))
        except asyncio.CancelledError:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
        except Exception:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise

    results: list[Any] = []
    for start in range(0, len(documents), batch_size):
        batch_results = await run_batch(documents[start : start + batch_size])
        results.extend(batch_results)
        log_rag_event(
            "bulk_ingest_batch_complete",
            project_id=project_id,
            count=len(batch_results),
            completed=len(results),
            total=len(documents),
        )
    return results
