from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, File, Query, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_current_user
from backend.api.deps.rag import get_rag_service
from backend.core.http_cache import apply_private_list_cache_headers, compute_documents_etag
from backend.db.session import get_db
from backend.modules.identity_access.models import User
from backend.modules.orchestration.services.service import OrchestrationService
from backend.modules.rag.bulk_ingest import bulk_ingest_documents_parallel
from backend.modules.rag.observability import log_rag_event
from backend.modules.rag.schemas import RagSearchFilters
from backend.modules.rag.service import RagService

router = APIRouter()


class RagDocumentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)
    task_id: str | None = None
    source_type: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    ttl_days: int | None = None
    queue_async: bool = True


class RagBulkDocumentItem(BaseModel):
    title: str
    content: str
    source_type: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RagBulkIngestRequest(BaseModel):
    documents: list[RagBulkDocumentItem] = Field(min_length=1, max_length=50)
    task_id: str | None = None
    queue_async: bool = True


class RagSearchRequest(BaseModel):
    query: str = Field(min_length=1)
    task_id: str | None = None
    top_k: int = Field(default=5, ge=1, le=20)
    include_decisions: bool = False
    source_kind: str | None = None


class RagAnswerRequest(BaseModel):
    query: str = Field(min_length=1)
    task_id: str | None = None
    top_k: int = Field(default=5, ge=1, le=20)
    include_decisions: bool = False


class RagDocumentResponse(BaseModel):
    document_id: str
    source_id: str
    source_type: str
    title: str
    owner_user_id: str
    project_id: str
    checksum: str
    chunk_count: int
    ingestion_status: str
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class RagChunkMatchResponse(BaseModel):
    chunk_id: str
    document_id: str
    title: str
    content: str
    chunk_index: int
    score: float
    hit_kind: str
    metadata: dict[str, Any]


class RagCitationResponse(BaseModel):
    source_index: int
    chunk_id: str
    document_id: str
    title: str
    chunk_index: int
    score: float
    excerpt: str


class RagAnswerResponse(BaseModel):
    query: str
    answer: str
    grounded: bool
    context_found: bool
    model: str
    provider: str
    citations: list[RagCitationResponse]


