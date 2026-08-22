from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from backend.api.deps.auth import get_current_user
from backend.db.session import get_db
from backend.modules.rag.router import (
    RagBulkIngestRequest,
    bulk_ingest_documents,
    get_rag_document,
    router,
)
from fastapi import FastAPI


def _document(document_id: str, title: str) -> SimpleNamespace:
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=document_id,
        filename=title,
        uploaded_by_user_id="user-1",
        project_id="project-1",
        chunk_count=1,
        ingestion_status="pending",
        metadata_json={"source_type": "text", "checksum": f"checksum-{document_id}"},
        created_at=now,
        updated_at=now,
    )


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/rag")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id="user-1")

    async def fake_db():
        yield AsyncMock()

    app.dependency_overrides[get_db] = fake_db
    return app


def test_bulk_document_route_is_present_in_openapi() -> None:
    schema = _app().openapi()

    operation = schema["paths"]["/api/v1/rag/projects/{project_id}/documents/bulk"]["post"]

    assert operation["responses"]["201"]
    request_schema = operation["requestBody"]["content"]["application/json"]["schema"]
    assert request_schema["$ref"].endswith("RagBulkIngestRequest")


@pytest.mark.asyncio
async def test_bulk_document_route_accepts_multiple_documents() -> None:
    rows = [_document("doc-1", "Architecture"), _document("doc-2", "Runbook")]
    payload = RagBulkIngestRequest.model_validate(
        {
            "documents": [
                {"title": "Architecture", "content": "System boundaries"},
                {"title": "Runbook", "content": "Recovery steps"},
            ],
            "queue_async": False,
        }
    )

    with (
        patch("backend.modules.rag.router.OrchestrationService") as orchestration_service,
        patch(
            "backend.modules.rag.router.bulk_ingest_documents_parallel",
            new=AsyncMock(return_value=rows),
        ) as bulk_ingest,
    ):
        orchestration_service.return_value.get_project = AsyncMock(
            return_value=SimpleNamespace(id="project-1")
        )
        response = await bulk_ingest_documents(
            "project-1",
            payload,
            db=AsyncMock(),
            current_user=SimpleNamespace(id="user-1"),
        )

    assert [item.document_id for item in response] == ["doc-1", "doc-2"]
    assert bulk_ingest.await_args.kwargs["documents"] == [
        {
            "title": "Architecture",
            "content": "System boundaries",
            "source_type": None,
            "metadata": {},
        },
        {
            "title": "Runbook",
            "content": "Recovery steps",
            "source_type": None,
            "metadata": {},
        },
    ]


@pytest.mark.asyncio
async def test_get_document_uses_direct_project_scoped_lookup() -> None:
    row = _document("doc-1", "Direct")
    with (
        patch("backend.modules.rag.router.OrchestrationService") as service_cls,
        patch("backend.modules.rag.router.OrchestrationRepository") as repo_cls,
    ):
        service_cls.return_value.get_project = AsyncMock(
            return_value=SimpleNamespace(id="project-1")
        )
        repo_cls.return_value.get_document = AsyncMock(return_value=row)

        response = await get_rag_document(
            "project-1",
            "doc-1",
            db=MagicMock(),
            current_user=SimpleNamespace(id="user-1"),
        )

    repo_cls.return_value.get_document.assert_awaited_once_with("project-1", "doc-1")
    assert response.document_id == "doc-1"
