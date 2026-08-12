"""Canonical workforce DTO builders — keep FE/BE contracts honest."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.workforce.models import Skill, SkillDraft, SkillVersion
from backend.modules.workforce.schemas import (
    SkillDraftResponse,
    SkillResponse,
    SkillVersionResponse,
)


def _constraints_list(markdown: str | None) -> list[str]:
    return [line for line in (markdown or "").splitlines() if line.strip()]


def _skill_payload(skill: Skill, version: SkillVersion | None) -> dict[str, Any]:
    nested = SkillVersionResponse.model_validate(version) if version else None
    return {
        "id": skill.id,
        "owner_id": skill.owner_id,
        "company_id": skill.company_id,
        "slug": skill.slug,
        "name": skill.name,
        "description": skill.description,
        "scope": skill.scope,
        "status": skill.status,
        "current_version_id": skill.current_version_id,
        "project_id": skill.project_id,
        "task_id": skill.task_id,
        "legacy_skill_pack_id": skill.legacy_skill_pack_id,
        "created_at": skill.created_at,
        "updated_at": skill.updated_at,
        "current_version": nested,
        "purpose": (version.purpose if version else "") or "",
        "when_to_use": (version.when_to_use if version else "") or "",
        "instructions": (version.instructions_markdown if version else "") or "",
        "instructions_markdown": (version.instructions_markdown if version else "") or "",
        "capabilities": list(version.capabilities_json or []) if version else [],
        "tools": list(version.required_tools_json or []) if version else [],
        "knowledge": list(version.knowledge_requirements_json or []) if version else [],
        "inputs": dict(version.input_schema_json or {}) if version else {},
        "outputs": dict(version.output_schema_json or {}) if version else {},
        "constraints": _constraints_list(version.constraints_markdown if version else None),
        "risk_level": (version.risk_level if version else "low") or "low",
        "examples": list(version.examples_json or []) if version else [],
        "evaluation_criteria": list(version.evaluation_criteria_json or []) if version else [],
        "version": int(version.version_number) if version else 0,
        "parent_skill_id": None,
    }


async def enrich_skill_response(db: AsyncSession, skill: Skill) -> SkillResponse:
    version: SkillVersion | None = None
    if skill.current_version_id:
        version = await db.get(SkillVersion, skill.current_version_id)
    return SkillResponse.model_validate(_skill_payload(skill, version))


async def enrich_skills(db: AsyncSession, skills: list[Skill]) -> list[SkillResponse]:
    version_ids = [s.current_version_id for s in skills if s.current_version_id]
    versions: dict[str, SkillVersion] = {}
    if version_ids:
        result = await db.execute(select(SkillVersion).where(SkillVersion.id.in_(version_ids)))
        for v in result.scalars().all():
            versions[v.id] = v
    return [
        SkillResponse.model_validate(
            _skill_payload(skill, versions.get(skill.current_version_id or ""))
        )
        for skill in skills
    ]


def skill_draft_response(draft: SkillDraft) -> SkillDraftResponse:
    errors = list(draft.validation_errors_json or [])
    warnings = list(draft.warnings_json or [])
    return SkillDraftResponse(
        id=draft.id,
        owner_id=draft.owner_id,
        company_id=draft.company_id,
        skill_id=draft.skill_id,
        source_type=draft.source_type,
        source_task_id=draft.source_task_id,
        source_project_id=draft.source_project_id,
        project_id=draft.source_project_id,
        status=draft.status,
        name=draft.name,
        slug=draft.slug,
        description=draft.description or "",
        purpose=draft.purpose or "",
        when_to_use=draft.when_to_use or "",
        instructions_markdown=draft.instructions_markdown or "",
        instructions=draft.instructions_markdown or "",
        scope=draft.scope,
        risk_level=draft.risk_level or "low",
        capabilities_json=list(draft.capabilities_json or []),
        required_tools_json=list(draft.required_tools_json or []),
        knowledge_requirements_json=list(draft.knowledge_requirements_json or []),
        input_schema_json=dict(draft.input_schema_json or {}),
        output_schema_json=dict(draft.output_schema_json or {}),
        constraints_markdown=draft.constraints_markdown or "",
        approval_policy_json=dict(draft.approval_policy_json or {}),
        examples_json=list(draft.examples_json or []),
        evaluation_criteria_json=list(draft.evaluation_criteria_json or []),
        validation_errors_json=errors,
        warnings_json=warnings,
        unmatched_sections_json=list(draft.unmatched_sections_json or []),
        duplicate_matches_json=list(draft.duplicate_matches_json or []),
        confidence=draft.confidence,
        generation_metadata_json=dict(draft.generation_metadata_json or {}),
        created_at=draft.created_at,
        updated_at=draft.updated_at,
        capabilities=list(draft.capabilities_json or []),
        tools=list(draft.required_tools_json or []),
        knowledge=list(draft.knowledge_requirements_json or []),
        inputs=dict(draft.input_schema_json or {}),
        outputs=dict(draft.output_schema_json or {}),
        constraints=_constraints_list(draft.constraints_markdown),
        examples=list(draft.examples_json or []),
        evaluation_criteria=list(draft.evaluation_criteria_json or []),
        validation_errors=[str(e) for e in errors],
        validation_warnings=[str(w) for w in warnings],
        duplicate_matches=list(draft.duplicate_matches_json or []),
        is_valid=len(errors) == 0 and bool((draft.purpose or "").strip()),
    )
