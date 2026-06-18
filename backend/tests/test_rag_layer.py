from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.modules.rag.chunking import ChunkingService
from backend.modules.rag.config import RagConfig
from backend.modules.rag.parsing import DocumentParser, content_checksum, detect_source_type
from backend.modules.rag.prompt_builder import RagPromptBuilder
from backend.modules.rag.reranker import RerankerService
from backend.modules.rag.schemas import RagChunkMatch, RagSearchFilters
from backend.modules.rag.service import RagService


def test_chunking_preserves_order_and_overlap():
    chunker = ChunkingService(RagConfig(chunk_size=40, chunk_overlap=10))
    text = "alpha beta gamma delta epsilon zeta eta theta iota kappa"
    parts = chunker.split_text(text)
    assert len(parts) >= 2
    assert parts[0].startswith("alpha")


def test_chunking_builds_stable_hashes():
    chunker = ChunkingService(RagConfig(chunk_size=120, chunk_overlap=20))
    chunks = chunker.build_chunks(
        document_id="doc1",
        source_id="doc1",
        source_type="markdown",
        title="Guide",
        content="## Setup\nInstall dependencies.\n## Run\nStart the server.",
        owner_user_id="u1",
        project_id="p1",
    )
    assert chunks
    assert chunks[0].chunk_index == 0
    assert chunks[0].content_hash
    assert chunks[0].metadata["content_hash"] == chunks[0].content_hash


def test_document_parser_normalizes_html_and_json():
    parser = DocumentParser()
    html_doc = parser.normalize_document(
        document_id="d1",
        source_id="d1",
        source_type="html",
        title="Page",
        content="<html><body><h1>Title</h1><script>x</script><p>Body</p></body></html>",
        owner_user_id="u1",
        project_id="p1",
    )
    assert "Title" in html_doc.content
    assert "<" not in html_doc.content

    json_doc = parser.normalize_document(
        document_id="d2",
        source_id="d2",
        source_type="json",
        title="Config",
        content='{"env":"prod","feature_flags":{"rag":true}}',
        owner_user_id="u1",
        project_id="p1",
    )
    assert "feature_flags" in json_doc.content
    assert json_doc.checksum == content_checksum(json_doc.content)


def test_detect_source_type_from_filename():
    assert detect_source_type("text/markdown", "README.md") == "markdown"
    assert detect_source_type(None, "main.py") == "code"


def test_prompt_builder_formats_sources_and_no_context_message():
    builder = RagPromptBuilder()
    matches = [
        RagChunkMatch(
            chunk_id="c1",
            document_id="d1",
            title="README.md",
            content="Troop uses pgvector for project knowledge.",
            chunk_index=0,
            score=0.91,
        )
    ]
    block = builder.build_context_block(matches)
    assert block.startswith("Relevant retrieved context:")
    assert "Document ID: d1" in block
    assert "Chunk ID: c1" in block
    assert "pgvector" in block
    assert builder.no_context_answer().startswith("I do not have enough information")


def test_reranker_boosts_keyword_overlap():
    reranker = RerankerService(enabled=True)
    matches = [
        RagChunkMatch(
            chunk_id="a",
            document_id="d1",
            title="Unrelated",
            content="Something else entirely.",
            chunk_index=0,
            score=0.5,
        ),
        RagChunkMatch(
            chunk_id="b",
            document_id="d2",
            title="Redis guide",
            content="Redis is used for Celery broker configuration.",
            chunk_index=1,
            score=0.48,
        ),
    ]
    ranked = reranker.rerank("Redis Celery broker", matches)
    assert ranked[0].chunk_id == "b"


@pytest.mark.asyncio
async def test_rag_service_disabled_answer():
    class _FakeSession:
        async def commit(self) -> None:
            return None

    service = RagService(_FakeSession(), config=RagConfig(enabled=False))  # type: ignore[arg-type]
    result = await service.answer(
        "How is Redis configured?",
        filters=RagSearchFilters(user_id="u1", project_id="p1"),
    )
    assert result.context_found is False
    assert "disabled" in result.answer.lower()


@pytest.mark.asyncio
async def test_rag_index_blocks_redacted_secrets():
    from backend.modules.memory.models import ProjectDocument
    from backend.modules.rag.retrieval import DocumentIngestionService

    db = MagicMock()
    db.flush = AsyncMock()
    document = ProjectDocument(
        id="doc-1",
        project_id="proj-1",
        uploaded_by_user_id="user-1",
        filename="secrets.env",
        content_type="text/plain",
        source_text="export OPENAI_API_KEY=sk-test12345678901234567890123456789012",
        metadata_json={},
        ingestion_status="pending",
        chunk_count=0,
    )
    service = DocumentIngestionService(db)
    indexed = await service.index_project_document(document)
    assert indexed == 0
    assert document.ingestion_status == "failed"
    assert document.metadata_json.get("ingest_error") == "blocked_by_redaction"

    class _FakeSession:
        async def commit(self) -> None:
            return None

    service = RagService(_FakeSession(), config=RagConfig(enabled=False))  # type: ignore[arg-type]
    assert await service.retrieve("query", filters=RagSearchFilters(project_id="p1")) == []
    assert await service.build_context("query", filters=RagSearchFilters(project_id="p1")) == ""
