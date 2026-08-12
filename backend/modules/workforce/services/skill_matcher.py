"""Deterministic skill matching service."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.workforce.models import Skill
from backend.modules.workforce.repository import WorkforceRepository
from backend.modules.workforce.schemas import SkillMatchResult


def _jaccard_similarity(set1: set[str], set2: set[str]) -> float:
    """Compute Jaccard similarity between two sets."""
    if not set1 and not set2:
        return 0.0
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    return intersection / union if union > 0 else 0.0


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
    ) -> list[SkillMatchResult]:
        """
        Match skills to requirements using deterministic scoring.

        Scoring components:
        - capability_overlap: Jaccard similarity of capabilities
        - tool_overlap: Jaccard similarity of tools
        - scope_relevance: preference for matching scopes
        - status_bonus: active > testing > draft
        """
        skills = await self.repo.list_skills(owner_id, status=None)
        matches: list[SkillMatchResult] = []

        req_cap_set = set(c.lower().strip() for c in required_capabilities if c)
        req_tool_set = set(t.lower().strip() for t in required_tools if t)

        for skill in skills:
            if not skill.current_version_id:
                continue

            version = await self.repo.get_skill_version(skill.current_version_id)
            if not version:
                continue

            skill_cap_set = set(c.lower().strip() for c in version.capabilities_json if c)
            skill_tool_set = set(t.lower().strip() for t in version.required_tools_json if t)

            capability_overlap = _jaccard_similarity(req_cap_set, skill_cap_set)
            tool_overlap = _jaccard_similarity(req_tool_set, skill_tool_set)

            scope_relevance = 0.0
            if skill.scope == task_scope:
                scope_relevance = 1.0
            elif skill.scope == "project" and task_scope in {"task", "project"}:
                scope_relevance = 0.7
            elif skill.scope == "organization":
                scope_relevance = 0.5

            status_bonus = 0.0
            if skill.status == "active":
                status_bonus = 0.3
            elif skill.status == "testing":
                status_bonus = 0.2
            elif skill.status == "draft":
                status_bonus = 0.1

            score = (
                capability_overlap * 0.4
                + tool_overlap * 0.3
                + scope_relevance * 0.2
                + status_bonus * 0.1
            )

            if score < 0.1:
                continue

            matched_caps = list(req_cap_set & skill_cap_set)
            matched_tools = list(req_tool_set & skill_tool_set)

            explanation_parts = []
            if capability_overlap > 0:
                explanation_parts.append(
                    f"{int(capability_overlap * 100)}% capability overlap"
                )
            if tool_overlap > 0:
                explanation_parts.append(f"{int(tool_overlap * 100)}% tool overlap")
            if scope_relevance > 0.5:
                explanation_parts.append(f"scope={skill.scope}")
            if skill.status == "active":
                explanation_parts.append("active")

            matches.append(
                SkillMatchResult(
                    skill_id=skill.id,
                    skill_name=skill.name,
                    skill_slug=skill.slug,
                    score=score,
                    capability_overlap=capability_overlap,
                    tool_overlap=tool_overlap,
                    scope_relevance=scope_relevance,
                    status_bonus=status_bonus,
                    explanation=", ".join(explanation_parts) if explanation_parts else "low match",
                    matched_capabilities=matched_caps,
                    matched_tools=matched_tools,
                )
            )

        matches.sort(key=lambda m: m.score, reverse=True)
        return matches[:20]
