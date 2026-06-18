from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.modules.ai.service import AiService


@pytest.mark.asyncio
async def test_create_document_from_text_queues_async_ingest():
    service = AiService(MagicMock())
    service.repo = MagicMock()
    service.repo.create_document = AsyncMock(
        return_value=MagicMock(id="doc-1", ingestion_status="pending", chunk_count=0)
    )
    service.repo.replace_document_chunks = AsyncMock()
    service._queue_ai_document_ingest = AsyncMock(return_value="job-1")
    service._index_ai_document = AsyncMock()
    service.db = MagicMock()
    service.db.commit = AsyncMock()
    service.db.refresh = AsyncMock()

    user = MagicMock(id="user-1")
    with patch("backend.modules.ai.service.settings.AI_DOCUMENT_INGEST_ASYNC", True):
        document, job_id = await service.create_document_from_text(
            user,
            title="Notes",
            description=None,
            content="Hello world from async ingest test.",
            content_type="text/plain",
        )

    assert job_id == "job-1"
    assert document.id == "doc-1"
    service._queue_ai_document_ingest.assert_awaited_once_with(user, "doc-1")
    service._index_ai_document.assert_not_called()


@pytest.mark.asyncio
async def test_create_document_from_text_indexes_sync_when_async_disabled():
    service = AiService(MagicMock())
    service.repo = MagicMock()
    service.repo.create_document = AsyncMock(
        return_value=MagicMock(id="doc-2", ingestion_status="completed", chunk_count=2)
    )
    service._queue_ai_document_ingest = AsyncMock()
    service._index_ai_document = AsyncMock()
    service.db = MagicMock()
    service.db.commit = AsyncMock()
    service.db.refresh = AsyncMock()

    user = MagicMock(id="user-1")
    with patch("backend.modules.ai.service.settings.AI_DOCUMENT_INGEST_ASYNC", True):
        _document, job_id = await service.create_document_from_text(
            user,
            title="Notes",
            description=None,
            content="Sync path content.",
            content_type="text/plain",
            queue_async=False,
        )

    assert job_id is None
    service._index_ai_document.assert_awaited_once()
    service._queue_ai_document_ingest.assert_not_called()


@pytest.mark.asyncio
async def test_process_ai_document_ingest_job_marks_failed_on_error():
    service = AiService(MagicMock())
    document = MagicMock(
        id="doc-3",
        source_text="content",
        metadata_json={},
        ingestion_status="pending",
    )
    service.repo = MagicMock()
    service.repo.get_document_for_user = AsyncMock(return_value=document)
    service._index_ai_document = AsyncMock(side_effect=RuntimeError("embed failed"))
    service.db = MagicMock()
    service.db.flush = AsyncMock()

    with pytest.raises(RuntimeError, match="embed failed"):
        await service.process_ai_document_ingest_job(user_id="user-1", document_id="doc-3")

    assert document.ingestion_status == "failed"
    assert "ingest_error" in document.metadata_json
