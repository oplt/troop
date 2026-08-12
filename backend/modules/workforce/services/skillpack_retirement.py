"""SkillPack hot-path retirement helpers and legacy read telemetry."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.team.models import AgentProfile, SkillPack


def assert_no_skillpack_writes() -> None:
    """Raise 410 when legacy SkillPack write paths are invoked."""
    raise HTTPException(
        status_code=410,
        detail=(
            "SkillPack writes are retired. Create a SkillDraft via /skill-drafts "
            "and publish a SkillVersion instead."
        ),
    )


async def legacy_skillpack_read_telemetry(db: AsyncSession) -> dict[str, Any]:
    """Count agents still referencing skills_json and remaining skill_packs rows."""
    agents_with_skills = await db.execute(
        select(func.count())
        .select_from(AgentProfile)
        .where(AgentProfile.skills_json.is_not(None))
        .where(func.json_array_length(AgentProfile.skills_json) > 0)
    )
    try:
        agents_count = int(agents_with_skills.scalar_one() or 0)
    except Exception:
        agent_rows = await db.execute(select(AgentProfile.skills_json))
        agents_count = sum(1 for row in agent_rows.all() if row[0] and len(list(row[0] or [])) > 0)

    pack_count = await db.execute(select(func.count()).select_from(SkillPack))
    return {
        "agents_with_non_empty_skills_json": agents_count,
        "skill_packs_rows": int(pack_count.scalar_one() or 0),
    }
