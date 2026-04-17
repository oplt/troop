from __future__ import annotations

from sqlalchemy import or_, select

from backend.modules.team.models import (
    AgentProfile,
    AgentProfileVersion,
    AgentTemplateCatalog,
    ProjectAgentMembership,
    SkillPack,
    TeamTemplateCatalog,
)


class TeamRepositoryMixin:
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

    async def list_team_templates(self) -> list[TeamTemplateCatalog]:
        result = await self.db.execute(
            select(TeamTemplateCatalog).order_by(TeamTemplateCatalog.name.asc())
        )
        return list(result.scalars().all())

    async def get_team_template(self, template_id: str) -> TeamTemplateCatalog | None:
        result = await self.db.execute(
            select(TeamTemplateCatalog).where(TeamTemplateCatalog.id == template_id)
        )
        return result.scalar_one_or_none()

    async def get_team_template_by_slug(self, slug: str) -> TeamTemplateCatalog | None:
        result = await self.db.execute(
            select(TeamTemplateCatalog).where(TeamTemplateCatalog.slug == slug)
        )
        return result.scalar_one_or_none()

    async def create_team_template(self, **kwargs) -> TeamTemplateCatalog:
        item = TeamTemplateCatalog(**kwargs)
        self.db.add(item)
        await self.db.flush()
        return item

    async def list_agent_templates(self) -> list[AgentTemplateCatalog]:
        result = await self.db.execute(
            select(AgentTemplateCatalog).order_by(AgentTemplateCatalog.name.asc())
        )
        return list(result.scalars().all())

    async def get_agent_template_by_slug(self, slug: str) -> AgentTemplateCatalog | None:
        result = await self.db.execute(select(AgentTemplateCatalog).where(AgentTemplateCatalog.slug == slug))
        return result.scalar_one_or_none()

    async def create_agent_template(self, **kwargs) -> AgentTemplateCatalog:
        item = AgentTemplateCatalog(**kwargs)
        self.db.add(item)
        await self.db.flush()
        return item

    async def list_project_memberships(self, project_id: str) -> list[ProjectAgentMembership]:
        result = await self.db.execute(
            select(ProjectAgentMembership)
            .where(ProjectAgentMembership.project_id == project_id)
            .order_by(ProjectAgentMembership.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_project_membership(
        self, project_id: str, agent_id: str
    ) -> ProjectAgentMembership | None:
        result = await self.db.execute(
            select(ProjectAgentMembership).where(
                ProjectAgentMembership.project_id == project_id,
                ProjectAgentMembership.agent_id == agent_id,
            )
        )
        return result.scalar_one_or_none()

    async def create_project_membership(self, **kwargs) -> ProjectAgentMembership:
        item = ProjectAgentMembership(**kwargs)
        self.db.add(item)
        await self.db.flush()
        return item

    async def get_project_membership_by_id(
        self, project_id: str, membership_id: str
    ) -> ProjectAgentMembership | None:
        result = await self.db.execute(
            select(ProjectAgentMembership).where(
                ProjectAgentMembership.project_id == project_id,
                ProjectAgentMembership.id == membership_id,
            )
        )
        return result.scalar_one_or_none()
