from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.tools.rag_eval_gate import run_gate
from backend.modules.rag.config import RagConfig
from backend.modules.rag.evaluation import (
    RetrievalEvalCase,
    answer_is_grounded,
    evaluate_retrieval_case,
)
from backend.modules.rag.retrieval import RetrieverService
from backend.modules.rag.schemas import RagAnswer, RagChunkMatch, RagCitation, RagSearchFilters


@pytest.mark.asyncio
async def test_golden_retrieval_prefers_high_score_chunk():
    """Minimal golden-set: query should return the highest-scoring known chunk first."""
    db = MagicMock()
    retriever = RetrieverService(db, config=RagConfig(enabled=True, score_threshold=0.2, top_k=3))
    retriever._embedder = MagicMock()
    retriever._embedder.embed_texts = AsyncMock(return_value=[[0.1, 0.2]])
    retriever._vector_store = MagicMock()
    retriever._vector_store.search = AsyncMock(
        return_value=[
            {
                "chunk_id": "golden-auth-middleware",
                "project_document_id": "doc-auth",
                "filename": "auth.md",
                "content": "JWT middleware validates bearer tokens on every API request.",
                "chunk_index": 0,
                "score": 0.92,
                "metadata_json": {},
            },
            {
                "chunk_id": "noise-footer",
                "project_document_id": "doc-misc",
                "filename": "footer.md",
                "content": "Copyright notice and unrelated footer links.",
                "chunk_index": 0,
                "score": 0.21,
                "metadata_json": {},
            },
        ]
    )
    retriever._reranker = MagicMock()
    retriever._reranker.rerank = lambda _q, items: items

    with (
        patch("backend.modules.rag.retrieval.get_cached_rag_retrieval", AsyncMock(return_value=None)),
        patch("backend.modules.rag.retrieval.set_cached_rag_retrieval", AsyncMock()),
    ):
        matches = await retriever.retrieve(
            "JWT middleware auth",
            filters=RagSearchFilters(user_id="u1", project_id="p1"),
        )

    assert matches
    assert matches[0].chunk_id == "golden-auth-middleware"
    assert matches[0].score >= 0.9


def test_retrieval_eval_fails_on_missing_expected_chunk():
    case = RetrievalEvalCase(
        query="JWT middleware auth",
        expected_chunk_ids=("golden-auth-middleware",),
        negative_chunk_ids=("noise-footer",),
    )
    result = evaluate_retrieval_case(
        case,
        [
            RagChunkMatch(
                chunk_id="noise-footer",
                document_id="doc-misc",
                title="footer.md",
                content="Copyright notice.",
                chunk_index=0,
                score=0.99,
            )
        ],
    )

    assert not result.passed
    assert result.missing_chunk_ids == ("golden-auth-middleware",)
    assert result.unexpected_chunk_ids == ("noise-footer",)


def test_retrieval_eval_allows_partial_recall_threshold():
    case = RetrievalEvalCase(
        query="auth and csrf",
        expected_chunk_ids=("golden-auth-middleware", "golden-csrf-token"),
        min_recall=0.5,
    )
    result = evaluate_retrieval_case(
        case,
        [
            RagChunkMatch(
                chunk_id="golden-auth-middleware",
                document_id="doc-auth",
                title="auth.md",
                content="JWT middleware validates bearer tokens.",
                chunk_index=0,
                score=0.91,
            )
        ],
    )

    assert result.passed
    assert result.recall == 0.5


def test_answer_grounding_requires_context_citations_and_valid_markers():
    answer = RagAnswer(
        query="How is auth checked?",
        answer="Auth uses middleware [source:golden-auth-middleware].",
        citations=[
            RagCitation(
                source_index=1,
                chunk_id="golden-auth-middleware",
                document_id="doc-auth",
                title="auth.md",
                chunk_index=0,
                score=0.92,
                excerpt="JWT middleware validates bearer tokens.",
            )
        ],
        grounded=True,
        context_found=True,
    )

    assert answer_is_grounded(answer)


def test_answer_grounding_rejects_unknown_source_marker():
    answer = RagAnswer(
        query="How is auth checked?",
        answer="Auth uses middleware [source:missing].",
        citations=[
            RagCitation(
                source_index=1,
                chunk_id="golden-auth-middleware",
                document_id="doc-auth",
                title="auth.md",
                chunk_index=0,
                score=0.92,
                excerpt="JWT middleware validates bearer tokens.",
            )
        ],
        grounded=True,
        context_found=True,
    )

    assert not answer_is_grounded(answer)


def test_rag_eval_gate_passes_committed_golden_fixture():
    assert run_gate(
        Path("backend/tests/fixtures/rag_eval_golden.json"),
        min_pass_rate=1.0,
    ) == 0
