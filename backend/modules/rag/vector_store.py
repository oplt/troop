from __future__ import annotations

from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.modules.memory.models import (
    ProjectDocument,
    ProjectDocumentChunk,
    normalize_embedding_for_vector,
)
from backend.modules.orchestration._helpers import _cosine_similarity, _estimate_embedding_tokens
from backend.modules.orchestration.repository import OrchestrationRepository
from backend.modules.rag.schemas import RagSearchFilters


class VectorStoreRepository(Protocol):
    async def upsert_document_chunks(
        self,
        document: ProjectDocument,
        chunks: list[tuple[int, str, int, list[float], dict[str, Any]]],
    ) -> None: ...

    async def search(
        self,
        project_id: str,
        query_vec: list[float],
        *,
        filters: RagSearchFilters,
        limit: int,
    ) -> list[dict[str, Any]]: ...

    async def text_search(
        self,
        project_id: str,
        query: str,
        *,
        filters: RagSearchFilters,
        limit: int,
    ) -> list[dict[str, Any]]: ...

    async def list_document_chunks_for_document(
        self, document_id: str
    ) -> list[ProjectDocumentChunk]: ...

    async def delete_document_vectors(self, project_id: str, document_id: str) -> None: ...

    async def list_chunks_fallback(
        self,
        project_id: str,
        *,
        filters: RagSearchFilters,
    ) -> list[ProjectDocumentChunk]: ...


class PgVectorStoreRepository:
    """Vector store backed by `project_document_chunks.embedding_vector`."""

    def __init__(self, db: AsyncSession):
        self._repo = OrchestrationRepository(db)
        self._db = db

    async def upsert_document_chunks(
        self,
        document: ProjectDocument,
        chunks: list[tuple[int, str, int, list[float], dict[str, Any]]],
    ) -> None:
        await self._repo.sync_document_chunks(document, chunks)

    async def search(
        self,
        project_id: str,
        query_vec: list[float],
        *,
        filters: RagSearchFilters,
        limit: int,
    ) -> list[dict[str, Any]]:
        return await self._repo.search_document_chunks_by_vector(
            project_id,
            normalize_embedding_for_vector(query_vec),
            task_id=filters.task_id,
            source_kind=filters.source_kind,
            top_k=limit,
        )

    async def text_search(
        self,
        project_id: str,
        query: str,
        *,
        filters: RagSearchFilters,
        limit: int,
    ) -> list[dict[str, Any]]:
        return await self._repo.search_document_chunks_by_text(
            project_id,
            query,
            task_id=filters.task_id,
            source_kind=filters.source_kind,
            top_k=limit,
        )

    async def list_document_chunks_for_document(
        self, document_id: str
    ) -> list[ProjectDocumentChunk]:
        return await self._repo.list_document_chunks_for_document(document_id)

    async def delete_document_vectors(self, project_id: str, document_id: str) -> None:
        document = await self._repo.get_document(project_id, document_id)
        if document is None:
            return
        await self._repo.replace_document_chunks(document, [])

    async def list_chunks_fallback(
        self,
        project_id: str,
        *,
        filters: RagSearchFilters,
    ) -> list[ProjectDocumentChunk]:
        return await self._repo.list_document_chunks(
            project_id,
            task_id=filters.task_id,
            source_kind=filters.source_kind,
            limit=settings.RAG_CHUNK_FALLBACK_MAX,
        )

    @staticmethod
    def estimate_tokens(text: str) -> int:
        return _estimate_embedding_tokens(text)

    @staticmethod
    def cosine_similarity(left: list[float], right: list[float]) -> float:
        return _cosine_similarity(left, right)
