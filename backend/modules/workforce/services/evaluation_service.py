"""Skill evaluation and usage tracking service."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.workforce.models import SkillEvaluation, SkillUsageStat
from backend.modules.workforce.repository import WorkforceRepository


class EvaluationService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = WorkforceRepository(db)

    async def record_evaluation(
        self,
        skill_id: str,
        skill_version_id: str | None = None,
        task_id: str | None = None,
        run_id: str | None = None,
        agent_id: str | None = None,
        success: bool = False,
        human_accepted: bool | None = None,
        score: float | None = None,
        latency_ms: int | None = None,
        token_usage: int | None = None,
        cost_usd: float | None = None,
        retry_count: int = 0,
        criteria_scores_json: dict | None = None,
        notes: str | None = None,
    ) -> SkillEvaluation:
        """Record a skill evaluation and update usage stats."""
        evaluation = await self.repo.create_skill_evaluation(
            skill_id=skill_id,
            skill_version_id=skill_version_id,
            task_id=task_id,
            run_id=run_id,
            agent_id=agent_id,
            success=success,
            human_accepted=human_accepted,
            score=score,
            latency_ms=latency_ms,
            token_usage=token_usage,
            cost_usd=cost_usd,
            retry_count=retry_count,
            criteria_scores_json=criteria_scores_json or {},
            notes=notes,
        )

        stat = await self.repo.get_skill_usage_stat(skill_id, skill_version_id)
        if stat is None:
            stat = await self.repo.create_skill_usage_stat(
                skill_id=skill_id,
                skill_version_id=skill_version_id,
                run_count=0,
                success_count=0,
                human_accept_count=0,
                total_latency_ms=0,
                total_cost_usd=0.0,
                total_retries=0,
            )

        stat.run_count += 1
        if success:
            stat.success_count += 1
        if human_accepted:
            stat.human_accept_count += 1
        if latency_ms:
            stat.total_latency_ms += latency_ms
        if cost_usd:
            stat.total_cost_usd += cost_usd
        stat.total_retries += retry_count
        stat.last_used_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(evaluation)
        return evaluation

    async def get_usage_stats(self, skill_id: str) -> list[SkillUsageStat]:
        """Get usage stats for a skill (all versions)."""
        from sqlalchemy import select
        from backend.modules.workforce.models import SkillUsageStat

        res = await self.db.execute(
            select(SkillUsageStat).where(SkillUsageStat.skill_id == skill_id)
        )
        return list(res.scalars().all())

    async def recommend_promotion(self, skill_id: str, owner_id: str) -> dict:
        """
        Recommend skill promotion based on success thresholds.

        Returns recommendation dict with eligible scopes.
        """
        skill = await self.repo.get_skill(skill_id, owner_id)
        if skill is None:
            return {"eligible": False, "reason": "skill not found"}

        stats = await self.get_usage_stats(skill_id)
        if not stats:
            return {"eligible": False, "reason": "no usage data"}

        total_runs = sum(s.run_count for s in stats)
        total_success = sum(s.success_count for s in stats)
        total_accepted = sum(s.human_accept_count for s in stats)

        success_rate = total_success / total_runs if total_runs > 0 else 0
        accept_rate = total_accepted / total_runs if total_runs > 0 else 0

        eligible_scopes = []
        if skill.scope == "task":
            if total_runs >= 5 and success_rate >= 0.8:
                eligible_scopes.append("project")
            if total_runs >= 20 and success_rate >= 0.9 and accept_rate >= 0.8:
                eligible_scopes.append("organization")
        elif skill.scope == "project":
            if total_runs >= 20 and success_rate >= 0.9 and accept_rate >= 0.8:
                eligible_scopes.append("organization")

        if not eligible_scopes:
            return {
                "eligible": False,
                "reason": f"needs more usage (runs={total_runs}, success={success_rate:.0%}, accepted={accept_rate:.0%})",
            }

        return {
            "eligible": True,
            "current_scope": skill.scope,
            "eligible_scopes": eligible_scopes,
            "stats": {
                "total_runs": total_runs,
                "success_rate": success_rate,
                "accept_rate": accept_rate,
            },
        }
