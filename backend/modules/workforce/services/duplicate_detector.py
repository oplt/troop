"""Duplicate skill detection service."""

from __future__ import annotations

import difflib

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.workforce.repository import WorkforceRepository
from backend.modules.workforce.schemas import DuplicateMatch


class DuplicateDetectorService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = WorkforceRepository(db)

    async def detect_duplicates(
        self,
        owner_id: str,
        name: str,
        slug: str,
        capabilities: list[str],
        threshold: float = 0.75,
    ) -> list[DuplicateMatch]:
        """
        Detect duplicate skills using name/slug similarity + capability overlap.

        Returns matches scoring above threshold (0-1).
        """
        existing_skills = await self.repo.list_skills(owner_id, status=None)
        matches: list[DuplicateMatch] = []

        name_lower = name.lower().strip()
        slug_lower = slug.lower().strip()
        cap_set = set(c.lower().strip() for c in capabilities if c)

        for skill in existing_skills:
            skill_name_lower = skill.name.lower().strip()
            skill_slug_lower = skill.slug.lower().strip()

            name_sim = difflib.SequenceMatcher(None, name_lower, skill_name_lower).ratio()
            slug_sim = difflib.SequenceMatcher(None, slug_lower, skill_slug_lower).ratio()

            version = None
            if skill.current_version_id:
                version = await self.repo.get_skill_version(skill.current_version_id)

            cap_sim = 0.0
            if version and version.capabilities_json:
                skill_cap_set = set(c.lower().strip() for c in version.capabilities_json if c)
                if cap_set and skill_cap_set:
                    intersection = len(cap_set & skill_cap_set)
                    union = len(cap_set | skill_cap_set)
                    cap_sim = intersection / union if union > 0 else 0.0

            similarity = max(name_sim, slug_sim) * 0.6 + cap_sim * 0.4

            if similarity >= threshold:
                reason_parts = []
                if name_sim >= 0.8:
                    reason_parts.append(f"name {int(name_sim * 100)}% similar")
                if slug_sim >= 0.8:
                    reason_parts.append(f"slug {int(slug_sim * 100)}% similar")
                if cap_sim >= 0.5:
                    reason_parts.append(f"capabilities {int(cap_sim * 100)}% overlap")

                matches.append(
                    DuplicateMatch(
                        draft_id=skill.id,
                        draft_name=skill.name,
                        similarity_score=similarity,
                        reason=", ".join(reason_parts) if reason_parts else "high similarity",
                    )
                )

        matches.sort(key=lambda m: m.similarity_score, reverse=True)
        return matches
