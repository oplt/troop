from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.cache import invalidate_project_knowledge_caches
from backend.core.config import settings
from backend.modules.identity_access.models import User
from backend.modules.memory.models import ProjectDocument
from backend.modules.orchestration.models import ProviderConfig
from backend.modules.orchestration.repository import OrchestrationRepository
from backend.modules.projects.orchestration_models import OrchestratorProject
from backend.modules.rag.config import RagConfig, resolve_rag_config
from backend.modules.rag.observability import log_rag_event
from backend.modules.rag.parsing import PDF_UNSUPPORTED_DETAIL, detect_source_type
from backend.modules.rag.retrieval import (
    DocumentIngestionService,
    RagAnswerService,
    RetrieverService,
)
from backend.modules.rag.schemas import RagAnswer, RagChunkMatch, RagDocument, RagSearchFilters


class RagService:
    """Unified RAG facade over project document storage and pgvector retrieval."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        config: RagConfig | None = None,
    ):
        self._db = db
        self._config = config or resolve_rag_config()
        self._repo = OrchestrationRepository(db)
        self._retriever = RetrieverService(db, config=self._config)
        self._ingestion = DocumentIngestionService(db, config=self._config)
        self._answer = RagAnswerService(
            self._retriever,
            config=self._config,
            generation_config_resolver=self._resolve_answer_generation_config,
        )

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    async def _resolve_answer_generation_config(
        self,
        filters: RagSearchFilters,
    ) -> tuple[ProviderConfig | None, str, str]:
        if not filters.user_id or not filters.project_id:
            return None, settings.OPENAI_DEFAULT_MODEL, settings.AI_DEFAULT_PROVIDER
        project = await self._repo.get_project(filters.user_id, filters.project_id)
        execution = dict((project.settings_json or {}).get("execution") or {}) if project else {}
        provider: ProviderConfig | None = None
        provider_id = execution.get("provider_config_id")
        if provider_id:
            provider = await self._repo.get_provider(filters.user_id, str(provider_id))
        if provider is None:
            providers = [
                item
                for item in await self._repo.list_providers(filters.user_id, filters.project_id)
                if item.is_enabled
            ]
            provider = next((item for item in providers if item.is_default), None) or (
                providers[0] if providers else None
            )

        model = str(execution.get("model_name") or "").strip()
        if not model and provider is not None:
            model = str(provider.default_model or "").strip()
        if not model:
            model = settings.OPENAI_DEFAULT_MODEL

        provider_key = self._provider_key_for_rag(provider)
        return provider, model, provider_key

    @staticmethod
    def _provider_key_for_rag(provider: ProviderConfig | None) -> str:
        if provider is None:
            return settings.AI_DEFAULT_PROVIDER
        provider_type = str(provider.provider_type or "").strip().lower()
        if provider_type in {"openai", "openai_compatible"}:
            return "openai"
        if provider_type == "anthropic":
            return "anthropic"
        if provider_type in {"local", "ollama"}:
            return "local"
        return settings.AI_DEFAULT_PROVIDER

    async def index_document(self, document_id: str, *, project_id: str) -> int:
        if not self._config.enabled:
            return 0
        document = await self._repo.get_document(project_id, document_id)
        if document is None:
            raise HTTPException(status_code=404, detail="Document not found")
        count = await self._ingestion.index_project_document(document)
        await self._db.commit()
        return count

    async def reindex_document(self, document_id: str, *, project_id: str) -> int:
        return await self.index_document(document_id, project_id=project_id)

    async def retrieve(
        self,
        query: str,
        *,
        filters: RagSearchFilters,
        limit: int | None = None,
    ) -> list[RagChunkMatch]:
        if not self._config.enabled:
            return []
        return await self._retriever.retrieve(query, filters=filters, limit=limit)

    async def build_context(
        self,
        query: str,
        *,
        filters: RagSearchFilters,
        limit: int | None = None,
    ) -> str:
        if not self._config.enabled:
            return ""
        return await self._retriever.build_context(query, filters=filters, limit=limit)

    async def answer(
        self,
        query: str,
        *,
        filters: RagSearchFilters,
        limit: int | None = None,
    ) -> RagAnswer:
        if not self._config.enabled:
            return RagAnswer(
                query=query,
                answer=(
                    "RAG is disabled. Enable RAG_ENABLED to generate grounded answers "
                    "from project knowledge."
                ),
                citations=[],
                grounded=False,
                context_found=False,
            )
        try:
            return await asyncio.wait_for(
                self._answer.answer(query, filters=filters, limit=limit),
                timeout=settings.RAG_ANSWER_TIMEOUT_SECONDS,
            )
        except TimeoutError as exc:
            raise HTTPException(status_code=504, detail="RAG answer timed out") from exc

    async def answer_stream(
        self,
        query: str,
        *,
        filters: RagSearchFilters,
        limit: int | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        if not self._config.enabled:
            yield {
                "type": "done",
                "query": query,
                "answer": (
                    "RAG is disabled. Enable RAG_ENABLED to generate grounded answers "
                    "from project knowledge."
                ),
                "grounded": False,
                "context_found": False,
                "citations": [],
                "model": "",
                "provider": "",
            }
            return
        async for event in self._answer.answer_stream(query, filters=filters, limit=limit):
            yield event

    async def delete_document(self, document_id: str, *, project_id: str) -> None:
        document = await self._repo.get_document(project_id, document_id)
        if document is None:
            raise HTTPException(status_code=404, detail="Document not found")
        await self._retriever._vector_store.delete_document_vectors(project_id, document_id)  # noqa: SLF001
        document.deleted_at = datetime.now(UTC)
        document.updated_at = datetime.now(UTC)
        await self._db.commit()
        await invalidate_project_knowledge_caches(project_id)
        log_rag_event("delete_document", project_id=project_id, document_id=document_id)

    async def ingest_text(
        self,
        user: User,
        project: OrchestratorProject,
        *,
        title: str,
        content: str,
        task_id: str | None = None,
        source_type: str | None = None,
        metadata: dict[str, Any] | None = None,
        ttl_days: int | None = None,
        queue_async: bool = True,
    ) -> ProjectDocument:
        if len(content.encode("utf-8")) > settings.AI_DOCUMENT_MAX_BYTES:
            raise HTTPException(status_code=413, detail="Document exceeds maximum size")

        st = source_type or detect_source_type("text/plain", title)
        if st == "pdf":
            raise HTTPException(status_code=400, detail=PDF_UNSUPPORTED_DETAIL)
        meta = dict(metadata or {})
        meta.setdefault("source_kind", "rag_ingest")
        meta.setdefault("source_type", st)

        document = await self._repo.create_document(
            project_id=project.id,
            task_id=task_id,
            uploaded_by_user_id=user.id,
            filename=title,
            content_type="text/plain",
            source_text=content,
            object_key=None,
            size_bytes=len(content.encode("utf-8")),
            summary_text=content[:500],
            ingestion_status="pending",
            chunk_count=0,
            ttl_days=ttl_days,
            expires_at=(datetime.now(UTC) + timedelta(days=ttl_days)) if ttl_days else None,
            metadata_json=meta,
        )
        if queue_async and self._config.enabled:
            await self._repo.create_memory_ingest_job(
                owner_id=user.id,
                project_id=project.id,
                job_type="document_ingest",
                payload_json={"project_id": project.id, "document_id": document.id},
                status="pending",
            )
        elif self._config.enabled:
            await self._ingestion.index_project_document(document)
        await self._db.commit()
        await self._db.refresh(document)
        log_rag_event(
            "ingest_queued" if queue_async else "ingest_complete",
            user_id=user.id,
            project_id=project.id,
            document_id=document.id,
        )
        return document

    async def ingest_upload(
        self,
        user: User,
        project: OrchestratorProject,
        file: UploadFile,
        *,
        task_id: str | None = None,
        ttl_days: int | None = None,
        queue_async: bool = True,
    ) -> ProjectDocument:
        payload = await file.read()
        if not payload:
            raise HTTPException(status_code=400, detail="Uploaded document is empty")
        source_type = detect_source_type(file.content_type, file.filename)
        if source_type == "pdf":
            raise HTTPException(status_code=400, detail=PDF_UNSUPPORTED_DETAIL)
        try:
            content = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(
                status_code=400, detail="Document must be valid UTF-8 text"
            ) from exc
        return await self.ingest_text(
            user,
            project,
            title=file.filename or "document.md",
            content=content,
            task_id=task_id,
            source_type=source_type,
            metadata={"content_type": file.content_type or "text/plain"},
            ttl_days=ttl_days,
            queue_async=queue_async,
        )

    def to_rag_document(self, row: ProjectDocument) -> RagDocument:
        return RagDocument(
            document_id=row.id,
            source_id=row.id,
            source_type=detect_source_type(row.content_type, row.filename),
            title=row.filename,
            content=row.source_text,
            owner_user_id=row.uploaded_by_user_id,
            project_id=row.project_id,
            metadata=dict(row.metadata_json or {}),
            checksum=str((row.metadata_json or {}).get("checksum") or ""),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
