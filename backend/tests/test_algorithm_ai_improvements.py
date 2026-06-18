from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from backend.modules.ai.providers import AiProviderRegistry, ProviderGenerateRequest
from backend.modules.memory.layer.redaction import redact_sensitive_content
from backend.modules.orchestration.context_packet import ContextPacket, dedupe_context_sections
from backend.modules.orchestration.tools import OrchestrationToolbox
from backend.modules.rag.config import RagConfig
from backend.modules.rag.parsing import DocumentParser, PDF_UNSUPPORTED_DETAIL
from backend.modules.rag.schemas import RagChunkMatch
from backend.modules.rag.service import RagService


def test_rag_config_local_score_threshold():
    cfg = RagConfig(embedding_provider="local", score_threshold=0.2, score_threshold_local=0.05)
    assert cfg.effective_score_threshold() == 0.05
    cfg_openai = RagConfig(embedding_provider="openai", score_threshold=0.2, score_threshold_local=0.05)
    assert cfg_openai.effective_score_threshold() == 0.2


def test_pdf_parser_rejects_stub_extraction():
    parser = DocumentParser()
    with pytest.raises(ValueError, match="PDF upload is not supported"):
        parser.parse(content=b"%PDF-1.4", source_type="pdf", title="spec.pdf")


@pytest.mark.asyncio
async def test_rag_service_rejects_pdf_upload():
    class _FakeSession:
        async def commit(self) -> None:
            return None

    service = RagService(_FakeSession())  # type: ignore[arg-type]
    user = MagicMock(id="user-1")
    project = MagicMock(id="project-1")
    with pytest.raises(HTTPException) as exc:
        await service.ingest_text(
            user,
            project,
            title="spec.pdf",
            content="ignored",
            source_type="pdf",
        )
    assert exc.value.status_code == 400
    assert PDF_UNSUPPORTED_DETAIL in str(exc.value.detail)


def test_dedupe_context_sections_drops_duplicate_memory():
    sections = {
        "task_title": "Task title: Auth middleware",
        "semantic_memory": "Semantic memory:\n- Use JWT for API auth",
        "knowledge": "Additional context:\n- Use JWT for API auth",
        "comments": "Recent comments:\nLooks good",
    }
    deduped = dedupe_context_sections(sections)
    assert "task_title" in deduped
    assert "semantic_memory" in deduped
    assert "knowledge" not in deduped
    assert "comments" in deduped


def test_context_packet_token_cap_keeps_high_score_sections():
    packet = ContextPacket(
        sections={
            "task_title": "Task title: Keep auth middleware correct",
            "comments": "Recent comments:\n" + "low signal " * 200,
            "acceptance": "Acceptance criteria: enforce JWT and CSRF checks",
        }
    )

    prompt = packet.combined_user_prompt(
        max_tokens=18,
        section_token_budgets={"comments": 200, "task_title": 80, "acceptance": 80},
        section_priority_scores={"comments": 0.01},
    )

    assert "Task title" in prompt
    assert "Acceptance criteria" in prompt
    assert "low signal" not in prompt


def test_redaction_env_var_assignment():
    text = "export DATABASE_URL=postgres://user:pass@db:5432/app\nok line"
    redacted, matched = redact_sensitive_content(text)
    assert "env_var" in matched
    assert "DATABASE_URL=postgres" not in redacted
    assert "ok line" in redacted


@pytest.mark.asyncio
async def test_knowledge_search_uses_rag_retrieve():
    toolbox = OrchestrationToolbox(
        db=MagicMock(),
        repo=MagicMock(),
        project=MagicMock(id="project-1"),
        task=None,
        run=MagicMock(triggered_by_user_id="user-1"),
    )
    match = RagChunkMatch(
        chunk_id="c1",
        document_id="d1",
        title="Policy",
        content="Return policy details",
        chunk_index=0,
        score=0.88,
    )
    mock_rag = MagicMock()
    mock_rag.retrieve = AsyncMock(return_value=[match])

    with patch("backend.modules.rag.service.RagService", return_value=mock_rag):
        result = await toolbox._knowledge_search({"query": "return policy", "limit": 2})

    assert result["retrieval"] == "vector"
    assert result["items"][0]["document_id"] == "d1"
    mock_rag.retrieve.assert_awaited_once()


@pytest.mark.asyncio
async def test_provider_generate_retries_transient_errors():
    registry = AiProviderRegistry()
    local = registry.get("local")
    calls = {"count": 0}
    original_generate = local.generate

    async def flaky_generate(request):
        calls["count"] += 1
        if calls["count"] < 2:
            raise TimeoutError("transient")
        return await original_generate(request)

    local.generate = flaky_generate  # type: ignore[method-assign]
    request = ProviderGenerateRequest(
        model="local-heuristic",
        system_prompt="sys",
        user_prompt="hello",
        response_format="text",
        temperature=0.0,
    )
    result = await registry.generate(request, provider_key="local", max_attempts=3)
    assert result.output_text
    assert calls["count"] == 2
