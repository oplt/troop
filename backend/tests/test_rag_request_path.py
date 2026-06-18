from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from backend.modules.ai.providers import AiProviderRegistry, ProviderGenerateRequest, ProviderGenerateResult
from backend.modules.rag.bulk_ingest import bulk_ingest_documents_parallel
from backend.modules.rag.config import RagConfig
from backend.modules.rag.schemas import RagSearchFilters
from backend.modules.rag.service import RagService


@pytest.mark.asyncio
async def test_rag_answer_times_out():
    class _FakeSession:
        async def commit(self) -> None:
            return None

    service = RagService(_FakeSession(), config=RagConfig(enabled=True))  # type: ignore[arg-type]

    async def slow_answer(*_args, **_kwargs):
        await asyncio.sleep(0.05)
        return MagicMock()

    with patch.object(service._answer, "answer", side_effect=slow_answer):
        with patch("backend.modules.rag.service.settings.RAG_ANSWER_TIMEOUT_SECONDS", 0.01):
            with pytest.raises(HTTPException) as exc:
                await service.answer("query", filters=RagSearchFilters(user_id="u1", project_id="p1"))
            assert exc.value.status_code == 504


@pytest.mark.asyncio
async def test_rag_answer_stream_yields_tokens_and_done():
    class _FakeSession:
        async def commit(self) -> None:
            return None

    service = RagService(_FakeSession(), config=RagConfig(enabled=True))  # type: ignore[arg-type]

    async def fake_stream(*_args, **_kwargs):
        yield {"type": "meta", "context_found": True, "citations": []}
        yield {"type": "token", "text": "Hello"}
        yield {"type": "done", "answer": "Hello", "grounded": True, "context_found": True}

    with patch.object(service._answer, "answer_stream", side_effect=fake_stream):
        events = [event async for event in service.answer_stream("q", filters=RagSearchFilters(project_id="p1"))]
    assert events[0]["type"] == "meta"
    assert events[1]["text"] == "Hello"
    assert events[-1]["type"] == "done"


@pytest.mark.asyncio
async def test_provider_registry_generate_delegates():
    registry = AiProviderRegistry()
    request = ProviderGenerateRequest(
        model="local-heuristic",
        system_prompt="sys",
        user_prompt="user",
        response_format="text",
        temperature=0.0,
    )
    result = await registry.generate(request)
    assert isinstance(result, ProviderGenerateResult)
    assert result.output_text


@pytest.mark.asyncio
async def test_provider_registry_stream_generate_yields_text():
    registry = AiProviderRegistry()
    request = ProviderGenerateRequest(
        model="local-heuristic",
        system_prompt="sys",
        user_prompt="user",
        response_format="text",
        temperature=0.0,
    )
    chunks = [chunk async for chunk in registry.stream_generate(request)]
    assert chunks
    assert any("Heuristic" in chunk or "user" in chunk for chunk in chunks)


@pytest.mark.asyncio
async def test_bulk_ingest_documents_parallel_uses_gather():
    user = MagicMock()
    user.id = "user-1"

    async def fake_ingest_text(*_args, title: str, **_kwargs):
        doc = MagicMock()
        doc.id = title
        return doc

    with patch("backend.modules.rag.bulk_ingest.SessionLocal") as session_local:
        session = AsyncMock()
        session_local.return_value.__aenter__.return_value = session
        with patch("backend.modules.rag.bulk_ingest.OrchestrationService") as orch_cls:
            with patch("backend.modules.rag.bulk_ingest.RagService") as rag_cls:
                orch_cls.return_value.get_project = AsyncMock(return_value=MagicMock(id="p1"))
                rag_cls.return_value.ingest_text = AsyncMock(side_effect=fake_ingest_text)
                rows = await bulk_ingest_documents_parallel(
                    user,
                    "p1",
                    documents=[{"title": "a", "content": "A"}, {"title": "b", "content": "B"}],
                    task_id=None,
                    queue_async=True,
                )
    assert len(rows) == 2
