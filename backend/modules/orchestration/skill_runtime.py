"""Load AgentSkillAssignment → SkillVersion payloads for runtime."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.workforce.models import AgentSkillAssignment, Skill, SkillVersion


async def load_assigned_skill_versions(
    db: AsyncSession,
    agent_id: str,
) -> list[dict[str, Any]]:
    """Resolve enabled assignments to concrete skill version payloads."""
    result = await db.execute(
        select(AgentSkillAssignment, Skill, SkillVersion)
        .join(Skill, Skill.id == AgentSkillAssignment.skill_id)
        .outerjoin(
            SkillVersion,
            SkillVersion.id
            == AgentSkillAssignment.skill_version_id,  # may be null when latest_active
        )
        .where(
            AgentSkillAssignment.agent_id == agent_id,
            AgentSkillAssignment.enabled.is_(True),
        )
        .order_by(AgentSkillAssignment.priority.asc())
    )
    rows = result.all()
    if not rows:
        return []

    # Batch-load current versions for latest_active policy
    need_current_ids = [
        skill.current_version_id
        for assignment, skill, pinned in rows
        if skill.current_version_id and (assignment.version_policy != "pinned" or pinned is None)
    ]
    current_by_id: dict[str, SkillVersion] = {}
    if need_current_ids:
        versions = await db.execute(
            select(SkillVersion).where(SkillVersion.id.in_(need_current_ids))
        )
        current_by_id = {v.id: v for v in versions.scalars().all()}

    payloads: list[dict[str, Any]] = []
    for assignment, skill, pinned in rows:
        version = pinned
        if (assignment.version_policy != "pinned" or version is None) and skill.current_version_id:
            version = current_by_id.get(skill.current_version_id)
        if version is None:
            continue
        payloads.append(
            {
                "skill_id": skill.id,
                "skill_version_id": version.id,
                "slug": skill.slug,
                "name": skill.name,
                "scope": skill.scope,
                "purpose": version.purpose,
                "when_to_use": version.when_to_use,
                "instructions_markdown": version.instructions_markdown,
                "constraints_markdown": version.constraints_markdown,
                "capabilities": list(version.capabilities_json or []),
                "required_tools": list(version.required_tools_json or []),
                "knowledge_requirements": list(version.knowledge_requirements_json or []),
                "input_schema": dict(version.input_schema_json or {}),
                "output_schema": dict(version.output_schema_json or {}),
                "approval_policy": dict(version.approval_policy_json or {}),
                "evaluation_criteria": list(version.evaluation_criteria_json or []),
                "risk_level": version.risk_level,
                "version_number": version.version_number,
                "version_policy": assignment.version_policy,
            }
        )
    return payloads
