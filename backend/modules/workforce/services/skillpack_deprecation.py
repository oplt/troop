"""SkillPack deprecation helpers — migrate legacy packs into SkillDraft/Skill."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.team.models import SkillPack
from backend.modules.workforce.repository import WorkforceRepository
from backend.modules.workforce.services.skill_service import SkillService


class SkillPackDeprecationService:
    """Convert legacy SkillPack rows into canonical Skill + SkillVersion."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = WorkforceRepository(db)
        self.skills = SkillService(db)

    async def list_legacy_packs(self) -> list[SkillPack]:
        result = await self.db.execute(select(SkillPack).order_by(SkillPack.slug.asc()))
        return list(result.scalars().all())

    async def migrate_pack_for_owner(
        self,
        owner_id: str,
        pack: SkillPack,
        *,
        company_id: str | None = None,
        publish: bool = True,
    ) -> dict[str, Any]:
        existing = await self.repo.find_skill_by_slug(owner_id, pack.slug)
        if existing:
            return {
                "status": "skipped",
                "reason": "skill_slug_exists",
                "skill_id": existing.id,
                "skill_pack_id": pack.id,
            }

        draft = await self.repo.create_skill_draft(
            owner_id=owner_id,
            company_id=company_id,
            name=pack.name,
            slug=pack.slug,
            description=pack.description or "",
            purpose=pack.description or pack.name,
            when_to_use=f"Use when working with the `{pack.slug}` skill pack capabilities.",
            instructions_markdown=pack.rules_markdown or pack.description or pack.name,
            scope="organization",
            risk_level="medium",
            source_type="markdown_import",
            capabilities_json=list(pack.capabilities_json or []),
            required_tools_json=list(pack.allowed_tools_json or []),
            generation_metadata_json={
                "legacy_skill_pack_id": pack.id,
                "migrated_from": "skill_packs",
            },
            status="draft",
        )
        await self.db.commit()
        if not publish:
            return {
                "status": "draft_created",
                "draft_id": draft.id,
                "skill_pack_id": pack.id,
            }

        skill = await self.skills.publish_draft(owner_id, draft.id, created_by=owner_id)
        skill.legacy_skill_pack_id = pack.id
        await self.db.commit()
        return {
            "status": "migrated",
            "skill_id": skill.id,
            "draft_id": draft.id,
            "skill_pack_id": pack.id,
        }

    async def migrate_all_for_owner(
        self, owner_id: str, *, company_id: str | None = None, publish: bool = True
    ) -> list[dict[str, Any]]:
        packs = await self.list_legacy_packs()
        results = []
        for pack in packs:
            results.append(
                await self.migrate_pack_for_owner(
                    owner_id, pack, company_id=company_id, publish=publish
                )
            )
        return results
