"""Agent, template, and legacy SkillPack repository accessors."""

from __future__ import annotations

from sqlalchemy import or_, select

from backend.modules.orchestration.models import AgentProfile, AgentProfileVersion, AgentTemplateCatalog, SkillPack


class OrchestrationAgentsRepositoryMixin:
    async def list_agents(self, owner_id: str, project_id: str | None = None) -> list[AgentProfile]:
        stmt = select(AgentProfile).where(AgentProfile.owner_id == owner_id)
        if project_id is None:
            stmt = stmt.where(AgentProfile.project_id.is_(None))
        else:
            stmt = stmt.where(
                or_(AgentProfile.project_id == project_id, AgentProfile.project_id.is_(None))
            )
        result = await self.db.execute(stmt.order_by(AgentProfile.updated_at.desc()))
        return list(result.scalars().all())

    async def get_agent(self, owner_id: str, agent_id: str) -> AgentProfile | None:
        result = await self.db.execute(
            select(AgentProfile).where(
                AgentProfile.id == agent_id,
                AgentProfile.owner_id == owner_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_agent_by_slug(self, owner_id: str, slug: str) -> AgentProfile | None:
        result = await self.db.execute(
            select(AgentProfile).where(
                AgentProfile.owner_id == owner_id,
                AgentProfile.slug == slug,
            )
        )
        return result.scalar_one_or_none()

    async def create_agent(self, **kwargs) -> AgentProfile:
        item = AgentProfile(**kwargs)
        self.db.add(item)
        await self.db.flush()
        return item

    async def create_agent_version(self, **kwargs) -> AgentProfileVersion:
        item = AgentProfileVersion(**kwargs)
        self.db.add(item)
        await self.db.flush()
        return item

    async def list_agent_versions(self, agent_id: str) -> list[AgentProfileVersion]:
        result = await self.db.execute(
            select(AgentProfileVersion)
            .where(AgentProfileVersion.agent_profile_id == agent_id)
            .order_by(AgentProfileVersion.version_number.desc())
        )
        return list(result.scalars().all())

    async def list_skill_packs(self) -> list[SkillPack]:
        result = await self.db.execute(select(SkillPack).order_by(SkillPack.name.asc()))
        return list(result.scalars().all())

    async def get_skill_pack_by_slug(self, slug: str) -> SkillPack | None:
        result = await self.db.execute(select(SkillPack).where(SkillPack.slug == slug))
        return result.scalar_one_or_none()

    async def create_skill_pack(self, **kwargs) -> SkillPack:
        item = SkillPack(**kwargs)
        self.db.add(item)
        await self.db.flush()
        return item

    async def list_agent_templates(self) -> list[AgentTemplateCatalog]:
        result = await self.db.execute(
            select(AgentTemplateCatalog).order_by(AgentTemplateCatalog.name.asc())
        )
        return list(result.scalars().all())

    async def get_agent_template(self, template_id: str) -> AgentTemplateCatalog | None:
        result = await self.db.execute(
            select(AgentTemplateCatalog).where(AgentTemplateCatalog.id == template_id)
        )
        return result.scalar_one_or_none()

    async def get_agent_template_by_slug(self, slug: str) -> AgentTemplateCatalog | None:
        result = await self.db.execute(
            select(AgentTemplateCatalog)
            .where(AgentTemplateCatalog.slug == slug)
            .order_by(AgentTemplateCatalog.created_at.desc(), AgentTemplateCatalog.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def create_agent_template(self, **kwargs) -> AgentTemplateCatalog:
        item = AgentTemplateCatalog(**kwargs)
        self.db.add(item)
        await self.db.flush()
        return item
