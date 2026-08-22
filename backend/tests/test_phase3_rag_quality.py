from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from backend.core.config import settings
from backend.modules.memory.models import ProjectDocument
from backend.modules.rag.config import RagConfig
from backend.modules.rag.evaluation import RetrievalEvalCase, evaluate_retrieval_case
from backend.modules.rag.fusion import reciprocal_rank_fusion
from backend.modules.rag.retrieval import DocumentIngestionService, RetrieverService
from backend.modules.rag.schemas import RagChunk, RagChunkMatch, RagDocument, RagSearchFilters
from backend.modules.rag.selection import select_context_matches


def _match(
    chunk_id: str,
    *,
    document_id: str | None = None,
    content: str | None = None,
    score: float = 0.8,
    source_id: str | None = None,
) -> RagChunkMatch:
    return RagChunkMatch(
        chunk_id=chunk_id,
        document_id=document_id or f"doc-{chunk_id}",
        title=f"{chunk_id}.md",
        content=content or f"Unique content for {chunk_id}",
        chunk_index=0,
        score=score,
        metadata={"source_id": source_id or f"source-{chunk_id}"},
    )


def test_rrf_fuses_ranks_without_comparing_raw_scores():
    vector = [_match("vector-only", score=0.99), _match("both", score=0.2)]
    lexical = [_match("both", score=0.01), _match("lexical-only", score=50.0)]

    fused = reciprocal_rank_fusion([vector, lexical], limit=3)

    assert [item.chunk_id for item in fused] == ["both", "vector-only", "lexical-only"]
    assert fused[0].score == 1.0


def test_context_selection_enforces_dedup_quotas_diversity_and_tokens():
    matches = [
        _match("a1", document_id="doc-a", content="alpha beta gamma", source_id="source-a"),
        _match("a2", document_id="doc-a", content="alpha beta gamma", source_id="source-a"),
        _match("a3", document_id="doc-a", content="alpha delta", source_id="source-a"),
        _match("b1", document_id="doc-b", content="bravo distinct", source_id="source-b"),
        _match("c1", document_id="doc-c", content="too many tokens here", source_id="source-c"),
    ]

    selected = select_context_matches(
        matches,
        limit=5,
        max_context_tokens=7,
        max_chunks_per_document=2,
        max_chunks_per_source=2,
        dedup_similarity_threshold=0.9,
        estimate_tokens=lambda text: len(text.split()),
    )

    assert [item.chunk_id for item in selected] == ["a1", "b1", "a3"]
    assert sum(len(item.content.split()) for item in selected) <= 7


def test_python_fallback_requires_explicit_production_override():
    with (
        patch.object(settings, "APP_ENV", "production"),
        patch.object(settings, "RAG_PYTHON_FALLBACK_ENABLED", True),
        patch.object(settings, "RAG_ALLOW_PYTHON_FALLBACK_IN_PRODUCTION", False),
    ):
        assert RagConfig.from_settings().python_fallback_enabled is False

    with (
        patch.object(settings, "APP_ENV", "production"),
        patch.object(settings, "RAG_PYTHON_FALLBACK_ENABLED", True),
        patch.object(settings, "RAG_ALLOW_PYTHON_FALLBACK_IN_PRODUCTION", True),
    ):
        assert RagConfig.from_settings().python_fallback_enabled is True


