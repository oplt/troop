"""Document chunk retrieval for AI Studio RAG."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from backend.core.config import settings
from backend.modules.identity_access.models import User
from backend.modules.orchestration._helpers import _cosine_similarity


class AiRetrievalMixin:
    async def retrieve_chunks(
        self,
        user: User,
        *,
        query: str,
        document_ids: list[str],
        top_k: int,
    ) -> list[dict[str, Any]]:
        allowed_docs = await self.repo.list_documents_for_user(user.id)
        allowed_doc_map = {
            document.id: document
            for document in allowed_docs
            if document.ingestion_status == "completed"
        }
        candidate_ids = document_ids or list(allowed_doc_map)
        invalid_ids = [
            document_id for document_id in candidate_ids if document_id not in allowed_doc_map
        ]
        if invalid_ids:
            raise HTTPException(status_code=404, detail="One or more documents were not found")
        query_embedding = (await self.providers.embed_texts([query]))[0]
        vector_hits = await self.repo.search_document_chunks_by_vector(
            user.id,
            candidate_ids,
            query_embedding,
            top_k=top_k,
        )
        if vector_hits:
            return [
                {
                    "document_id": str(row["document_id"]),
                    "chunk_id": str(row["chunk_id"]),
                    "document_title": str(row.get("document_title") or "document"),
                    "chunk_index": int(row.get("chunk_index") or 0),
                    "score": round(float(row.get("score") or 0.0), 4),
                    "content": str(row.get("content") or ""),
                }
                for row in vector_hits
            ]

        if not settings.AI_RETRIEVE_PYTHON_FALLBACK_ENABLED:
            return []

        chunks = await self.repo.list_document_chunks(
            candidate_ids,
            limit=settings.RAG_CHUNK_FALLBACK_MAX,
        )
        if not chunks:
            return []
        matches = []
        for chunk in chunks:
            if not chunk.embedding_json:
                continue
            score = _cosine_similarity(query_embedding, chunk.embedding_json)
            document = allowed_doc_map[chunk.document_id]
            matches.append(
                {
                    "document_id": chunk.document_id,
                    "chunk_id": chunk.id,
                    "document_title": document.title,
                    "chunk_index": chunk.chunk_index,
                    "score": round(score, 4),
                    "content": chunk.content,
                }
            )
        matches.sort(key=lambda item: item["score"], reverse=True)
        return matches[:top_k]
