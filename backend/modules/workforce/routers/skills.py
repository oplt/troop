"""Skill management endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_authenticated_user
from backend.db.session import get_db
from backend.modules.identity_access.models import User
from backend.modules.workforce.dto import enrich_skill_response, enrich_skills
from backend.modules.workforce.schemas import (
    SkillDraftResponse,
    SkillImproveRequest,
    SkillPromoteRequest,
    SkillResponse,
    SkillUsageResponse,
    SkillVersionResponse,
)
from backend.modules.workforce.services.evaluation_service import EvaluationService
from backend.modules.workforce.services.skill_service import SkillService

router = APIRouter(prefix="/skills")


@router.get("", response_model=list[SkillResponse])
async def list_skills(
    status: str | None = None,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> list[SkillResponse]:
    """List skills owned by the current user."""
    service = SkillService(db)
    skills = await service.list(user.id, status=status)
    return await enrich_skills(db, skills)


@router.post("/migrate-skill-packs")
async def migrate_skill_packs(
    publish: bool = True,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Migrate legacy SkillPack catalog into SkillDraft/Skill for the current user."""
    from backend.modules.workforce.services.skillpack_deprecation import (
        SkillPackDeprecationService,
    )

    results = await SkillPackDeprecationService(db).migrate_all_for_owner(user.id, publish=publish)
    return {
        "migrated": sum(1 for r in results if r.get("status") == "migrated"),
        "drafts": sum(1 for r in results if r.get("status") == "draft_created"),
        "skipped": sum(1 for r in results if r.get("status") == "skipped"),
        "results": results,
    }


@router.post("/reconcile-uncertain-ownership")
async def reconcile_uncertain_ownership(
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Disable skills whose SkillPack ownership bridge is uncertain."""
    from backend.modules.workforce.services.skill_ownership_reconciliation import (
        disable_skills_needing_reconciliation,
    )

    # Auth gate: any authenticated owner may run; effect is global bridge-linked skills.
    _ = user
    return await disable_skills_needing_reconciliation(db)


@router.get("/{skill_id}", response_model=SkillResponse)
async def get_skill(
    skill_id: str,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> SkillResponse:
    """Get a single skill by ID."""
    service = SkillService(db)
    skill = await service.get(user.id, skill_id)
    return await enrich_skill_response(db, skill)


@router.get("/{skill_id}/versions", response_model=list[SkillVersionResponse])
async def list_skill_versions(
    skill_id: str,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> list[SkillVersionResponse]:
    """List all versions of a skill."""
    service = SkillService(db)
    versions = await service.list_versions(user.id, skill_id)
    return [SkillVersionResponse.model_validate(v) for v in versions]


@router.get("/{skill_id}/usage", response_model=SkillUsageResponse)
async def get_skill_usage(
    skill_id: str,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> SkillUsageResponse:
    """Get usage statistics for a skill."""
    service = SkillService(db)
    await service.get(user.id, skill_id)
    eval_service = EvaluationService(db)
    stats = await eval_service.get_usage_stats(skill_id)

    if not stats:
        return SkillUsageResponse(skill_id=skill_id)

    # Aggregate across all versions
    total_runs = sum(s.run_count for s in stats)
    total_success = sum(s.success_count for s in stats)
    total_accepted = sum(s.human_accept_count for s in stats)
    total_latency = sum(s.total_latency_ms for s in stats)
    total_cost = sum(s.total_cost_usd for s in stats)
    total_retries = sum(s.total_retries for s in stats)
    last_used = max((s.last_used_at for s in stats if s.last_used_at), default=None)

    success_rate = total_success / total_runs if total_runs > 0 else 0.0
    avg_latency = total_latency / total_runs if total_runs > 0 else None
    avg_cost = total_cost / total_runs if total_runs > 0 else None
    retry_rate = total_retries / total_runs if total_runs > 0 else 0.0

    # Get promotion recommendation
    recommendation = await eval_service.recommend_promotion(skill_id, user.id)
    promo = None
    if recommendation.get("eligible"):
        eligible_scopes = recommendation.get("eligible_scopes", [])
        if eligible_scopes:
            promo = f"Ready for {', '.join(eligible_scopes)}"

    return SkillUsageResponse(
        skill_id=skill_id,
        run_count=total_runs,
        success_count=total_success,
        human_accept_count=total_accepted,
        success_rate=success_rate,
        avg_latency_ms=avg_latency,
        avg_cost_usd=avg_cost,
        retry_rate=retry_rate,
        last_used_at=last_used,
        promotion_recommendation=promo,
    )


@router.post("/{skill_id}/promote", response_model=SkillResponse)
async def promote_skill(
    skill_id: str,
    payload: SkillPromoteRequest,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> SkillResponse:
    """Promote a skill to a broader scope."""
    service = SkillService(db)
    skill = await service.promote_scope(user.id, skill_id, payload.target_scope, reason=None)
    return await enrich_skill_response(db, skill)


@router.post("/{skill_id}/improve", response_model=SkillDraftResponse)
async def improve_skill(
    skill_id: str,
    payload: SkillImproveRequest,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> SkillDraftResponse:
    """Create an improvement SkillDraft from the active published SkillVersion."""
    from backend.modules.workforce.dto import skill_draft_response

    service = SkillService(db)
    draft = await service.improve_skill(
        user.id,
        skill_id,
        feedback=payload.feedback,
        evaluation_id=payload.evaluation_id,
        created_by=user.id,
    )
    return skill_draft_response(draft)