def _document_response(item) -> RagDocumentResponse:
    meta = dict(item.metadata_json or {})
    return RagDocumentResponse(
        document_id=item.id,
        source_id=item.id,
        source_type=str(meta.get("source_type") or "text"),
        title=item.filename,
        owner_user_id=item.uploaded_by_user_id,
        project_id=item.project_id,
        checksum=str(meta.get("checksum") or ""),
        chunk_count=item.chunk_count,
        ingestion_status=item.ingestion_status,
        metadata=meta,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _chunk_match(item) -> RagChunkMatchResponse:
    return RagChunkMatchResponse(
        chunk_id=item.chunk_id,
        document_id=item.document_id,
        title=item.title,
        content=item.content,
        chunk_index=item.chunk_index,
        score=item.score,
        hit_kind=item.hit_kind,
        metadata=item.metadata,
    )


def _filters(user: User, project_id: str, **kwargs) -> RagSearchFilters:
    return RagSearchFilters(user_id=user.id, project_id=project_id, **kwargs)


@router.post(
    "/projects/{project_id}/documents",
    response_model=RagDocumentResponse,
    status_code=201,
)
async def create_rag_document(
    project_id: str,
    payload: RagDocumentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    orch = OrchestrationService(db)
    project = await orch.get_project(current_user, project_id)
    rag = RagService(db)
    document = await rag.ingest_text(
        current_user,
        project,
        title=payload.title,
        content=payload.content,
        task_id=payload.task_id,
        source_type=payload.source_type,
        metadata=payload.metadata,
        ttl_days=payload.ttl_days,
        queue_async=payload.queue_async,
    )
    try:
        from backend.workers.orchestration import queue_memory_ingest_jobs

        if payload.queue_async:
            queue_memory_ingest_jobs()
    except Exception as exc:
        log_rag_event(
            "ingest_queue_failed",
            project_id=project_id,
            document_id=document.id,
            error=str(exc),
            level="warning",
        )
    return _document_response(document)
async def bulk_ingest_documents(
    project_id: str,
    payload: RagBulkIngestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await OrchestrationService(db).get_project(current_user, project_id)
    documents = [
        {
            "title": item.title,
            "content": item.content,
            "source_type": item.source_type,
            "metadata": item.metadata,
        }
        for item in payload.documents
    ]
    rows = await bulk_ingest_documents_parallel(
        current_user,
        project_id,
        documents=documents,
        task_id=payload.task_id,
        queue_async=payload.queue_async,
    )
    out = [_document_response(row) for row in rows]
    if payload.queue_async:
        try:
            from backend.workers.orchestration import queue_memory_ingest_jobs

            queue_memory_ingest_jobs()
        except Exception as exc:
            log_rag_event(
                "bulk_ingest_queue_failed",
                project_id=project_id,
                count=len(out),
                error=str(exc),
                level="warning",
            )
    return out


@router.post("/projects/{project_id}/documents/upload", response_model=RagDocumentResponse)
async def upload_rag_document(
    project_id: str,
    file: UploadFile = File(...),
    task_id: str | None = None,
    queue_async: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    orch = OrchestrationService(db)
    project = await orch.get_project(current_user, project_id)
    rag = RagService(db)
    document = await rag.ingest_upload(
        current_user,
        project,
        file,
        task_id=task_id,
        queue_async=queue_async,
    )
    if queue_async:
        try:
            from backend.workers.orchestration import queue_memory_ingest_jobs

            queue_memory_ingest_jobs()
        except Exception as exc:
            log_rag_event(
                "upload_queue_failed",
                project_id=project_id,
                document_id=document.id,
                error=str(exc),
                level="warning",
            )
    return _document_response(document)


@router.get("/projects/{project_id}/documents", response_model=list[RagDocumentResponse])
async def list_rag_documents(
    project_id: str,
    request: Request,
    response: Response,
    task_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = await OrchestrationService(db).list_documents(current_user, project_id, task_id)
    etag = compute_documents_etag(rows)
    apply_private_list_cache_headers(response, etag)
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=dict(response.headers))
    return [_document_response(row) for row in rows]


@router.get("/projects/{project_id}/documents/{document_id}", response_model=RagDocumentResponse)
async def get_rag_document(
    project_id: str,
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = await OrchestrationService(db).list_documents(current_user, project_id)
    row = next((item for item in rows if item.id == document_id), None)
    if row is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Document not found")
    return _document_response(row)


@router.delete("/projects/{project_id}/documents/{document_id}", status_code=204)
async def delete_rag_document(
    project_id: str,
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    rag: RagService = Depends(get_rag_service),
):
    await OrchestrationService(db).get_project(current_user, project_id)
    await rag.delete_document(document_id, project_id=project_id)
    return Response(status_code=204)


@router.post("/projects/{project_id}/search", response_model=list[RagChunkMatchResponse])
async def rag_search(
    project_id: str,
    payload: RagSearchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    rag: RagService = Depends(get_rag_service),
):
    await OrchestrationService(db).get_project(current_user, project_id)
    matches = await rag.retrieve(
        payload.query,
        filters=_filters(
            current_user,
            project_id,
            task_id=payload.task_id,
            include_decisions=payload.include_decisions,
            source_kind=payload.source_kind,
        ),
        limit=payload.top_k,
    )
    return [_chunk_match(item) for item in matches]


@router.post("/projects/{project_id}/answer", response_model=RagAnswerResponse)
async def rag_answer(
    project_id: str,
    payload: RagAnswerRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    rag: RagService = Depends(get_rag_service),
):
    await OrchestrationService(db).get_project(current_user, project_id)
    result = await rag.answer(
        payload.query,
        filters=_filters(
            current_user,
            project_id,
            task_id=payload.task_id,
            include_decisions=payload.include_decisions,
        ),
        limit=payload.top_k,
    )
    return RagAnswerResponse(
        query=result.query,
        answer=result.answer,
        grounded=result.grounded,
        context_found=result.context_found,
        model=result.model,
        provider=result.provider,
        citations=[
            RagCitationResponse(
                source_index=c.source_index,
                chunk_id=c.chunk_id,
                document_id=c.document_id,
                title=c.title,
                chunk_index=c.chunk_index,
                score=c.score,
                excerpt=c.excerpt,
            )
            for c in result.citations
        ],
    )


@router.post("/projects/{project_id}/answer/stream")
async def rag_answer_stream(
    project_id: str,
    payload: RagAnswerRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await OrchestrationService(db).get_project(current_user, project_id)
    rag = RagService(db)
    filters = _filters(
        current_user,
        project_id,
        task_id=payload.task_id,
        include_decisions=payload.include_decisions,
    )

    async def event_stream():
        async for event in rag.answer_stream(
            payload.query,
            filters=filters,
            limit=payload.top_k,
        ):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/projects/{project_id}/documents/{document_id}/reindex")
async def reindex_rag_document(
    project_id: str,
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await OrchestrationService(db).get_project(current_user, project_id)
    count = await RagService(db).reindex_document(document_id, project_id=project_id)
    return {"document_id": document_id, "chunk_count": count, "status": "completed"}
