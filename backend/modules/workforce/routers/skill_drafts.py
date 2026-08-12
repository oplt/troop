"""Skill draft management endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_authenticated_user
from backend.db.session import get_db
from backend.modules.identity_access.models import User
from backend.modules.workforce.dto import enrich_skill_response, skill_draft_response
from backend.modules.workforce.schemas import (
    SkillDraftCreate,
    SkillDraftResponse,
    SkillDraftUpdate,
    SkillResponse,
)
from backend.modules.workforce.services.skill_service import SkillService

router = APIRouter(prefix="/skill-drafts")


@router.get("", response_model=list[SkillDraftResponse])
async def list_skill_drafts(
    status: str | None = None,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> list[SkillDraftResponse]:
    """List skill drafts owned by the current user."""
    service = SkillService(db)
    drafts = await service.list_drafts(user.id, status=status)
    return [skill_draft_response(d) for d in drafts]


@router.post("", response_model=SkillDraftResponse, status_code=201)
async def create_skill_draft(
    payload: SkillDraftCreate,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> SkillDraftResponse:
    """Create a new skill draft."""
    from backend.modules.workforce.authz import (
        assert_company_owned,
        assert_project_owned,
        assert_task_owned,
    )

    await assert_company_owned(db, user.id, payload.company_id)
    await assert_project_owned(db, user.id, payload.source_project_id)
    await assert_task_owned(db, user.id, payload.source_task_id)

    service = SkillService(db)
    draft = await service.create_draft(
        owner_id=user.id,
        company_id=payload.company_id,
        name=payload.name,
        slug=payload.slug,
        description=payload.description,
        purpose=payload.purpose,
        when_to_use=payload.when_to_use,
        instructions_markdown=payload.instructions_markdown,
        scope=payload.scope,
        risk_level=payload.risk_level,
        source_type=payload.source_type,
        source_task_id=payload.source_task_id,
        source_project_id=payload.source_project_id,
        skill_id=payload.skill_id,
        capabilities_json=payload.capabilities,
        required_tools_json=payload.required_tools,
        knowledge_requirements_json=payload.knowledge_requirements,
        input_schema_json=payload.input_schema,
        output_schema_json=payload.output_schema,
        constraints_markdown=payload.constraints_markdown,
        approval_policy_json=payload.approval_policy,
        examples_json=payload.examples,
        evaluation_criteria_json=payload.evaluation_criteria,
        confidence=payload.confidence,
        generation_metadata_json=payload.generation_metadata,
        unmatched_sections_json=payload.unmatched_sections,
        warnings_json=payload.warnings,
    )
    return skill_draft_response(draft)


@router.post("/import-markdown", response_model=SkillDraftResponse, status_code=201)
async def import_skill_markdown(
    payload: dict,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> SkillDraftResponse:
    """Create a SkillDraft from markdown (canonical import path; not SkillPack)."""
    from backend.modules.workforce.authz import assert_company_owned
    from backend.modules.workforce.services.markdown_skill_import import (
        MarkdownSkillImportService,
    )

    content = str(payload.get("content") or payload.get("markdown") or "")
    if not content.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="content required")
    company_id = payload.get("company_id")
    await assert_company_owned(db, user.id, company_id)
    draft = await MarkdownSkillImportService(db).import_markdown(
        user.id,
        content,
        file_name=payload.get("file_name") or payload.get("filename"),
        company_id=company_id,
        scope=str(payload.get("scope") or "organization"),
    )
    return skill_draft_response(draft)


@router.get("/{draft_id}", response_model=SkillDraftResponse)
async def get_skill_draft(
    draft_id: str,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> SkillDraftResponse:
    """Get a single skill draft by ID."""
    service = SkillService(db)
    draft = await service.get_draft(user.id, draft_id)
    return skill_draft_response(draft)


@router.patch("/{draft_id}", response_model=SkillDraftResponse)
async def update_skill_draft(
    draft_id: str,
    payload: SkillDraftUpdate,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> SkillDraftResponse:
    """Update a skill draft."""
    service = SkillService(db)
    kwargs = {}
    if payload.name is not None:
        kwargs["name"] = payload.name
    if payload.slug is not None:
        kwargs["slug"] = payload.slug
    if payload.description is not None:
        kwargs["description"] = payload.description
    if payload.purpose is not None:
        kwargs["purpose"] = payload.purpose
    if payload.when_to_use is not None:
        kwargs["when_to_use"] = payload.when_to_use
    if payload.instructions_markdown is not None:
        kwargs["instructions_markdown"] = payload.instructions_markdown
    if payload.scope is not None:
        kwargs["scope"] = payload.scope
    if payload.risk_level is not None:
        kwargs["risk_level"] = payload.risk_level
    if payload.status is not None:
        kwargs["status"] = payload.status
    if payload.capabilities is not None:
        kwargs["capabilities_json"] = payload.capabilities
    if payload.required_tools is not None:
        kwargs["required_tools_json"] = payload.required_tools
    if payload.knowledge_requirements is not None:
        kwargs["knowledge_requirements_json"] = payload.knowledge_requirements
    if payload.input_schema is not None:
        kwargs["input_schema_json"] = payload.input_schema
    if payload.output_schema is not None:
        kwargs["output_schema_json"] = payload.output_schema
    if payload.constraints_markdown is not None:
        kwargs["constraints_markdown"] = payload.constraints_markdown
    if payload.approval_policy is not None:
        kwargs["approval_policy_json"] = payload.approval_policy
    if payload.examples is not None:
        kwargs["examples_json"] = payload.examples
    if payload.evaluation_criteria is not None:
        kwargs["evaluation_criteria_json"] = payload.evaluation_criteria

    draft = await service.update_draft(user.id, draft_id, **kwargs)
    return skill_draft_response(draft)


@router.post("/{draft_id}/validate", response_model=SkillDraftResponse)
async def validate_skill_draft(
    draft_id: str,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> SkillDraftResponse:
    """Validate a skill draft and persist errors/warnings/duplicates."""
    from backend.modules.workforce.services.skill_validation import SkillValidationService

    service = SkillService(db)
    draft = await service.get_draft(user.id, draft_id)
    result = await SkillValidationService(db).validate_draft(user.id, draft)
    return skill_draft_response(result["draft"])


@router.post("/{draft_id}/publish", response_model=SkillResponse)
async def publish_skill_draft(
    draft_id: str,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> SkillResponse:
    """Publish a skill draft as an active skill (fails on validation errors)."""
    service = SkillService(db)
    skill = await service.publish_draft(user.id, draft_id, created_by=user.id)
    return await enrich_skill_response(db, skill)
