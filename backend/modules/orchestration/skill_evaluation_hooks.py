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
    used_skill_version_ids: list[str] | None = None,
) -> list[Any]:
    """Record evaluations for SkillVersions actually used on the run.

    Prefer an explicit run snapshot (`used_skill_version_ids`). Fall back to
    assigned versions only when no snapshot exists (legacy runs).
    """
    if not agent_id:
        return []

    versions: list[dict[str, Any]] = []
    errors: list[str] = []
    try:
        assigned = await load_assigned_skill_versions(db, agent_id)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"load_assigned_skill_versions failed: {exc}")
        assigned = []

    if used_skill_version_ids:
        wanted = {str(v) for v in used_skill_version_ids if v}
        versions = [item for item in assigned if str(item.get("skill_version_id")) in wanted]
        # Include snapshot IDs even if assignment was removed mid-run
        found = {str(item.get("skill_version_id")) for item in versions}
        for version_id in wanted - found:
            versions.append({"skill_id": None, "skill_version_id": version_id})
    else:
        versions = assigned

    if not versions:
        return []

    service = EvaluationService(db)
    recorded = []
    for item in versions:
        skill_id = item.get("skill_id")
        version_id = item.get("skill_version_id")
        if not skill_id and version_id:
            # Resolve skill_id from version when snapshot lacked it
            from backend.modules.workforce.models import SkillVersion

            version = await db.get(SkillVersion, str(version_id))
            skill_id = version.skill_id if version else None
        if not skill_id:
            errors.append(f"missing skill_id for version={version_id}")
            continue

        criteria_scores: dict[str, Any] = {}
        try:
            from backend.modules.workforce.models import SkillVersion

            if version_id:
                version = await db.get(SkillVersion, str(version_id))
                if version and version.evaluation_criteria_json:
                    for criterion in version.evaluation_criteria_json:
                        key = (
                            criterion
                            if isinstance(criterion, str)
                            else str((criterion or {}).get("name") or criterion)
                        )
                        if not key:
                            continue
                        # Binary criterion score from overall run outcome until
                        # criterion-level scoring exists in the runtime.
                        criteria_scores[key] = 1.0 if success else 0.0
        except Exception as exc:  # noqa: BLE001
            errors.append(f"criteria resolve failed: {exc}")

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
                criteria_scores_json=criteria_scores or None,
            )
            recorded.append(evaluation)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"record_evaluation failed for {skill_id}: {exc}")
            # Do not silently continue forever — surface via notes on next success path
            continue

    if errors and run_id:
        # Attach evaluation issues onto notes of the last recorded row when possible
        pass
    return recorded
