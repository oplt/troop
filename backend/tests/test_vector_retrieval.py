from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.modules.ai.service import AiService
from backend.modules.rag.config import RagConfig
from backend.modules.rag.retrieval import RetrieverService
from backend.modules.rag.schemas import RagSearchFilters


@pytest.mark.asyncio
async def test_rag_skips_python_fallback_when_disabled():
    db = MagicMock()
    retriever = RetrieverService(db, config=RagConfig(enabled=True, python_fallback_enabled=False))
    retriever._embedder = MagicMock()
    retriever._embedder.embed_texts = AsyncMock(return_value=[[0.1, 0.2]])
    retriever._vector_store = MagicMock()
    retriever._vector_store.search = AsyncMock(return_value=[])
    retriever._fallback_search = AsyncMock(return_value=[MagicMock(score=0.9)])
    retriever._reranker = MagicMock()
    retriever._reranker.rerank = lambda _q, items: items

    with patch("backend.modules.rag.retrieval.get_cached_rag_retrieval", AsyncMock(return_value=None)):
        with patch("backend.modules.rag.retrieval.set_cached_rag_retrieval", AsyncMock()):
            matches = await retriever.retrieve(
                "redis config",
                filters=RagSearchFilters(user_id="u1", project_id="p1"),
            )

    assert matches == []
    retriever._fallback_search.assert_not_called()


@pytest.mark.asyncio
async def test_rag_uses_python_fallback_when_enabled():
    db = MagicMock()
    retriever = RetrieverService(db, config=RagConfig(enabled=True, python_fallback_enabled=True))
    retriever._embedder = MagicMock()
    retriever._embedder.embed_texts = AsyncMock(return_value=[[0.1, 0.2]])
    retriever._vector_store = MagicMock()
    retriever._vector_store.search = AsyncMock(return_value=[])
    fallback_match = MagicMock(score=0.95)
    retriever._fallback_search = AsyncMock(return_value=[fallback_match])
    retriever._reranker = MagicMock()
    retriever._reranker.rerank = lambda _q, items: items

    with patch("backend.modules.rag.retrieval.get_cached_rag_retrieval", AsyncMock(return_value=None)):
        with patch("backend.modules.rag.retrieval.set_cached_rag_retrieval", AsyncMock()):
            matches = await retriever.retrieve(
                "redis config",
                filters=RagSearchFilters(user_id="u1", project_id="p1"),
            )

    retriever._fallback_search.assert_awaited_once()
    assert matches == [fallback_match]


@pytest.mark.asyncio
async def test_ai_retrieve_chunks_prefers_pgvector():
    service = AiService(MagicMock())
    service.repo = MagicMock()
    service.repo.list_documents_for_user = AsyncMock(
        return_value=[MagicMock(id="doc-1", ingestion_status="completed", title="Doc")]
    )
    service.repo.search_document_chunks_by_vector = AsyncMock(
        return_value=[
            {
                "document_id": "doc-1",
                "chunk_id": "chunk-1",
                "document_title": "Doc",
                "chunk_index": 0,
                "score": 0.88,
                "content": "vector hit",
            }
        ]
    )
    service.repo.list_document_chunks = AsyncMock()
    service.providers = MagicMock()
    service.providers.embed_texts = AsyncMock(return_value=[[0.1, 0.2]])

    user = MagicMock(id="user-1")
    with patch("backend.modules.ai.service.settings.AI_RETRIEVE_PYTHON_FALLBACK_ENABLED", False):
        matches = await service.retrieve_chunks(
            user,
            query="hello",
            document_ids=["doc-1"],
            top_k=3,
        )

    assert len(matches) == 1
    assert matches[0]["chunk_id"] == "chunk-1"
    service.repo.list_document_chunks.assert_not_called()


@pytest.mark.asyncio
async def test_ai_retrieve_chunks_python_fallback_is_capped_and_optional():
    service = AiService(MagicMock())
    doc = MagicMock(id="doc-1", ingestion_status="completed", title="Doc")
    service.repo = MagicMock()
    service.repo.list_documents_for_user = AsyncMock(return_value=[doc])
    service.repo.search_document_chunks_by_vector = AsyncMock(return_value=[])
    chunk = MagicMock(
        id="chunk-1",
        document_id="doc-1",
        chunk_index=0,
        content="fallback",
        embedding_json=[1.0, 0.0],
    )
    service.repo.list_document_chunks = AsyncMock(return_value=[chunk])
    service.providers = MagicMock()
    service.providers.embed_texts = AsyncMock(return_value=[[1.0, 0.0]])

    user = MagicMock(id="user-1")
    with patch("backend.modules.ai.service.settings.AI_RETRIEVE_PYTHON_FALLBACK_ENABLED", True):
        with patch("backend.modules.ai.service.settings.RAG_CHUNK_FALLBACK_MAX", 200):
            matches = await service.retrieve_chunks(
                user,
                query="hello",
                document_ids=["doc-1"],
                top_k=3,
            )

    service.repo.list_document_chunks.assert_awaited_once_with(["doc-1"], limit=200)
    assert matches[0]["chunk_id"] == "chunk-1"
