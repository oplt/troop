"""Workforce persistence layer matching all service calls."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.workforce.models import (
    ActionPolicy,
    AgentSkillAssignment,
    ConnectorDefinition,
    ConnectorInstallation,
    Department,
    ProjectAnalysis,
    Skill,
    SkillDraft,
    SkillEvaluation,
    SkillUsageStat,
    SkillVersion,
    TaskAnalysis,
    TaskRequirement,
    ToolDefinition,
    ToolGrant,
    WorkflowDefinition,
)


class WorkforceRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ─── Departments ─────────────────────────────────────────────

    async def list_departments(
        self, company_id: str, *, include_archived: bool = False
    ) -> list[Department]:
        stmt = select(Department).where(Department.company_id == company_id)
        if not include_archived:
            stmt = stmt.where(Department.is_archived.is_(False))
        stmt = stmt.order_by(Department.name.asc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_department(self, department_id: str, company_id: str) -> Department | None:
        """Get department with company_id filter for ownership verification."""
        result = await self.db.execute(
            select(Department).where(
                Department.id == department_id,
                Department.company_id == company_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_department_by_id(self, department_id: str) -> Department | None:
        result = await self.db.execute(select(Department).where(Department.id == department_id))
        return result.scalar_one_or_none()

    async def find_department_by_slug(self, company_id: str, slug: str) -> Department | None:
        result = await self.db.execute(
            select(Department).where(
                Department.company_id == company_id,
                Department.slug == slug,
            )
        )
        return result.scalar_one_or_none()

    async def create_department(self, **kwargs: Any) -> Department:
        item = Department(**kwargs)
        self.db.add(item)
        await self.db.flush()
        return item

    # ─── Skills ──────────────────────────────────────────────────

    async def list_skills(
        self,
        owner_id: str,
        *,
        status: str | None = None,
        scope: str | None = None,
        project_id: str | None = None,
    ) -> list[Skill]:
        stmt = select(Skill).where(Skill.owner_id == owner_id)
        if status:
            stmt = stmt.where(Skill.status == status)
        if scope:
            stmt = stmt.where(Skill.scope == scope)
        if project_id:
            stmt = stmt.where((Skill.project_id == project_id) | (Skill.scope == "organization"))
        stmt = stmt.order_by(Skill.name.asc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_skill(self, skill_id: str, owner_id: str) -> Skill | None:
        """Get skill with owner_id filter for ownership verification."""
        result = await self.db.execute(
            select(Skill).where(
                Skill.id == skill_id,
                Skill.owner_id == owner_id,
            )
        )
        return result.scalar_one_or_none()

    async def find_skill_by_slug(self, owner_id: str, slug: str) -> Skill | None:
        result = await self.db.execute(
            select(Skill).where(
                Skill.owner_id == owner_id,
                Skill.slug == slug,
            )
        )
        return result.scalar_one_or_none()

    async def create_skill(self, **kwargs: Any) -> Skill:
        item = Skill(**kwargs)
        self.db.add(item)
        await self.db.flush()
        return item

    # ─── Skill Versions ──────────────────────────────────────────

    async def create_skill_version(self, **kwargs: Any) -> SkillVersion:
        item = SkillVersion(**kwargs)
        self.db.add(item)
        await self.db.flush()
        return item

    async def list_skill_versions(self, skill_id: str) -> list[SkillVersion]:
        result = await self.db.execute(
            select(SkillVersion)
            .where(SkillVersion.skill_id == skill_id)
            .order_by(SkillVersion.version_number.desc())
        )
        return list(result.scalars().all())

    async def get_skill_version(self, version_id: str) -> SkillVersion | None:
        result = await self.db.execute(select(SkillVersion).where(SkillVersion.id == version_id))
        return result.scalar_one_or_none()

    async def get_latest_skill_version_number(self, skill_id: str) -> int:
        """Return latest version number or 0 if no versions exist."""
        versions = await self.list_skill_versions(skill_id)
        if not versions:
            return 0
        return max(v.version_number for v in versions)

    # ─── Skill Drafts ────────────────────────────────────────────

    async def list_skill_drafts(
        self, owner_id: str, *, status: str | None = None
    ) -> list[SkillDraft]:
        stmt = select(SkillDraft).where(SkillDraft.owner_id == owner_id)
        if status:
            stmt = stmt.where(SkillDraft.status == status)
        stmt = stmt.order_by(SkillDraft.updated_at.desc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_skill_draft(self, draft_id: str, owner_id: str) -> SkillDraft | None:
        """Get draft with owner_id filter for ownership verification."""
        result = await self.db.execute(
            select(SkillDraft).where(
                SkillDraft.id == draft_id,
                SkillDraft.owner_id == owner_id,
            )
        )
        return result.scalar_one_or_none()

    async def create_skill_draft(self, **kwargs: Any) -> SkillDraft:
        item = SkillDraft(**kwargs)
        self.db.add(item)
        await self.db.flush()
        return item

    # ─── Task Analysis ───────────────────────────────────────────

    async def get_latest_task_analysis(self, task_id: str) -> TaskAnalysis | None:
        result = await self.db.execute(
            select(TaskAnalysis)
            .where(TaskAnalysis.task_id == task_id)
            .order_by(TaskAnalysis.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_task_analysis_by_fingerprint(
        self, fingerprint: str, task_id: str
    ) -> TaskAnalysis | None:
        result = await self.db.execute(
            select(TaskAnalysis)
            .where(
                TaskAnalysis.task_id == task_id,
                TaskAnalysis.content_fingerprint == fingerprint,
            )
            .order_by(TaskAnalysis.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def create_task_analysis(self, **kwargs: Any) -> TaskAnalysis:
        item = TaskAnalysis(**kwargs)
        self.db.add(item)
        await self.db.flush()
        return item

    async def create_task_requirement(self, **kwargs: Any) -> TaskRequirement:
        item = TaskRequirement(**kwargs)
        self.db.add(item)
        await self.db.flush()
        return item

    async def list_task_requirements(self, analysis_id: str) -> list[TaskRequirement]:
        result = await self.db.execute(
            select(TaskRequirement).where(TaskRequirement.analysis_id == analysis_id)
        )
        return list(result.scalars().all())

    # ─── Project Analysis ────────────────────────────────────────

    async def create_project_analysis(self, **kwargs: Any) -> ProjectAnalysis:
        item = ProjectAnalysis(**kwargs)
        self.db.add(item)
        await self.db.flush()
        return item

    # ─── Agent Skill Assignments ─────────────────────────────────

    async def list_agent_skill_assignments(self, agent_id: str) -> list[AgentSkillAssignment]:
        result = await self.db.execute(
            select(AgentSkillAssignment).where(
                AgentSkillAssignment.agent_id == agent_id,
                AgentSkillAssignment.enabled.is_(True),
            )
        )
        return list(result.scalars().all())

    async def create_agent_skill_assignment(self, **kwargs: Any) -> AgentSkillAssignment:
        item = AgentSkillAssignment(**kwargs)
        self.db.add(item)
        await self.db.flush()
        return item

    async def upsert_agent_skill_assignment(self, **kwargs: Any) -> AgentSkillAssignment:
        agent_id = kwargs["agent_id"]
        skill_id = kwargs["skill_id"]
        result = await self.db.execute(
            select(AgentSkillAssignment).where(
                AgentSkillAssignment.agent_id == agent_id,
                AgentSkillAssignment.skill_id == skill_id,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            for key, value in kwargs.items():
                setattr(existing, key, value)
            await self.db.flush()
            return existing
        item = AgentSkillAssignment(**kwargs)
        self.db.add(item)
        await self.db.flush()
        return item

    # ─── Skill Evaluations ───────────────────────────────────────

    async def create_skill_evaluation(self, **kwargs: Any) -> SkillEvaluation:
        item = SkillEvaluation(**kwargs)
        self.db.add(item)
        await self.db.flush()
        return item

    async def get_skill_usage_stat(
        self, skill_id: str, skill_version_id: str | None
    ) -> SkillUsageStat | None:
        stmt = select(SkillUsageStat).where(SkillUsageStat.skill_id == skill_id)
        if skill_version_id is None:
            stmt = stmt.where(SkillUsageStat.skill_version_id.is_(None))
        else:
            stmt = stmt.where(SkillUsageStat.skill_version_id == skill_version_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def create_skill_usage_stat(self, **kwargs: Any) -> SkillUsageStat:
        item = SkillUsageStat(**kwargs)
        self.db.add(item)
        await self.db.flush()
        return item

    async def list_skill_usage_stats(self, skill_ids: list[str]) -> list[SkillUsageStat]:
        if not skill_ids:
            return []
        result = await self.db.execute(
            select(SkillUsageStat).where(SkillUsageStat.skill_id.in_(skill_ids))
        )
        return list(result.scalars().all())

    # ─── Connectors ──────────────────────────────────────────────

    async def list_connector_installations(self, owner_id: str) -> list[ConnectorInstallation]:
        result = await self.db.execute(
            select(ConnectorInstallation)
            .where(ConnectorInstallation.owner_id == owner_id)
            .order_by(ConnectorInstallation.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_connector_definitions_by_ids(
        self, definition_ids: list[str]
    ) -> list[ConnectorDefinition]:
        if not definition_ids:
            return []
        result = await self.db.execute(
            select(ConnectorDefinition).where(ConnectorDefinition.id.in_(definition_ids))
        )
        return list(result.scalars().all())

    # ─── Tool Grants ─────────────────────────────────────────────

    async def list_tool_grants_for_subject(
        self, subject_type: str, subject_id: str, *, effect: str | None = "allow"
    ) -> list[ToolGrant]:
        stmt = select(ToolGrant).where(
            ToolGrant.subject_type == subject_type,
            ToolGrant.subject_id == subject_id,
        )
        if effect is not None:
            stmt = stmt.where(ToolGrant.effect == effect)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_tool_grants_for_subjects(
        self, subject_type: str, subject_ids: list[str], *, effect: str | None = "allow"
    ) -> list[ToolGrant]:
        if not subject_ids:
            return []
        stmt = select(ToolGrant).where(
            ToolGrant.subject_type == subject_type,
            ToolGrant.subject_id.in_(subject_ids),
        )
        if effect is not None:
            stmt = stmt.where(ToolGrant.effect == effect)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_tool_definitions_by_ids(self, ids: list[str]) -> list[ToolDefinition]:
        if not ids:
            return []
        result = await self.db.execute(select(ToolDefinition).where(ToolDefinition.id.in_(ids)))
        return list(result.scalars().all())

    # ─── Action Policies ─────────────────────────────────────────

    async def list_action_policies(self, owner_id: str) -> list[ActionPolicy]:
        result = await self.db.execute(
            select(ActionPolicy)
            .where(ActionPolicy.owner_id == owner_id)
            .order_by(ActionPolicy.action_key.asc())
        )
        return list(result.scalars().all())

    # ─── Tool Definitions ────────────────────────────────────────

    async def list_tool_definitions(self, *, is_active: bool | None = True) -> list[ToolDefinition]:
        stmt = select(ToolDefinition)
        if is_active is not None:
            stmt = stmt.where(ToolDefinition.is_active.is_(is_active))
        stmt = stmt.order_by(ToolDefinition.name.asc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_tool_definition(self, slug: str) -> ToolDefinition | None:
        result = await self.db.execute(select(ToolDefinition).where(ToolDefinition.slug == slug))
        return result.scalar_one_or_none()

    async def create_tool_definition(self, **kwargs: Any) -> ToolDefinition:
        item = ToolDefinition(**kwargs)
        self.db.add(item)
        await self.db.flush()
        return item

    # ─── Action Policies ─────────────────────────────────────────

    async def get_action_policy(
        self,
        owner_id: str,
        scope_type: str,
        scope_id: str | None,
        action_key: str,
    ) -> ActionPolicy | None:
        """Get action policy for specific scope and action."""
        stmt = select(ActionPolicy).where(
            ActionPolicy.owner_id == owner_id,
            ActionPolicy.scope_type == scope_type,
            ActionPolicy.action_key == action_key,
        )
        if scope_id is not None:
            stmt = stmt.where(ActionPolicy.scope_id == scope_id)
        else:
            stmt = stmt.where(ActionPolicy.scope_id.is_(None))
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def create_action_policy(self, **kwargs: Any) -> ActionPolicy:
        item = ActionPolicy(**kwargs)
        self.db.add(item)
        await self.db.flush()
        return item

    # ─── Workflows ───────────────────────────────────────────────

    async def list_workflows(self, owner_id: str) -> list[WorkflowDefinition]:
        result = await self.db.execute(
            select(WorkflowDefinition)
            .where(
                (WorkflowDefinition.owner_id == owner_id)
                | (WorkflowDefinition.is_template.is_(True))
            )
            .order_by(WorkflowDefinition.name.asc())
        )
        return list(result.scalars().all())
