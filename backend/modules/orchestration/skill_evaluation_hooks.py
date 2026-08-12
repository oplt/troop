"""Record SkillEvaluation / SkillUsageStat from orchestration run outcomes."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.orchestration.models import RunEvent, TaskRun
from backend.modules.orchestration.skill_runtime import load_assigned_skill_versions
from backend.modules.workforce.services.evaluation_service import EvaluationService


def _criteria_scores_unmeasured(criteria: list[Any]) -> dict[str, Any]:
    """Do not invent criterion scores from overall run success."""
    scores: dict[str, Any] = {}
    for criterion in criteria or []:
        if isinstance(criterion, str):
            key = criterion
        elif isinstance(criterion, dict):
            key = str(criterion.get("name") or criterion.get("id") or "")
        else:
            key = str(criterion or "")
        if not key:
            continue
        scores[key] = {
            "status": "unmeasured",
            "score": None,
            "evaluator": None,
            "evidence": [],
        }
    return scores


async def _emit_eval_event(
    db: AsyncSession,
    *,
    run: TaskRun | None,
    run_id: str | None,
    task_id: str | None,
    message: str,
    payload: dict[str, Any] | None = None,
) -> None:
    if not run_id and run is None:
        return
    rid = run_id or (run.id if run else None)
    if not rid:
        return
    event = RunEvent(
        run_id=rid,
        task_id=task_id or (run.task_id if run else None),
        level="warning",
        event_type="skill_evaluation_error",
        message=message,
        payload_json=payload or {},
    )
    db.add(event)
    await db.flush()


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
    run: TaskRun | None = None,
) -> list[Any]:
    """Record evaluations for SkillVersions used on the run (frozen snapshot preferred)."""
    if not agent_id:
        return []

    errors: list[str] = []
    versions: list[dict[str, Any]] = []

    # Prefer frozen snapshot skills on the run
    if run is not None:
        snapshot = (run.checkpoint_json or {}).get("skill_version_snapshot") or {}
        frozen = snapshot.get("skills") or []
        if frozen:
            versions = [
                {
                    "skill_id": item.get("skill_id"),
                    "skill_version_id": item.get("skill_version_id"),
                    "evaluation_criteria": item.get("evaluation_criteria") or [],
                }
                for item in frozen
                if isinstance(item, dict)
            ]

    if not versions:
        try:
            assigned = await load_assigned_skill_versions(db, agent_id)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"load_assigned_skill_versions failed: {exc}")
            assigned = []
        if used_skill_version_ids:
            wanted = {str(v) for v in used_skill_version_ids if v}
            versions = [item for item in assigned if str(item.get("skill_version_id")) in wanted]
        else:
            versions = assigned

    if not versions:
        if errors:
            await _emit_eval_event(
                db,
                run=run,
                run_id=run_id,
                task_id=task_id,
                message="; ".join(errors),
                payload={"errors": errors},
            )
            await db.commit()
        return []

    service = EvaluationService(db)
    recorded = []
    for item in versions:
        skill_id = item.get("skill_id")
        version_id = item.get("skill_version_id")
        if not skill_id and version_id:
            from backend.modules.workforce.models import SkillVersion

            version = await db.get(SkillVersion, str(version_id))
            skill_id = version.skill_id if version else None
            if version and not item.get("evaluation_criteria"):
                item["evaluation_criteria"] = list(version.evaluation_criteria_json or [])
        if not skill_id:
            errors.append(f"missing skill_id for version={version_id}")
            continue

        criteria_scores = _criteria_scores_unmeasured(item.get("evaluation_criteria") or [])
        # Overall success is recorded separately; criterion scores stay unmeasured
        # unless a dedicated evaluator supplied evidence.
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

    if errors:
        await _emit_eval_event(
            db,
            run=run,
            run_id=run_id,
            task_id=task_id,
            message="; ".join(errors[:5]),
            payload={"errors": errors, "recorded": len(recorded)},
        )
    await db.commit()
    return recorded
