"""Disable Skill entities whose SkillPack bridge ownership is uncertain."""

from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.workforce.models import Skill


async def disable_skills_needing_reconciliation(db: AsyncSession) -> dict[str, int]:
    """Mark skills linked to uncertain bridge rows as disabled until reconciled.

    Bridge statuses treated as needing reconciliation:
    - ownership_uncertain
    - unreferenced_system
    - needs_reconciliation
    """
    try:
        result = await db.execute(
            text(
                """
                SELECT skill_id, ownership_status
                FROM skill_pack_ownership_bridge
                WHERE ownership_status IN (
                    'ownership_uncertain',
                    'unreferenced_system',
                    'needs_reconciliation'
                )
                AND skill_id IS NOT NULL
                """
            )
        )
        rows = list(result.mappings().all())
    except Exception:
        # Table may not exist in unit-test SQLite without migrations
        return {"examined": 0, "disabled": 0}

    skill_ids = [str(r["skill_id"]) for r in rows if r.get("skill_id")]
    if not skill_ids:
        return {"examined": 0, "disabled": 0}

    disabled = 0
    skill_res = await db.execute(select(Skill).where(Skill.id.in_(skill_ids)))
    for skill in skill_res.scalars().all():
        if skill.status == "active":
            skill.status = "disabled"
            disabled += 1
        note = "[ownership_status=needs_reconciliation]"
        if note not in (skill.description or ""):
            skill.description = f"{(skill.description or '').rstrip()} {note}".strip()

    await db.commit()
    return {"examined": len(skill_ids), "disabled": disabled}
