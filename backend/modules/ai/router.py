from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_current_user
from backend.core.config import settings
from backend.core.pagination import build_cursor_page, fetch_limit, token_from_created_at_id
from backend.core.schemas import CursorPageResponse
from backend.db.session import get_db
from backend.modules.ai.schemas import (
    AiChunkMatchResponse,
    AiDocumentCreate,
    AiDocumentIngestResponse,
    AiDocumentResponse,
    AiEvaluationCaseCreate,
    AiEvaluationCaseFromTraceCreate,
    AiEvaluationCaseResponse,
    AiEvaluationDatasetCreate,
    AiEvaluationDatasetResponse,
    AiEvaluationDatasetUpdate,
    AiEvaluationRunRequest,
    AiEvaluationRunResponse,
    AiEvaluationScorecardResponse,
    AiFeedbackCreate,
    AiFeedbackResponse,
    AiModuleOverviewResponse,
    AiPromptTemplateCreate,
    AiPromptTemplateResponse,
    AiPromptTemplateUpdate,
    AiPromptVersionCreate,
    AiPromptVersionResponse,
    AiPromptVersionUpdate,
    AiProviderDescriptor,
    AiRetrieveRequest,
    AiReviewCreate,
    AiReviewDecision,
    AiReviewItemResponse,
    AiRunRequest,
    AiRunResponse,
)
from backend.modules.ai.service import AiService
from backend.modules.identity_access.models import User

router = APIRouter()


def _prompt_template_to_response(template) -> AiPromptTemplateResponse:
    return AiPromptTemplateResponse.model_validate(template)


def _prompt_version_to_response(version) -> AiPromptVersionResponse:
    return AiPromptVersionResponse(
        id=version.id,
        prompt_template_id=version.prompt_template_id,
        version_number=version.version_number,
        provider_key=version.provider_key,
        model_name=version.model_name,
        system_prompt=version.system_prompt,
        user_prompt_template=version.user_prompt_template,
        variable_definitions=version.variable_definitions_json,
        response_format=version.response_format,
        temperature=version.temperature,
        rollout_percentage=version.rollout_percentage,
        is_published=version.is_published,
        input_cost_per_million=version.input_cost_per_million,
        output_cost_per_million=version.output_cost_per_million,
        created_by_user_id=version.created_by_user_id,
        created_at=version.created_at,
    )


