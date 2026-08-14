"""Document chunking, embedding, and async ingest jobs."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.modules.ai.gateway.pricing import estimate_tokens as _estimate_tokens
from backend.modules.identity_access.models import User
from backend.modules.orchestration._helpers import _chunk_text
from backend.modules.orchestration.repository import OrchestrationRepository

logger = get_logger(__name__)


class AiDocumentIngestionMixin:
    def _validate_document_content(self, content: str) -> None:
        if not content.strip():
            raise HTTPException(status_code=422, detail="Document content must not be empty")
        if len(content.encode("utf-8")) > settings.AI_DOCUMENT_MAX_BYTES:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"Document exceeds the maximum size of {settings.AI_DOCUMENT_MAX_BYTES} bytes"
                ),
            )

    async def _index_ai_document(self, document) -> None:
        content = document.source_text or ""
        chunks = _chunk_text(
            content, settings.AI_DOCUMENT_CHUNK_SIZE, settings.AI_DOCUMENT_CHUNK_OVERLAP
        )
        embeddings = await self.providers.embed_texts(chunks) if chunks else []
        await self.repo.replace_document_chunks(
            document,
            [
                (index, chunk, _estimate_tokens(chunk), embeddings[index])
                for index, chunk in enumerate(chunks)
            ],
        )
        document.ingestion_status = "completed"
        document.chunk_count = len(chunks)
        document.updated_at = datetime.now(UTC)
        await self.db.flush()

    async def _queue_ai_document_ingest(self, user: User, document_id: str) -> str:
        job = await OrchestrationRepository(self.db).create_memory_ingest_job(
            owner_id=user.id,
            project_id=None,
            job_type="ai_document_ingest",
            payload_json={"document_id": document_id, "user_id": user.id},
            status="pending",
        )
        try:
            from backend.workers.orchestration import queue_memory_ingest_jobs

            queue_memory_ingest_jobs()
        except Exception as exc:
            logger.warning(
                "ai_document_ingest_queue_failed document_id=%s error=%s",
                document_id,
                exc,
            )
        return job.id

    async def process_ai_document_ingest_job(self, *, user_id: str, document_id: str) -> None:
        document = await self.repo.get_document_for_user(user_id, document_id)
        if document is None:
            raise RuntimeError("ai_document_ingest target not found")
        document.ingestion_status = "running"
        document.updated_at = datetime.now(UTC)
        await self.db.flush()
        try:
            await self._index_ai_document(document)
        except Exception as exc:
            document.ingestion_status = "failed"
            document.metadata_json = {
                **(document.metadata_json or {}),
                "ingest_error": str(exc)[:2000],
            }
            document.updated_at = datetime.now(UTC)
            await self.db.flush()
            raise

    async def create_document_from_text(
        self,
        user: User,
        *,
        title: str,
        description: str | None,
        content: str,
        content_type: str,
        filename: str | None = None,
        metadata: dict[str, Any] | None = None,
        queue_async: bool | None = None,
    ) -> tuple[Any, str | None]:
        self._validate_document_content(content)
        use_async = settings.AI_DOCUMENT_INGEST_ASYNC if queue_async is None else bool(queue_async)
        document = await self.repo.create_document(
            user_id=user.id,
            title=title,
            description=description,
            filename=filename,
            content_type=content_type,
            size_bytes=len(content.encode("utf-8")),
            ingestion_status="pending" if use_async else "completed",
            source_text=content,
            metadata_json=metadata or {},
            chunk_count=0,
        )
        ingest_job_id: str | None = None
        if use_async:
            ingest_job_id = await self._queue_ai_document_ingest(user, document.id)
        else:
            await self._index_ai_document(document)
        await self.db.commit()
        await self.db.refresh(document)
        return document, ingest_job_id