@pytest.mark.asyncio
async def test_retriever_hybrid_search_uses_rrf_candidate_pool():
    vector_store = MagicMock()
    vector_store.search = AsyncMock(
        return_value=[
            {
                "chunk_id": "vector-only",
                "project_document_id": "doc-vector",
                "filename": "vector.md",
                "content": "semantic match",
                "chunk_index": 0,
                "score": 0.92,
                "metadata_json": {},
            },
            {
                "chunk_id": "both",
                "project_document_id": "doc-both",
                "filename": "both.md",
                "content": "TROOP-42 exact match",
                "chunk_index": 0,
                "score": 0.7,
                "metadata_json": {},
            },
        ]
    )
    vector_store.text_search = AsyncMock(
        return_value=[
            {
                "chunk_id": "both",
                "project_document_id": "doc-both",
                "filename": "both.md",
                "content": "TROOP-42 exact match",
                "chunk_index": 0,
                "score": 0.05,
                "metadata_json": {},
            }
        ]
    )
    embedder = MagicMock()
    embedder.embed_texts = AsyncMock(return_value=[[0.1, 0.2]])
    retriever = RetrieverService(
        MagicMock(),
        config=RagConfig(
            enabled=True,
            top_k=2,
            candidate_top_k=30,
            hybrid_search_enabled=True,
            score_threshold=0.2,
            score_threshold_local=0.2,
        ),
        vector_store=vector_store,
        embedder=embedder,
    )

    with (
        patch(
            "backend.modules.rag.retrieval.get_cached_rag_retrieval", AsyncMock(return_value=None)
        ),
        patch("backend.modules.rag.retrieval.set_cached_rag_retrieval", AsyncMock()),
    ):
        matches = await retriever.retrieve(
            "TROOP-42",
            filters=RagSearchFilters(user_id="user-1", project_id="project-1"),
        )

    assert [item.chunk_id for item in matches] == ["both", "vector-only"]
    vector_store.search.assert_awaited_once()
    vector_store.text_search.assert_awaited_once()
    assert vector_store.search.await_args.kwargs["limit"] == 30


@pytest.mark.asyncio
async def test_incremental_index_embeds_only_changed_content():
    document = ProjectDocument(
        id="doc-1",
        project_id="project-1",
        uploaded_by_user_id="user-1",
        filename="guide.md",
        content_type="text/markdown",
        source_text="safe source",
        metadata_json={},
    )
    normalized = RagDocument(
        document_id="doc-1",
        source_id="doc-1",
        source_type="markdown",
        title="guide.md",
        content="safe source",
        owner_user_id="user-1",
        project_id="project-1",
        checksum="checksum",
    )
    chunks = [
        RagChunk(
            chunk_id="chunk-old",
            document_id="doc-1",
            source_id="doc-1",
            source_type="markdown",
            title="guide.md",
            content="unchanged",
            chunk_index=0,
            content_hash="hash-old",
            owner_user_id="user-1",
            project_id="project-1",
        ),
        RagChunk(
            chunk_id="chunk-new",
            document_id="doc-1",
            source_id="doc-1",
            source_type="markdown",
            title="guide.md",
            content="changed",
            chunk_index=1,
            content_hash="hash-new",
            owner_user_id="user-1",
            project_id="project-1",
        ),
    ]
    parser = MagicMock()
    parser.normalize_document.return_value = normalized
    chunker = MagicMock()
    chunker.build_chunks.return_value = chunks
    embedder = MagicMock()
    embedder.embed_texts = AsyncMock(return_value=[[0.9, 0.8]])
    existing = MagicMock(
        metadata_json={"content_hash": "hash-old"},
        embedding_vector=[0.1, 0.2],
        embedding_json=[],
    )
    vector_store = MagicMock()
    vector_store.list_document_chunks_for_document = AsyncMock(return_value=[existing])
    vector_store.upsert_document_chunks = AsyncMock()
    db = MagicMock()
    db.flush = AsyncMock()

    service = DocumentIngestionService(
        db,
        parser=parser,
        chunker=chunker,
        embedder=embedder,
        vector_store=vector_store,
    )
    indexed = await service.index_project_document(document)

    assert indexed == 2
    embedder.embed_texts.assert_awaited_once_with(["changed"])
    rows = vector_store.upsert_document_chunks.await_args.args[1]
    assert rows[0][3] == [0.1, 0.2]
    assert rows[1][3] == [0.9, 0.8]


def test_eval_reports_rank_and_leakage_metrics():
    case = RetrievalEvalCase(
        query="policy",
        expected_chunk_ids=("expected",),
        forbidden_project_ids=("project-b",),
        acl_denied_chunk_ids=("denied",),
    )
    result = evaluate_retrieval_case(
        case,
        [
            _match("noise"),
            _match("expected"),
            RagChunkMatch(
                chunk_id="denied",
                document_id="doc-denied",
                title="secret",
                content="secret",
                chunk_index=0,
                score=0.1,
                metadata={"project_id": "project-b"},
            ),
        ],
    )

    assert result.reciprocal_rank == 0.5
    assert 0 < result.ndcg < 1
    assert result.cross_project_leakage is True
    assert result.acl_leakage is True
    assert result.passed is False
