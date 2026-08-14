"""Deterministic skill matching with hard filters + explainable scores.

Avoids N+1 by batch-loading skill versions and usage stats for candidate skills.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.validation.text import jaccard_similarity, token_jaccard
from backend.modules.workforce.models import Skill, SkillUsageStat, SkillVersion
from backend.modules.workforce.repository import WorkforceRepository
from backend.modules.workforce.schemas import SkillMatchResult

_RISK_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def _schema_type_hint(value: object) -> str:
    if isinstance(value, dict):
        explicit = value.get("type")
        if isinstance(explicit, str) and explicit.strip():
            return explicit.strip().lower()
        if "properties" in value:
            return "object"
        if "items" in value:
            return "array"
    return "unknown"


def _schema_compat_score(
    required_schema: dict | None,
    skill_schema: dict | None,
) -> float:
    """Overlap of property keys and coarse type hints between schemas."""
    if not required_schema:
        return 0.5
    req_props = required_schema.get("properties")
    if not isinstance(req_props, dict) or not req_props:
        return 0.5
    skill_props = (skill_schema or {}).get("properties")
    if not isinstance(skill_props, dict) or not skill_props:
        return 0.0

    req_keys = {str(k).lower() for k in req_props}
    skill_keys = {str(k).lower() for k in skill_props}
    key_overlap = jaccard_similarity(req_keys, skill_keys)
    if not req_keys:
        return 0.5

    type_matches = 0
    for key, req_def in req_props.items():
        skill_def = skill_props.get(key)
        if not isinstance(skill_def, dict):
            continue
        if _schema_type_hint(req_def) == _schema_type_hint(skill_def):
            type_matches += 1
    type_score = type_matches / len(req_props)
    return key_overlap * 0.65 + type_score * 0.35


def _risk_compat_score(task_risk: str | None, skill_risk: str) -> float:
    skill_rank = _RISK_RANK.get((skill_risk or "low").lower(), 1)
    if not task_risk:
        # Prefer lower-risk skills when task risk is unknown — slight adjustment only.
        return max(0.55, 1.0 - skill_rank * 0.1)
    task_rank = _RISK_RANK.get(task_risk.lower(), 1)
    if skill_rank <= task_rank:
        return 1.0
    return max(0.0, 1.0 - (skill_rank - task_rank) * 0.25)


def _usage_success_score(stat: SkillUsageStat | None) -> float:
    if stat is None or stat.run_count <= 0:
        return 0.5
    return stat.success_count / stat.run_count


def _scope_allowed(
    skill: Skill,
    *,
    task_id: str | None,
    project_id: str | None,
    company_id: str | None,
) -> bool:
    if skill.status not in {"active", "testing"}:
        return False
    if not skill.current_version_id:
        return False
    if skill.scope == "task":
        return bool(task_id and skill.task_id == task_id)
    if skill.scope == "project":
        return bool(project_id and skill.project_id == project_id)
    if skill.scope == "organization":
        return not (company_id and skill.company_id and skill.company_id != company_id)
    if skill.scope in {"template", "global"}:
        return skill.status == "active"
    return False


class SkillMatcherService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = WorkforceRepository(db)

    async def match_skills(
        self,
        owner_id: str,
        required_capabilities: list[str],
        required_tools: list[str],
        task_scope: str = "task",
        *,
        task_id: str | None = None,
        project_id: str | None = None,
        company_id: str | None = None,
        required_knowledge: list[str] | None = None,
        task_risk_level: str | None = None,
        required_input_schema: dict | None = None,
        required_output_schema: dict | None = None,
        available_knowledge_keys: list[str] | None = None,
        query_text: str | None = None,
    ) -> list[SkillMatchResult]:
        skills = await self.repo.list_skills(owner_id, status=None)
        candidates = [
            skill
            for skill in skills
            if _scope_allowed(skill, task_id=task_id, project_id=project_id, company_id=company_id)
        ]
        version_ids = [s.current_version_id for s in candidates if s.current_version_id]
        versions_by_id: dict[str, SkillVersion] = {}
        if version_ids:
            result = await self.db.execute(
                select(SkillVersion).where(SkillVersion.id.in_(version_ids))
            )
            versions_by_id = {v.id: v for v in result.scalars().all()}

        skill_ids = [s.id for s in candidates]
        usage_stats = await self.repo.list_skill_usage_stats(skill_ids)
        usage_by_skill: dict[str, SkillUsageStat] = {}
        for skill in candidates:
            version_id = skill.current_version_id
            if not version_id:
                continue
            matching = [
                stat
                for stat in usage_stats
                if stat.skill_id == skill.id and stat.skill_version_id == version_id
            ]
            if matching:
                usage_by_skill[skill.id] = max(matching, key=lambda s: s.run_count)

        req_cap_set = {c.lower().strip() for c in required_capabilities if c}
        req_tool_set = {t.lower().strip() for t in required_tools if t}
        req_knowledge_set = {k.lower().strip() for k in (required_knowledge or []) if k}
        available_knowledge_set = {k.lower().strip() for k in (available_knowledge_keys or []) if k}
        query = (query_text or "").strip()
        matches: list[SkillMatchResult] = []

        for skill in candidates:
            version = versions_by_id.get(skill.current_version_id or "")
            if not version:
                continue

            skill_cap_set = {c.lower().strip() for c in (version.capabilities_json or []) if c}
            skill_tool_set = {t.lower().strip() for t in (version.required_tools_json or []) if t}
            skill_knowledge_set = {
                k.lower().strip() for k in (version.knowledge_requirements_json or []) if k
            }

            capability_overlap = jaccard_similarity(req_cap_set, skill_cap_set)
            tool_overlap = jaccard_similarity(req_tool_set, skill_tool_set) if req_tool_set else 0.5
            knowledge_overlap = (
                jaccard_similarity(req_knowledge_set, skill_knowledge_set)
                if req_knowledge_set
                else 0.5
            )
            knowledge_availability = (
                jaccard_similarity(available_knowledge_set, skill_knowledge_set)
                if available_knowledge_set and skill_knowledge_set
                else 0.5
                if not skill_knowledge_set
                else 0.0
            )
            input_schema_score = _schema_compat_score(
                required_input_schema,
                dict(version.input_schema_json or {}),
            )
            output_schema_score = _schema_compat_score(
                required_output_schema,
                dict(version.output_schema_json or {}),
            )
            schema_score = (
                (input_schema_score + output_schema_score) / 2.0
                if required_input_schema or required_output_schema
                else 0.5
            )
            skill_text = " ".join(
                [
                    str(version.purpose or ""),
                    str(version.when_to_use or ""),
                    " ".join(str(c) for c in (version.capabilities_json or [])),
                ]
            ).strip()
            semantic_score = token_jaccard(query, skill_text) if query and skill_text else 0.5
            risk_score = _risk_compat_score(task_risk_level, version.risk_level or "low")
            history_score = _usage_success_score(usage_by_skill.get(skill.id))

            # Scope relevance — do not give free points merely for being active org-wide.
            if skill.scope == "task" and task_id and skill.task_id == task_id:
                scope_relevance = 1.0
            elif skill.scope == "project" and project_id and skill.project_id == project_id:
                scope_relevance = 0.9
            elif skill.scope == "organization":
                scope_relevance = 0.55
            elif skill.scope in {"template", "global"}:
                scope_relevance = 0.45
            else:
                scope_relevance = 0.2

            status_bonus = {"active": 0.15, "testing": 0.08}.get(skill.status, 0.0)

            # Capability coverage dominates; active status alone cannot inflate a zero-overlap skill.
            if capability_overlap <= 0 and tool_overlap < 0.2:
                continue

            score = (
                capability_overlap * 0.34
                + tool_overlap * 0.13
                + knowledge_overlap * 0.07
                + knowledge_availability * 0.06
                + schema_score * 0.08
                + semantic_score * 0.10
                + scope_relevance * 0.10
                + status_bonus * 0.05
                + history_score * 0.05
                + risk_score * 0.02
            )
            if score < 0.12:
                continue

            matched_caps = sorted(req_cap_set & skill_cap_set)
            matched_tools = sorted(req_tool_set & skill_tool_set)
            explanation_parts = [
                f"capabilities {int(capability_overlap * 100)}%",
            ]
            if req_tool_set:
                explanation_parts.append(f"tools {int(tool_overlap * 100)}%")
            if req_knowledge_set:
                explanation_parts.append(f"knowledge {int(knowledge_overlap * 100)}%")
            if available_knowledge_set and skill_knowledge_set:
                explanation_parts.append(
                    f"knowledge_available {int(knowledge_availability * 100)}%"
                )
            if required_input_schema or required_output_schema:
                explanation_parts.append(f"schema {int(schema_score * 100)}%")
            if query:
                explanation_parts.append(f"semantic {int(semantic_score * 100)}%")
            explanation_parts.append(f"risk={version.risk_level or 'low'}")
            if usage_by_skill.get(skill.id):
                explanation_parts.append(f"success_rate {int(history_score * 100)}%")
            explanation_parts.append(f"scope={skill.scope}")
            explanation_parts.append(f"status={skill.status}")

            matches.append(
                SkillMatchResult(
                    skill_id=skill.id,
                    skill_name=skill.name,
                    skill_slug=skill.slug,
                    score=round(score, 4),
                    capability_overlap=capability_overlap,
                    tool_overlap=tool_overlap,
                    scope_relevance=scope_relevance,
                    status_bonus=status_bonus,
                    explanation="; ".join(explanation_parts),
                    matched_capabilities=matched_caps,
                    matched_tools=matched_tools,
                    scope=skill.scope,
                    status=skill.status,
                )
            )

        matches.sort(key=lambda m: m.score, reverse=True)
        return matches[:20]