def _document_to_response(document) -> AiDocumentResponse:
    return AiDocumentResponse(
        id=document.id,
        title=document.title,
        description=document.description,
        filename=document.filename,
        content_type=document.content_type,
        size_bytes=document.size_bytes,
        ingestion_status=document.ingestion_status,
        metadata=document.metadata_json,
        chunk_count=document.chunk_count,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


def _run_to_response(run) -> AiRunResponse:
    return AiRunResponse(
        id=run.id,
        prompt_template_id=run.prompt_template_id,
        prompt_version_id=run.prompt_version_id,
        provider_key=run.provider_key,
        model_name=run.model_name,
        status=run.status,
        response_format=run.response_format,
        variables=run.variables_json,
        retrieval_query=run.retrieval_query,
        retrieved_chunk_ids=run.retrieved_chunk_ids_json,
        input_messages=run.input_messages_json,
        output_text=run.output_text,
        output_json=run.output_json,
        latency_ms=run.latency_ms,
        input_tokens=run.input_tokens,
        output_tokens=run.output_tokens,
        total_tokens=run.total_tokens,
        estimated_cost_micros=run.estimated_cost_micros,
        error_message=run.error_message,
        review_status=run.review_status,
        created_at=run.created_at,
        completed_at=run.completed_at,
    )


def _review_to_response(review) -> AiReviewItemResponse:
    return AiReviewItemResponse.model_validate(review)


def _feedback_to_response(feedback) -> AiFeedbackResponse:
    return AiFeedbackResponse.model_validate(feedback)


def _dataset_to_response(dataset) -> AiEvaluationDatasetResponse:
    return AiEvaluationDatasetResponse.model_validate(dataset)


def _dataset_case_to_response(case) -> AiEvaluationCaseResponse:
    return AiEvaluationCaseResponse(
        id=case.id,
        dataset_id=case.dataset_id,
        input_variables=case.input_variables_json,
        expected_output_text=case.expected_output_text,
        expected_output_json=case.expected_output_json,
        expected_assertions=case.expected_assertions_json,
        notes=case.notes,
        source_run_id=case.source_run_id,
        source_trace_span_id=case.source_trace_span_id,
        provenance=case.provenance_json or {},
        input_snapshot=case.input_snapshot_json or {},
        correction=case.correction_json,
        created_at=case.created_at,
    )


async def _evaluation_run_to_response(service: AiService, run) -> AiEvaluationRunResponse:
    items = await service.repo.list_evaluation_run_items(run.id)
    return AiEvaluationRunResponse(
        id=run.id,
        dataset_id=run.dataset_id,
        prompt_version_id=run.prompt_version_id,
        status=run.status,
        total_cases=run.total_cases,
        passed_cases=run.passed_cases,
        average_score=run.average_score,
        baseline_run_id=run.baseline_run_id,
        candidate_config=run.candidate_config_json or {},
        metrics=run.metrics_json or {},
        scorecard=run.scorecard_json or {},
        judge_version_id=run.judge_version_id,
        created_at=run.created_at,
        completed_at=run.completed_at,
        items=[
            {
                "evaluation_case_id": item.evaluation_case_id,
                "ai_run_id": item.ai_run_id,
                "score": item.score,
                "passed": item.passed,
                "notes": item.notes,
                "metrics": item.metrics_json or {},
            }
            for item in items
        ],
    )


@router.get("/overview", response_model=AiModuleOverviewResponse)
async def get_overview(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = AiService(db)
    overview = await service.get_overview(current_user)
    return AiModuleOverviewResponse(
        providers=overview["providers"],
        recent_runs=[_run_to_response(item) for item in overview["recent_runs"]],
        prompt_template_count=overview["prompt_template_count"],
        document_count=overview["document_count"],
        pending_review_count=overview["pending_review_count"],
        dataset_count=overview["dataset_count"],
    )


@router.get("/providers", response_model=list[AiProviderDescriptor])
async def list_providers():
    return AiService.list_provider_descriptors()


@router.get("/prompts", response_model=list[AiPromptTemplateResponse])
async def list_prompt_templates(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = AiService(db)
    templates = await service.list_prompt_templates(current_user)
    return [_prompt_template_to_response(item) for item in templates]


@router.post("/prompts", response_model=AiPromptTemplateResponse, status_code=201)
async def create_prompt_template(
    payload: AiPromptTemplateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = AiService(db)
    template = await service.create_prompt_template(
        current_user, payload.key, payload.name, payload.description
    )
    return _prompt_template_to_response(template)


@router.patch("/prompts/{template_id}", response_model=AiPromptTemplateResponse)
async def update_prompt_template(
    template_id: str,
    payload: AiPromptTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = AiService(db)
    template = await service.update_prompt_template(
        current_user,
        template_id,
        payload.model_dump(exclude_unset=True),
    )
    return _prompt_template_to_response(template)


@router.get("/prompts/{template_id}/versions", response_model=list[AiPromptVersionResponse])
async def list_prompt_versions(
    template_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = AiService(db)
    versions = await service.list_prompt_versions(current_user, template_id)
    return [_prompt_version_to_response(item) for item in versions]


@router.post(
    "/prompts/{template_id}/versions",
    response_model=AiPromptVersionResponse,
    status_code=201,
)
async def create_prompt_version(
    template_id: str,
    payload: AiPromptVersionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = AiService(db)
    version = await service.create_prompt_version(current_user, template_id, payload.model_dump())
    return _prompt_version_to_response(version)


@router.patch(
    "/prompts/{template_id}/versions/{version_id}",
    response_model=AiPromptVersionResponse,
)
async def update_prompt_version(
    template_id: str,
    version_id: str,
    payload: AiPromptVersionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = AiService(db)
    version = await service.update_prompt_version(
        current_user,
        template_id,
        version_id,
        payload.model_dump(exclude_unset=True),
    )
    return _prompt_version_to_response(version)


def _document_ingest_response(
    document, *, ingest_job_id: str | None = None
) -> AiDocumentIngestResponse:
    return AiDocumentIngestResponse(
        document=_document_to_response(document),
        ingest_job_id=ingest_job_id,
        queued=bool(ingest_job_id),
    )


@router.get("/documents", response_model=CursorPageResponse[AiDocumentResponse])
async def list_documents(
    limit: int = Query(settings.CURSOR_PAGE_DEFAULT_LIMIT, ge=1, le=settings.CURSOR_PAGE_MAX_LIMIT),
    cursor_created_at: datetime | None = Query(default=None),
    cursor_id: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = AiService(db)
    rows = await service.list_documents(
        current_user,
        limit=fetch_limit(limit),
        cursor_created_at=cursor_created_at,
        cursor_id=cursor_id,
    )
    page, next_cursor = build_cursor_page(rows, limit, token_from_row=token_from_created_at_id)
    return CursorPageResponse(
        items=[_document_to_response(item) for item in page],
        next_cursor=next_cursor,
    )


@router.get("/documents/{document_id}", response_model=AiDocumentResponse)
async def get_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = AiService(db)
    return _document_to_response(await service.get_document(current_user, document_id))


@router.post("/documents", response_model=AiDocumentIngestResponse)
async def create_document(
    payload: AiDocumentCreate,
    queue_async: bool | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = AiService(db)
    document, ingest_job_id = await service.create_document_from_text(
        current_user,
        title=payload.title,
        description=payload.description,
        content=payload.content,
        content_type=payload.content_type,
        metadata=payload.metadata,
        queue_async=queue_async,
    )
    body = _document_ingest_response(document, ingest_job_id=ingest_job_id)
    if ingest_job_id:
        return JSONResponse(status_code=202, content=body.model_dump(mode="json"))
    return body


@router.post("/documents/upload", response_model=AiDocumentIngestResponse)
async def upload_document(
    file: UploadFile = File(...),
    description: str | None = Form(default=None),
    queue_async: bool | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = AiService(db)
    document, ingest_job_id = await service.create_document_from_upload(
        current_user,
        file,
        description,
        queue_async=queue_async,
    )
    body = _document_ingest_response(document, ingest_job_id=ingest_job_id)
    if ingest_job_id:
        return JSONResponse(status_code=202, content=body.model_dump(mode="json"))
    return body


@router.post("/retrieve", response_model=list[AiChunkMatchResponse])
async def retrieve_chunks(
    payload: AiRetrieveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = AiService(db)
    matches = await service.retrieve_chunks(
        current_user,
        query=payload.query,
        document_ids=payload.document_ids,
        top_k=payload.top_k,
    )
    return [AiChunkMatchResponse(**item) for item in matches]


@router.get("/runs", response_model=CursorPageResponse[AiRunResponse])
async def list_runs(
    limit: int = Query(settings.CURSOR_PAGE_DEFAULT_LIMIT, ge=1, le=settings.CURSOR_PAGE_MAX_LIMIT),
    cursor_created_at: datetime | None = Query(default=None),
    cursor_id: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = AiService(db)
    rows = await service.list_runs(
        current_user,
        limit=fetch_limit(limit),
        cursor_created_at=cursor_created_at,
        cursor_id=cursor_id,
    )
    page, next_cursor = build_cursor_page(rows, limit, token_from_row=token_from_created_at_id)
    return CursorPageResponse(
        items=[_run_to_response(item) for item in page],
        next_cursor=next_cursor,
    )


@router.get("/runs/{run_id}", response_model=AiRunResponse)
async def get_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = AiService(db)
    return _run_to_response(await service.get_run(current_user, run_id))


@router.post("/runs", response_model=AiRunResponse, status_code=201)
async def create_run(
    payload: AiRunRequest,
    queue_async: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = AiService(db)
    run = await service.run_prompt(
        current_user,
        prompt_template_key=payload.prompt_template_key,
        prompt_version_id=payload.prompt_version_id,
        variables=payload.variables,
        retrieval_query=payload.retrieval_query,
        document_ids=payload.document_ids,
        top_k=payload.top_k,
        review_required=payload.review_required,
        queue_async=queue_async,
    )
    body = _run_to_response(run)
    if queue_async:
        return JSONResponse(status_code=202, content=body.model_dump(mode="json"))
    return body


@router.get("/reviews", response_model=list[AiReviewItemResponse])
async def list_reviews(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = AiService(db)
    return [_review_to_response(item) for item in await service.list_reviews(current_user)]


@router.post("/runs/{run_id}/reviews", response_model=AiReviewItemResponse, status_code=201)
async def create_review(
    run_id: str,
    payload: AiReviewCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = AiService(db)
    review = await service.create_review(current_user, run_id, payload.assigned_to_user_id)
    return _review_to_response(review)


@router.post("/reviews/{review_id}/decision", response_model=AiReviewItemResponse)
async def decide_review(
    review_id: str,
    payload: AiReviewDecision,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = AiService(db)
    review = await service.decide_review(current_user, review_id, payload.model_dump())
    return _review_to_response(review)


@router.get("/runs/{run_id}/feedback", response_model=list[AiFeedbackResponse])
async def list_feedback(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = AiService(db)
    feedback_items = await service.list_feedback(current_user, run_id)
    return [_feedback_to_response(item) for item in feedback_items]


@router.post("/runs/{run_id}/feedback", response_model=AiFeedbackResponse, status_code=201)
async def create_feedback(
    run_id: str,
    payload: AiFeedbackCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = AiService(db)
    feedback = await service.add_feedback(
        current_user,
        run_id,
        payload.rating,
        payload.comment,
        payload.corrected_output,
    )
    return _feedback_to_response(feedback)


@router.get("/evaluation-datasets", response_model=list[AiEvaluationDatasetResponse])
async def list_datasets(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = AiService(db)
    return [_dataset_to_response(item) for item in await service.list_datasets(current_user)]


@router.post("/evaluation-datasets", response_model=AiEvaluationDatasetResponse, status_code=201)
async def create_dataset(
    payload: AiEvaluationDatasetCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = AiService(db)
    dataset = await service.create_dataset(current_user, payload.name, payload.description)
    return _dataset_to_response(dataset)


@router.patch("/evaluation-datasets/{dataset_id}", response_model=AiEvaluationDatasetResponse)
async def update_dataset(
    dataset_id: str,
    payload: AiEvaluationDatasetUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = AiService(db)
    dataset = await service.update_dataset(
        current_user, dataset_id, payload.model_dump(exclude_unset=True)
    )
    return _dataset_to_response(dataset)


@router.get(
    "/evaluation-datasets/{dataset_id}/cases",
    response_model=list[AiEvaluationCaseResponse],
)
async def list_dataset_cases(
    dataset_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = AiService(db)
    cases = await service.list_dataset_cases(current_user, dataset_id)
    return [_dataset_case_to_response(item) for item in cases]


@router.post(
    "/evaluation-datasets/{dataset_id}/cases",
    response_model=AiEvaluationCaseResponse,
    status_code=201,
)
async def create_dataset_case(
    dataset_id: str,
    payload: AiEvaluationCaseCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = AiService(db)
    case = await service.create_dataset_case(current_user, dataset_id, payload.model_dump())
    return _dataset_case_to_response(case)


@router.post(
    "/evaluation-datasets/{dataset_id}/cases/from-trace",
    response_model=AiEvaluationCaseResponse,
    status_code=201,
)
async def create_dataset_case_from_trace(
    dataset_id: str,
    payload: AiEvaluationCaseFromTraceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = AiService(db)
    case = await service.create_case_from_trace(
        current_user,
        dataset_id,
        payload.model_dump(),
    )
    return _dataset_case_to_response(case)


@router.get("/evaluation-runs", response_model=CursorPageResponse[AiEvaluationRunResponse])
async def list_evaluation_runs(
    limit: int = Query(settings.CURSOR_PAGE_DEFAULT_LIMIT, ge=1, le=settings.CURSOR_PAGE_MAX_LIMIT),
    cursor_created_at: datetime | None = Query(default=None),
    cursor_id: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = AiService(db)
    rows = await service.list_evaluation_runs(
        current_user,
        limit=fetch_limit(limit),
        cursor_created_at=cursor_created_at,
        cursor_id=cursor_id,
    )
    page, next_cursor = build_cursor_page(rows, limit, token_from_row=token_from_created_at_id)
    return CursorPageResponse(
        items=[await _evaluation_run_to_response(service, run) for run in page],
        next_cursor=next_cursor,
    )


@router.get("/evaluation-runs/{evaluation_run_id}", response_model=AiEvaluationRunResponse)
async def get_evaluation_run(
    evaluation_run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = AiService(db)
    run = await service.get_evaluation_run(current_user, evaluation_run_id)
    return await _evaluation_run_to_response(service, run)


@router.get(
    "/evaluation-runs/{evaluation_run_id}/scorecard",
    response_model=AiEvaluationScorecardResponse,
)
async def get_evaluation_scorecard(
    evaluation_run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = AiService(db)
    scorecard = await service.get_evaluation_scorecard(current_user, evaluation_run_id)
    return AiEvaluationScorecardResponse.model_validate(scorecard)


@router.post(
    "/evaluation-datasets/{dataset_id}/run",
    response_model=AiEvaluationRunResponse,
    status_code=201,
)
async def run_evaluation(
    dataset_id: str,
    payload: AiEvaluationRunRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = AiService(db)
    evaluation_run = await service.run_evaluation(current_user, dataset_id, payload.model_dump())
    return await _evaluation_run_to_response(service, evaluation_run)
