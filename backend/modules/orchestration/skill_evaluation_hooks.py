"""Record SkillEvaluation / SkillUsageStat from orchestration run outcomes."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.orchestration.skill_runtime import load_assigned_skill_versions
from backend.modules.workforce.services.evaluation_service import EvaluationService


async def record_skill_usage_for_run(
    db: AsyncSession,
    *,
    agent_id: str | None,
    task_id: str | None,
    run_id: str | None,
    success: bool,
    latency_ms: int | None = None,
    token_usage: int | None = None,
    cost_usd: float | None = None,
    retry_count: int = 0,
    human_accepted: bool | None = None,
    notes: str | None = None,
) -> list[Any]:
    """For each assigned SkillVersion on the agent, record an evaluation row."""
    if not agent_id:
        return []
    try:
        versions = await load_assigned_skill_versions(db, agent_id)
    except Exception:
        return []
    if not versions:
        return []

    service = EvaluationService(db)
    recorded = []
    for item in versions:
        skill_id = item.get("skill_id")
        version_id = item.get("skill_version_id")
        if not skill_id:
            continue
        try:
            evaluation = await service.record_evaluation(
                skill_id=str(skill_id),
                skill_version_id=str(version_id) if version_id else None,
                task_id=task_id,
                run_id=run_id,
                agent_id=agent_id,
                success=success,
                human_accepted=human_accepted,
                latency_ms=latency_ms,
                token_usage=token_usage,
                cost_usd=cost_usd,
                retry_count=retry_count,
                notes=notes,
            )
            recorded.append(evaluation)
        except Exception:
            continue
    return recorded
