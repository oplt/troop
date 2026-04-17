from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.github.repository import GithubRepositoryMixin
from backend.modules.memory.repository import MemoryRepositoryMixin
from backend.modules.orchestration.models import (
    AgentMemoryEntry,
    AgentProfile,
    AgentProfileVersion,
    AgentTemplateCatalog,
    ModelCapability,
    ApprovalRequest,
    Brainstorm,
    BrainstormMessage,
    BrainstormParticipant,
    EpisodicArchiveManifest,
    EpisodicSearchIndex,
    EvalRecord,
    GithubConnection,
    GithubIssueLink,
    GithubRepository,
    GithubSyncEvent,
    MemoryIngestJob,
    OrchestratorProject,
    OrchestratorTask,
    ProjectAgentMembership,
    ProceduralPlaybook,
    ProjectDecision,
    ProjectDocument,
    ProjectDocumentChunk,
    normalize_embedding_for_vector,
    ProjectMilestone,
    ProjectRepositoryLink,
    ProviderConfig,
    RunEvent,
    SemanticMemoryEntry,
    SemanticMemoryLink,
    SkillPack,
    TaskArtifact,
    TaskComment,
    TaskDependency,
    TaskRun,
)
from backend.modules.projects.orchestration_repository import OrchestrationProjectsRepositoryMixin
from backend.modules.team.repository import TeamRepositoryMixin


class OrchestrationRepository(
    TeamRepositoryMixin,
    OrchestrationProjectsRepositoryMixin,
    GithubRepositoryMixin,
    MemoryRepositoryMixin,
):
    def __init__(self, db: AsyncSession):
        self.db = db

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
        result = await self.db.execute(select(AgentTemplateCatalog).order_by(AgentTemplateCatalog.name.asc()))
        return list(result.scalars().all())

    async def get_agent_template_by_slug(self, slug: str) -> AgentTemplateCatalog | None:
        result = await self.db.execute(select(AgentTemplateCatalog).where(AgentTemplateCatalog.slug == slug))
        return result.scalar_one_or_none()

    async def create_agent_template(self, **kwargs) -> AgentTemplateCatalog:
        item = AgentTemplateCatalog(**kwargs)
        self.db.add(item)
        await self.db.flush()
        return item

    async def list_projects(self, owner_id: str) -> list[OrchestratorProject]:
        result = await self.db.execute(
            select(OrchestratorProject)
            .where(OrchestratorProject.owner_id == owner_id)
            .order_by(OrchestratorProject.updated_at.desc())
        )
        return list(result.scalars().all())

    async def get_project(self, owner_id: str, project_id: str) -> OrchestratorProject | None:
        result = await self.db.execute(
            select(OrchestratorProject).where(
                OrchestratorProject.id == project_id,
                OrchestratorProject.owner_id == owner_id,
            )
        )
        return result.scalar_one_or_none()

    async def create_project(self, **kwargs) -> OrchestratorProject:
        item = OrchestratorProject(**kwargs)
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

    async def list_project_repositories(self, project_id: str) -> list[ProjectRepositoryLink]:
        result = await self.db.execute(
            select(ProjectRepositoryLink).where(ProjectRepositoryLink.project_id == project_id)
        )
        return list(result.scalars().all())

    async def create_project_repository(self, **kwargs) -> ProjectRepositoryLink:
        item = ProjectRepositoryLink(**kwargs)
        self.db.add(item)
        await self.db.flush()
        return item

    async def get_project_repository(self, project_id: str, repository_link_id: str) -> ProjectRepositoryLink | None:
        result = await self.db.execute(
            select(ProjectRepositoryLink).where(
                ProjectRepositoryLink.project_id == project_id,
                ProjectRepositoryLink.id == repository_link_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_tasks(self, project_id: str) -> list[OrchestratorTask]:
        result = await self.db.execute(
            select(OrchestratorTask)
            .where(OrchestratorTask.project_id == project_id)
            .order_by(OrchestratorTask.position.asc(), OrchestratorTask.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_task(self, project_id: str, task_id: str) -> OrchestratorTask | None:
        result = await self.db.execute(
            select(OrchestratorTask).where(
                OrchestratorTask.project_id == project_id,
                OrchestratorTask.id == task_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_task_by_id(self, task_id: str) -> OrchestratorTask | None:
        result = await self.db.execute(
            select(OrchestratorTask).where(OrchestratorTask.id == task_id)
        )
        return result.scalar_one_or_none()

    async def create_task(self, **kwargs) -> OrchestratorTask:
        item = OrchestratorTask(**kwargs)
        self.db.add(item)
        await self.db.flush()
        return item

    async def replace_task_dependencies(self, task_id: str, dependency_ids: Sequence[str]) -> None:
        existing = await self.db.execute(
            select(TaskDependency).where(TaskDependency.task_id == task_id)
        )
        for item in existing.scalars().all():
            await self.db.delete(item)
        for dependency_id in dependency_ids:
            self.db.add(TaskDependency(task_id=task_id, depends_on_task_id=dependency_id))
        await self.db.flush()

    async def list_task_dependencies(self, project_id: str) -> list[TaskDependency]:
        task_ids_query = select(OrchestratorTask.id).where(OrchestratorTask.project_id == project_id)
        result = await self.db.execute(
            select(TaskDependency).where(TaskDependency.task_id.in_(task_ids_query))
        )
        return list(result.scalars().all())

    async def list_task_dependencies_for_task(self, task_id: str) -> list[TaskDependency]:
        result = await self.db.execute(
            select(TaskDependency).where(TaskDependency.task_id == task_id)
        )
        return list(result.scalars().all())

    async def list_task_comments(self, task_id: str) -> list[TaskComment]:
        result = await self.db.execute(
            select(TaskComment)
            .where(TaskComment.task_id == task_id)
            .order_by(TaskComment.created_at.asc())
        )
        return list(result.scalars().all())

    async def create_task_comment(self, **kwargs) -> TaskComment:
        item = TaskComment(**kwargs)
        self.db.add(item)
        await self.db.flush()
        return item

    async def list_task_artifacts(self, task_id: str) -> list[TaskArtifact]:
        result = await self.db.execute(
            select(TaskArtifact)
            .where(TaskArtifact.task_id == task_id)
            .order_by(TaskArtifact.created_at.desc())
        )
        return list(result.scalars().all())

    async def create_task_artifact(self, **kwargs) -> TaskArtifact:
        item = TaskArtifact(**kwargs)
        self.db.add(item)
        await self.db.flush()
        return item

    async def get_next_task_position(self, project_id: str) -> int:
        value = await self.db.scalar(
            select(func.max(OrchestratorTask.position)).where(OrchestratorTask.project_id == project_id)
        )
        return int(value or -1) + 1

    async def create_run(self, **kwargs) -> TaskRun:
        item = TaskRun(**kwargs)
        self.db.add(item)
        await self.db.flush()
        return item

    async def get_run(self, owner_id: str, run_id: str) -> TaskRun | None:
        result = await self.db.execute(
            select(TaskRun)
            .join(OrchestratorProject, TaskRun.project_id == OrchestratorProject.id)
            .where(TaskRun.id == run_id, OrchestratorProject.owner_id == owner_id)
        )
        return result.scalar_one_or_none()

    async def list_runs(self, owner_id: str, project_id: str | None = None) -> list[TaskRun]:
        stmt = (
            select(TaskRun)
            .join(OrchestratorProject, TaskRun.project_id == OrchestratorProject.id)
            .where(OrchestratorProject.owner_id == owner_id)
        )
        if project_id:
            stmt = stmt.where(TaskRun.project_id == project_id)
        result = await self.db.execute(stmt.order_by(TaskRun.created_at.desc()))
        return list(result.scalars().all())

    async def sum_token_usage_for_agent(self, owner_id: str, agent_id: str, since: datetime) -> int:
        stmt = (
            select(func.coalesce(func.sum(TaskRun.token_total), 0))
            .select_from(TaskRun)
            .join(OrchestratorProject, TaskRun.project_id == OrchestratorProject.id)
            .where(
                OrchestratorProject.owner_id == owner_id,
                or_(TaskRun.worker_agent_id == agent_id, TaskRun.orchestrator_agent_id == agent_id),
                TaskRun.created_at >= since,
            )
        )
        result = await self.db.execute(stmt)
        return int(result.scalar_one() or 0)

    async def sum_estimated_cost_micros_for_agent(self, owner_id: str, agent_id: str, since: datetime) -> int:
        stmt = (
            select(func.coalesce(func.sum(TaskRun.estimated_cost_micros), 0))
            .select_from(TaskRun)
            .join(OrchestratorProject, TaskRun.project_id == OrchestratorProject.id)
            .where(
                OrchestratorProject.owner_id == owner_id,
                or_(TaskRun.worker_agent_id == agent_id, TaskRun.orchestrator_agent_id == agent_id),
                TaskRun.created_at >= since,
            )
        )
        result = await self.db.execute(stmt)
        return int(result.scalar_one() or 0)

    async def sum_run_event_cost_micros_for_run(self, run_id: str) -> int:
        stmt = select(func.coalesce(func.sum(RunEvent.cost_usd_micros), 0)).where(RunEvent.run_id == run_id)
        result = await self.db.execute(stmt)
        return int(result.scalar_one() or 0)

    async def map_github_issue_summaries_by_link_id(
        self, link_ids: Sequence[str]
    ) -> dict[str, dict[str, object | None]]:
        unique = [item for item in dict.fromkeys(link_ids) if item]
        if not unique:
            return {}
        stmt = (
            select(
                GithubIssueLink.id,
                GithubIssueLink.issue_number,
                GithubIssueLink.issue_url,
                GithubRepository.full_name,
            )
            .join(GithubRepository, GithubIssueLink.repository_id == GithubRepository.id)
            .where(GithubIssueLink.id.in_(unique))
        )
        result = await self.db.execute(stmt)
        out: dict[str, dict[str, object | None]] = {}
        for link_id, issue_number, issue_url, full_name in result.all():
            url = issue_url
            if not url and full_name and issue_number is not None:
                url = f"https://github.com/{full_name}/issues/{int(issue_number)}"
            out[str(link_id)] = {
                "issue_number": int(issue_number) if issue_number is not None else None,
                "issue_url": str(url) if url else None,
                "repository_full_name": str(full_name) if full_name else None,
            }
        return out

    async def count_active_runs_by_worker(self, project_id: str, agent_ids: Sequence[str]) -> dict[str, int]:
        if not agent_ids:
            return {}
        result = await self.db.execute(
            select(TaskRun.worker_agent_id, func.count(TaskRun.id))
            .where(
                TaskRun.project_id == project_id,
                TaskRun.worker_agent_id.in_(agent_ids),
                TaskRun.status.in_(["queued", "in_progress", "blocked"]),
            )
            .group_by(TaskRun.worker_agent_id)
        )
        return {agent_id: count for agent_id, count in result.all() if agent_id}

    async def create_run_event(self, **kwargs) -> RunEvent:
        item = RunEvent(**kwargs)
        self.db.add(item)
        await self.db.flush()
        return item

    async def list_run_events(self, run_id: str) -> list[RunEvent]:
        result = await self.db.execute(
            select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.created_at.asc())
        )
        return list(result.scalars().all())

    async def list_run_events_since(
        self, run_id: str, *, created_after: datetime | None, limit: int = 200
    ) -> list[RunEvent]:
        stmt = select(RunEvent).where(RunEvent.run_id == run_id)
        if created_after is not None:
            stmt = stmt.where(RunEvent.created_at > created_after)
        result = await self.db.execute(
            stmt.order_by(RunEvent.created_at.asc(), RunEvent.id.asc()).limit(limit)
        )
        return list(result.scalars().all())

    async def get_run_for_worker(self, run_id: str) -> TaskRun | None:
        result = await self.db.execute(select(TaskRun).where(TaskRun.id == run_id))
        return result.scalar_one_or_none()

    async def list_providers(self, owner_id: str, project_id: str | None = None) -> list[ProviderConfig]:
        stmt = select(ProviderConfig).where(ProviderConfig.owner_id == owner_id)
        if project_id is None:
            stmt = stmt.where(ProviderConfig.project_id.is_(None))
        else:
            stmt = stmt.where(or_(ProviderConfig.project_id == project_id, ProviderConfig.project_id.is_(None)))
        result = await self.db.execute(stmt.order_by(ProviderConfig.is_default.desc(), ProviderConfig.updated_at.desc()))
        return list(result.scalars().all())

    async def get_provider(self, owner_id: str, provider_id: str) -> ProviderConfig | None:
        result = await self.db.execute(
            select(ProviderConfig).where(
                ProviderConfig.owner_id == owner_id,
                ProviderConfig.id == provider_id,
            )
        )
        return result.scalar_one_or_none()

    async def create_provider(self, **kwargs) -> ProviderConfig:
        item = ProviderConfig(**kwargs)
        self.db.add(item)
        await self.db.flush()
        return item

    async def list_all_providers(self, *, enabled_only: bool = True) -> list[ProviderConfig]:
        stmt = select(ProviderConfig)
        if enabled_only:
            stmt = stmt.where(ProviderConfig.is_enabled.is_(True))
        result = await self.db.execute(stmt.order_by(ProviderConfig.updated_at.desc()))
        return list(result.scalars().all())

    async def list_model_capabilities(
        self, provider_type: str | None = None, *, active_only: bool = True
    ) -> list[ModelCapability]:
        stmt = select(ModelCapability)
        if provider_type:
            stmt = stmt.where(ModelCapability.provider_type == provider_type)
        if active_only:
            stmt = stmt.where(ModelCapability.is_active.is_(True))
        result = await self.db.execute(
            stmt.order_by(ModelCapability.provider_type.asc(), ModelCapability.model_slug.asc())
        )
        return list(result.scalars().all())

    async def get_model_capability(
        self, model_slug: str, provider_type: str | None = None
    ) -> ModelCapability | None:
        stmt = select(ModelCapability).where(ModelCapability.model_slug == model_slug)
        if provider_type:
            stmt = stmt.where(ModelCapability.provider_type == provider_type)
        result = await self.db.execute(stmt.order_by(ModelCapability.updated_at.desc()))
        return result.scalars().first()

    async def create_model_capability(self, **kwargs) -> ModelCapability:
        item = ModelCapability(**kwargs)
        self.db.add(item)
        await self.db.flush()
        return item

    async def create_brainstorm(self, **kwargs) -> Brainstorm:
        item = Brainstorm(**kwargs)
        self.db.add(item)
        await self.db.flush()
        return item

    async def get_brainstorm(self, owner_id: str, brainstorm_id: str) -> Brainstorm | None:
        result = await self.db.execute(
            select(Brainstorm)
            .join(OrchestratorProject, Brainstorm.project_id == OrchestratorProject.id)
            .where(Brainstorm.id == brainstorm_id, OrchestratorProject.owner_id == owner_id)
        )
        return result.scalar_one_or_none()

    async def list_brainstorms(self, owner_id: str, project_id: str | None = None) -> list[Brainstorm]:
        stmt = (
            select(Brainstorm)
            .join(OrchestratorProject, Brainstorm.project_id == OrchestratorProject.id)
            .where(OrchestratorProject.owner_id == owner_id)
        )
        if project_id:
            stmt = stmt.where(Brainstorm.project_id == project_id)
        result = await self.db.execute(stmt.order_by(Brainstorm.updated_at.desc()))
        return list(result.scalars().all())

    async def list_brainstorm_participants(self, brainstorm_id: str) -> list[BrainstormParticipant]:
        result = await self.db.execute(
            select(BrainstormParticipant)
            .where(BrainstormParticipant.brainstorm_id == brainstorm_id)
            .order_by(BrainstormParticipant.order_index.asc())
        )
        return list(result.scalars().all())

    async def count_brainstorm_participants(self, brainstorm_ids: Sequence[str]) -> dict[str, int]:
        if not brainstorm_ids:
            return {}
        result = await self.db.execute(
            select(BrainstormParticipant.brainstorm_id, func.count(BrainstormParticipant.id))
            .where(BrainstormParticipant.brainstorm_id.in_(brainstorm_ids))
            .group_by(BrainstormParticipant.brainstorm_id)
        )
        return {brainstorm_id: count for brainstorm_id, count in result.all()}

    async def create_brainstorm_participant(self, **kwargs) -> BrainstormParticipant:
        item = BrainstormParticipant(**kwargs)
        self.db.add(item)
        await self.db.flush()
        return item

    async def list_brainstorm_messages(self, brainstorm_id: str) -> list[BrainstormMessage]:
        result = await self.db.execute(
            select(BrainstormMessage)
            .where(BrainstormMessage.brainstorm_id == brainstorm_id)
            .order_by(BrainstormMessage.round_number.asc(), BrainstormMessage.created_at.asc())
        )
        return list(result.scalars().all())

    async def create_brainstorm_message(self, **kwargs) -> BrainstormMessage:
        item = BrainstormMessage(**kwargs)
        self.db.add(item)
        await self.db.flush()
        return item

    async def create_project_decision(self, **kwargs) -> ProjectDecision:
        item = ProjectDecision(**kwargs)
        self.db.add(item)
        await self.db.flush()
        return item

    async def list_project_decisions(self, project_id: str) -> list[ProjectDecision]:
        result = await self.db.execute(
            select(ProjectDecision)
            .where(ProjectDecision.project_id == project_id)
            .order_by(ProjectDecision.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_project_milestones(self, project_id: str) -> list[ProjectMilestone]:
        result = await self.db.execute(
            select(ProjectMilestone)
            .where(ProjectMilestone.project_id == project_id)
            .order_by(ProjectMilestone.position, ProjectMilestone.created_at)
        )
        return list(result.scalars().all())

    async def create_project_milestone(self, **kwargs) -> ProjectMilestone:
        item = ProjectMilestone(**kwargs)
        self.db.add(item)
        await self.db.flush()
        return item

    async def update_project_milestone(self, milestone_id: str, updates: dict) -> ProjectMilestone | None:
        result = await self.db.execute(
            select(ProjectMilestone).where(ProjectMilestone.id == milestone_id)
        )
        item = result.scalar_one_or_none()
        if not item:
            return None
        for k, v in updates.items():
            setattr(item, k, v)
        await self.db.flush()
        return item

    async def list_subtasks(self, parent_task_id: str) -> list[OrchestratorTask]:
        result = await self.db.execute(
            select(OrchestratorTask)
            .where(OrchestratorTask.parent_task_id == parent_task_id)
            .order_by(OrchestratorTask.position)
        )
        return list(result.scalars().all())

    async def create_github_connection(self, **kwargs) -> GithubConnection:
        item = GithubConnection(**kwargs)
        self.db.add(item)
        await self.db.flush()
        return item

    async def list_github_connections(self, owner_id: str) -> list[GithubConnection]:
        result = await self.db.execute(
            select(GithubConnection)
            .where(GithubConnection.owner_id == owner_id)
            .order_by(GithubConnection.updated_at.desc())
        )
        return list(result.scalars().all())

    async def get_github_connection(self, owner_id: str, connection_id: str) -> GithubConnection | None:
        result = await self.db.execute(
            select(GithubConnection).where(
                GithubConnection.owner_id == owner_id,
                GithubConnection.id == connection_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_github_connection_by_installation(
        self, owner_id: str, installation_id: int
    ) -> GithubConnection | None:
        result = await self.db.execute(
            select(GithubConnection).where(
                GithubConnection.owner_id == owner_id,
                GithubConnection.metadata_json["installation_id"].as_integer() == installation_id,
            )
        )
        return result.scalar_one_or_none()

    async def create_github_repository(self, **kwargs) -> GithubRepository:
        item = GithubRepository(**kwargs)
        self.db.add(item)
        await self.db.flush()
        return item

    async def list_github_repositories(self, owner_id: str) -> list[GithubRepository]:
        result = await self.db.execute(
            select(GithubRepository)
            .join(GithubConnection, GithubRepository.connection_id == GithubConnection.id)
            .where(GithubConnection.owner_id == owner_id)
            .order_by(GithubRepository.full_name.asc())
        )
        return list(result.scalars().all())

    async def get_github_repository(self, owner_id: str, repository_id: str) -> GithubRepository | None:
        result = await self.db.execute(
            select(GithubRepository)
            .join(GithubConnection, GithubRepository.connection_id == GithubConnection.id)
            .where(
                GithubRepository.id == repository_id,
                GithubConnection.owner_id == owner_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_github_repository_by_full_name(self, full_name: str) -> GithubRepository | None:
        result = await self.db.execute(
            select(GithubRepository).where(GithubRepository.full_name == full_name)
        )
        return result.scalar_one_or_none()

    async def get_issue_link_by_repo_and_number(
        self, repository_id: str, issue_number: int
    ) -> GithubIssueLink | None:
        result = await self.db.execute(
            select(GithubIssueLink).where(
                GithubIssueLink.repository_id == repository_id,
                GithubIssueLink.issue_number == issue_number,
            )
        )
        return result.scalar_one_or_none()

    async def create_issue_link(self, **kwargs) -> GithubIssueLink:
        item = GithubIssueLink(**kwargs)
        self.db.add(item)
        await self.db.flush()
        return item

    async def list_issue_links(self, owner_id: str, project_id: str | None = None) -> list[GithubIssueLink]:
        stmt = (
            select(GithubIssueLink)
            .join(GithubRepository, GithubIssueLink.repository_id == GithubRepository.id)
            .join(GithubConnection, GithubRepository.connection_id == GithubConnection.id)
            .where(GithubConnection.owner_id == owner_id)
        )
        if project_id:
            stmt = stmt.where(GithubRepository.project_id == project_id)
        result = await self.db.execute(stmt.order_by(GithubIssueLink.updated_at.desc()))
        return list(result.scalars().all())

    async def list_issue_links_stale(self, *, older_than: datetime, limit: int = 40) -> list[GithubIssueLink]:
        stmt = (
            select(GithubIssueLink)
            .join(GithubRepository, GithubIssueLink.repository_id == GithubRepository.id)
            .join(GithubConnection, GithubRepository.connection_id == GithubConnection.id)
            .where(
                GithubConnection.is_active.is_(True),
                or_(GithubIssueLink.last_synced_at.is_(None), GithubIssueLink.last_synced_at < older_than),
            )
            .order_by(GithubIssueLink.last_synced_at.asc().nullsfirst())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_issue_link(self, owner_id: str, issue_link_id: str) -> GithubIssueLink | None:
        result = await self.db.execute(
            select(GithubIssueLink)
            .join(GithubRepository, GithubIssueLink.repository_id == GithubRepository.id)
            .join(GithubConnection, GithubRepository.connection_id == GithubConnection.id)
            .where(GithubIssueLink.id == issue_link_id, GithubConnection.owner_id == owner_id)
        )
        return result.scalar_one_or_none()

    async def create_sync_event(self, **kwargs) -> GithubSyncEvent:
        item = GithubSyncEvent(**kwargs)
        self.db.add(item)
        await self.db.flush()
        return item

    async def get_sync_event(self, sync_event_id: str) -> GithubSyncEvent | None:
        result = await self.db.execute(
            select(GithubSyncEvent).where(GithubSyncEvent.id == sync_event_id)
        )
        return result.scalar_one_or_none()

    async def list_sync_events(self, owner_id: str, project_id: str | None = None) -> list[GithubSyncEvent]:
        stmt = (
            select(GithubSyncEvent)
            .join(GithubRepository, GithubSyncEvent.repository_id == GithubRepository.id, isouter=True)
            .join(GithubConnection, GithubRepository.connection_id == GithubConnection.id, isouter=True)
            .where(or_(GithubConnection.owner_id == owner_id, GithubSyncEvent.repository_id.is_(None)))
        )
        if project_id:
            stmt = stmt.where(GithubRepository.project_id == project_id)
        result = await self.db.execute(stmt.order_by(GithubSyncEvent.created_at.desc()))
        return list(result.scalars().all())

    async def list_sync_events_for_task(self, task_id: str) -> list[GithubSyncEvent]:
        stmt = (
            select(GithubSyncEvent)
            .join(GithubIssueLink, GithubSyncEvent.issue_link_id == GithubIssueLink.id)
            .where(GithubIssueLink.task_id == task_id)
            .order_by(GithubSyncEvent.created_at.asc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_tool_failure_payloads_for_owner(
        self, owner_id: str, since: datetime
    ) -> list[dict[str, Any]]:
        stmt = (
            select(RunEvent.payload_json)
            .join(TaskRun, RunEvent.run_id == TaskRun.id)
            .join(OrchestratorProject, TaskRun.project_id == OrchestratorProject.id)
            .where(
                OrchestratorProject.owner_id == owner_id,
                RunEvent.created_at >= since,
                RunEvent.event_type == "tool_call_failed",
            )
        )
        result = await self.db.execute(stmt)
        return [row[0] if isinstance(row[0], dict) else {} for row in result.all()]

    async def create_document(self, **kwargs) -> ProjectDocument:
        item = ProjectDocument(**kwargs)
        self.db.add(item)
        await self.db.flush()
        return item

    async def list_documents(self, project_id: str, task_id: str | None = None) -> list[ProjectDocument]:
        stmt = select(ProjectDocument).where(
            ProjectDocument.project_id == project_id,
            ProjectDocument.deleted_at.is_(None),
        )
        if task_id is not None:
            stmt = stmt.where(
                or_(ProjectDocument.task_id == task_id, ProjectDocument.task_id.is_(None))
            )
        result = await self.db.execute(stmt.order_by(ProjectDocument.created_at.desc()))
        return list(result.scalars().all())

    async def get_document(self, project_id: str, document_id: str) -> ProjectDocument | None:
        result = await self.db.execute(
            select(ProjectDocument).where(
                ProjectDocument.project_id == project_id,
                ProjectDocument.id == document_id,
            )
        )
        return result.scalar_one_or_none()

    async def replace_document_chunks(
        self,
        document: ProjectDocument,
        chunks: list[tuple[int, str, int, list[float], dict]],
    ) -> None:
        result = await self.db.execute(
            select(ProjectDocumentChunk).where(ProjectDocumentChunk.project_document_id == document.id)
        )
        for item in result.scalars().all():
            await self.db.delete(item)
        await self.db.flush()
        for chunk_index, content, token_count, embedding, metadata in chunks:
            ev = normalize_embedding_for_vector(embedding)
            self.db.add(
                ProjectDocumentChunk(
                    project_document_id=document.id,
                    project_id=document.project_id,
                    task_id=document.task_id,
                    chunk_index=chunk_index,
                    content=content,
                    token_count=token_count,
                    embedding_json=embedding,
                    embedding_vector=ev,
                    metadata_json=metadata,
                )
            )
        await self.db.flush()

    async def search_document_chunks_by_vector(
        self,
        project_id: str,
        query_vec: list[float],
        *,
        task_id: str | None,
        source_kind: str | None,
        top_k: int,
    ) -> list[dict]:
        qv = normalize_embedding_for_vector(query_vec)
        literal = "[" + ",".join(str(float(x)) for x in qv) + "]"
        clauses = [
            "c.project_id = :pid",
            "c.deleted_at IS NULL",
            "d.deleted_at IS NULL",
            "c.embedding_vector IS NOT NULL",
        ]
        params: dict[str, str | int] = {"pid": project_id, "qv": literal, "lim": max(1, min(top_k, 20))}
        if task_id is not None:
            clauses.append("(c.task_id = :tid OR c.task_id IS NULL)")
            params["tid"] = task_id
        if source_kind:
            clauses.append("c.metadata_json->>'source_kind' = :sk")
            params["sk"] = source_kind
        where_sql = " AND ".join(clauses)
        sql = text(
            f"""
            SELECT c.id AS chunk_id, c.project_document_id, c.chunk_index, c.content, c.metadata_json,
                   d.filename,
                   1 - (c.embedding_vector <=> CAST(:qv AS vector)) AS score
            FROM project_document_chunks c
            INNER JOIN project_documents d ON d.id = c.project_document_id
            WHERE {where_sql}
            ORDER BY c.embedding_vector <=> CAST(:qv AS vector)
            LIMIT :lim
            """
        )
        result = await self.db.execute(sql, params)
        return [dict(r) for r in result.mappings().all()]

    async def list_document_chunks(
        self,
        project_id: str,
        *,
        task_id: str | None = None,
        source_kind: str | None = None,
    ) -> list[ProjectDocumentChunk]:
        stmt = (
            select(ProjectDocumentChunk)
            .join(ProjectDocument, ProjectDocumentChunk.project_document_id == ProjectDocument.id)
            .where(
                ProjectDocumentChunk.project_id == project_id,
                ProjectDocumentChunk.deleted_at.is_(None),
                ProjectDocument.deleted_at.is_(None),
            )
        )
        if task_id is not None:
            stmt = stmt.where(
                or_(ProjectDocumentChunk.task_id == task_id, ProjectDocumentChunk.task_id.is_(None))
            )
        if source_kind:
            stmt = stmt.where(
                ProjectDocumentChunk.metadata_json["source_kind"].as_string() == source_kind
            )
        result = await self.db.execute(
            stmt.order_by(ProjectDocumentChunk.project_document_id.asc(), ProjectDocumentChunk.chunk_index.asc())
        )
        return list(result.scalars().all())

    async def create_agent_memory(self, **kwargs) -> AgentMemoryEntry:
        item = AgentMemoryEntry(**kwargs)
        self.db.add(item)
        await self.db.flush()
        return item

    async def list_agent_memory(
        self,
        owner_id: str,
        *,
        project_id: str | None = None,
        agent_id: str | None = None,
        status: str | None = None,
    ) -> list[AgentMemoryEntry]:
        stmt = select(AgentMemoryEntry).where(
            AgentMemoryEntry.owner_id == owner_id,
            AgentMemoryEntry.deleted_at.is_(None),
        )
        if project_id is not None:
            stmt = stmt.where(AgentMemoryEntry.project_id == project_id)
        if agent_id is not None:
            stmt = stmt.where(AgentMemoryEntry.agent_id == agent_id)
        if status is not None:
            stmt = stmt.where(AgentMemoryEntry.status == status)
        result = await self.db.execute(stmt.order_by(AgentMemoryEntry.updated_at.desc()))
        return list(result.scalars().all())

    async def get_agent_memory(self, owner_id: str, memory_id: str) -> AgentMemoryEntry | None:
        result = await self.db.execute(
            select(AgentMemoryEntry).where(
                AgentMemoryEntry.owner_id == owner_id,
                AgentMemoryEntry.id == memory_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_latest_run_for_task(
        self, project_id: str, task_id: str, *, exclude_run_id: str | None = None
    ) -> TaskRun | None:
        stmt = (
            select(TaskRun)
            .where(TaskRun.project_id == project_id, TaskRun.task_id == task_id)
            .order_by(TaskRun.created_at.desc())
        )
        if exclude_run_id:
            stmt = stmt.where(TaskRun.id != exclude_run_id)
        result = await self.db.execute(stmt.limit(1))
        return result.scalars().first()

    async def list_active_runs_for_task(self, project_id: str, task_id: str) -> list[TaskRun]:
        result = await self.db.execute(
            select(TaskRun)
            .where(
                TaskRun.project_id == project_id,
                TaskRun.task_id == task_id,
                TaskRun.status.in_(("queued", "in_progress", "blocked")),
            )
            .order_by(TaskRun.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_pending_approvals_for_task(
        self, owner_id: str, project_id: str, task_id: str
    ) -> list[ApprovalRequest]:
        """Pending approvals for this task (direct task_id or GitHub issue link to task)."""
        by_task = (
            select(ApprovalRequest)
            .join(OrchestratorProject, ApprovalRequest.project_id == OrchestratorProject.id)
            .where(
                ApprovalRequest.status == "pending",
                ApprovalRequest.task_id == task_id,
                ApprovalRequest.project_id == project_id,
                OrchestratorProject.owner_id == owner_id,
            )
        )
        by_link = (
            select(ApprovalRequest)
            .join(GithubIssueLink, ApprovalRequest.issue_link_id == GithubIssueLink.id)
            .join(GithubRepository, GithubIssueLink.repository_id == GithubRepository.id)
            .join(GithubConnection, GithubRepository.connection_id == GithubConnection.id)
            .where(
                ApprovalRequest.status == "pending",
                GithubIssueLink.task_id == task_id,
                GithubConnection.owner_id == owner_id,
            )
        )
        rows_by_task = list((await self.db.execute(by_task)).scalars().all())
        rows_by_link = list((await self.db.execute(by_link)).scalars().all())
        seen: set[str] = set()
        merged: list[ApprovalRequest] = []
        for row in rows_by_task + rows_by_link:
            if row.id in seen:
                continue
            seen.add(row.id)
            merged.append(row)
        merged.sort(key=lambda a: a.created_at, reverse=True)
        return merged

    async def list_pending_approvals_for_run(self, owner_id: str, run_id: str) -> list[ApprovalRequest]:
        result = await self.db.execute(
            select(ApprovalRequest)
            .join(TaskRun, ApprovalRequest.run_id == TaskRun.id)
            .join(OrchestratorProject, TaskRun.project_id == OrchestratorProject.id)
            .where(
                ApprovalRequest.status == "pending",
                ApprovalRequest.run_id == run_id,
                OrchestratorProject.owner_id == owner_id,
            )
            .order_by(ApprovalRequest.created_at.desc())
        )
        return list(result.scalars().all())

    async def create_approval(self, **kwargs) -> ApprovalRequest:
        item = ApprovalRequest(**kwargs)
        self.db.add(item)
        await self.db.flush()
        return item

    async def list_approvals(self, owner_id: str, status: str | None = None) -> list[ApprovalRequest]:
        stmt = (
            select(ApprovalRequest)
            .join(OrchestratorProject, ApprovalRequest.project_id == OrchestratorProject.id, isouter=True)
            .where(or_(OrchestratorProject.owner_id == owner_id, ApprovalRequest.project_id.is_(None)))
        )
        if status:
            stmt = stmt.where(ApprovalRequest.status == status)
        result = await self.db.execute(stmt.order_by(ApprovalRequest.created_at.desc()))
        return list(result.scalars().all())

    async def get_approval(self, owner_id: str, approval_id: str) -> ApprovalRequest | None:
        result = await self.db.execute(
            select(ApprovalRequest)
            .join(OrchestratorProject, ApprovalRequest.project_id == OrchestratorProject.id, isouter=True)
            .where(
                ApprovalRequest.id == approval_id,
                or_(OrchestratorProject.owner_id == owner_id, ApprovalRequest.project_id.is_(None)),
            )
        )
        return result.scalar_one_or_none()

    async def list_eval_records(self, project_id: str) -> list[EvalRecord]:
        result = await self.db.execute(
            select(EvalRecord).where(EvalRecord.project_id == project_id).order_by(EvalRecord.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_eval_record(self, project_id: str, eval_id: str) -> EvalRecord | None:
        result = await self.db.execute(
            select(EvalRecord).where(EvalRecord.id == eval_id, EvalRecord.project_id == project_id)
        )
        return result.scalar_one_or_none()

    async def create_eval_record(self, **kwargs) -> EvalRecord:
        item = EvalRecord(**kwargs)
        self.db.add(item)
        await self.db.flush()
        return item

    async def aggregate_run_costs(
        self,
        owner_id: str,
        *,
        since: datetime,
    ) -> dict[str, list | int | float]:
        """Roll up task_runs for projects owned by owner_id since ``since``."""
        project_stmt = select(OrchestratorProject.id, OrchestratorProject.name).where(
            OrchestratorProject.owner_id == owner_id
        )
        proj_result = await self.db.execute(project_stmt)
        projects = {row[0]: row[1] for row in proj_result.all()}
        if not projects:
            return {
                "by_project": [],
                "by_agent": [],
                "by_provider": [],
                "most_expensive_runs": [],
                "total_cost_micros": 0,
                "total_tokens": 0,
            }

        project_ids = list(projects.keys())
        base_filter = TaskRun.project_id.in_(project_ids) & (TaskRun.created_at >= since)

        by_proj = await self.db.execute(
            select(
                TaskRun.project_id,
                func.coalesce(func.sum(TaskRun.estimated_cost_micros), 0),
                func.coalesce(func.sum(TaskRun.token_total), 0),
                func.count(TaskRun.id),
            )
            .where(base_filter)
            .group_by(TaskRun.project_id)
        )
        by_project = [
            {
                "project_id": pid,
                "name": projects.get(pid, "Unknown"),
                "cost_usd": int(cost) / 1_000_000,
                "tokens": int(tokens),
                "runs": int(runs),
            }
            for pid, cost, tokens, runs in by_proj.all()
        ]

        agent_key = func.coalesce(TaskRun.worker_agent_id, TaskRun.orchestrator_agent_id)
        by_ag = await self.db.execute(
            select(
                agent_key,
                func.coalesce(func.sum(TaskRun.estimated_cost_micros), 0),
                func.coalesce(func.sum(TaskRun.token_total), 0),
                func.count(TaskRun.id),
            )
            .where(base_filter, agent_key.isnot(None))
            .group_by(agent_key)
        )
        by_agent = [
            {
                "agent_id": aid,
                "name": None,
                "cost_usd": int(cost) / 1_000_000,
                "tokens": int(tokens),
                "runs": int(runs),
            }
            for aid, cost, tokens, runs in by_ag.all()
        ]

        by_prov = await self.db.execute(
            select(
                TaskRun.provider_config_id,
                func.coalesce(func.sum(TaskRun.estimated_cost_micros), 0),
                func.coalesce(func.sum(TaskRun.token_total), 0),
                func.count(TaskRun.id),
            )
            .where(base_filter, TaskRun.provider_config_id.isnot(None))
            .group_by(TaskRun.provider_config_id)
        )
        prov_rows = by_prov.all()
        provider_names: dict[str, str] = {}
        if prov_rows:
            pids = [row[0] for row in prov_rows]
            pr = await self.db.execute(select(ProviderConfig).where(ProviderConfig.id.in_(pids)))
            for p in pr.scalars().all():
                provider_names[p.id] = p.name
        by_provider = [
            {
                "provider_id": pid,
                "name": provider_names.get(pid, "Provider"),
                "cost_usd": int(cost) / 1_000_000,
                "tokens": int(tokens),
                "runs": int(runs),
            }
            for pid, cost, tokens, runs in prov_rows
        ]

        top_stmt = (
            select(TaskRun)
            .where(base_filter)
            .order_by(TaskRun.estimated_cost_micros.desc())
            .limit(20)
        )
        top_result = await self.db.execute(top_stmt)
        most_expensive = []
        for tr in top_result.scalars().all():
            most_expensive.append(
                {
                    "id": tr.id,
                    "project_id": tr.project_id,
                    "model_name": tr.model_name,
                    "cost_usd": tr.estimated_cost_micros / 1_000_000,
                    "tokens": tr.token_total,
                    "status": tr.status,
                    "created_at": tr.created_at,
                }
            )

        tot = await self.db.execute(
            select(
                func.coalesce(func.sum(TaskRun.estimated_cost_micros), 0),
                func.coalesce(func.sum(TaskRun.token_total), 0),
            ).where(base_filter)
        )
        total_cost_micros, total_tokens = tot.one()

        return {
            "by_project": by_project,
            "by_agent": by_agent,
            "by_provider": by_provider,
            "most_expensive_runs": most_expensive,
            "total_cost_micros": int(total_cost_micros or 0),
            "total_tokens": int(total_tokens or 0),
        }

    async def summarize_portfolio_for_owner(self, owner_id: str) -> list[dict[str, Any]]:
        """Per-project counts for multi-repo / portfolio dashboards (owner-scoped)."""
        pr = await self.db.execute(
            select(OrchestratorProject.id, OrchestratorProject.name, OrchestratorProject.slug).where(
                OrchestratorProject.owner_id == owner_id
            )
        )
        rows = pr.all()
        if not rows:
            return []
        project_ids = [r[0] for r in rows]
        active_runs: dict[str, int] = {}
        if project_ids:
            ar = await self.db.execute(
                select(TaskRun.project_id, func.count())
                .where(
                    TaskRun.project_id.in_(project_ids),
                    TaskRun.status.in_(["queued", "in_progress", "blocked"]),
                )
                .group_by(TaskRun.project_id)
            )
            active_runs = {str(pid): int(c or 0) for pid, c in ar.all()}
        open_tasks: dict[str, int] = {}
        if project_ids:
            ot = await self.db.execute(
                select(OrchestratorTask.project_id, func.count())
                .where(
                    OrchestratorTask.project_id.in_(project_ids),
                    ~OrchestratorTask.status.in_(["completed", "archived", "synced_to_github"]),
                )
                .group_by(OrchestratorTask.project_id)
            )
            open_tasks = {str(pid): int(c or 0) for pid, c in ot.all()}
        repo_links: dict[str, int] = {}
        if project_ids:
            rl = await self.db.execute(
                select(ProjectRepositoryLink.project_id, func.count())
                .where(ProjectRepositoryLink.project_id.in_(project_ids))
                .group_by(ProjectRepositoryLink.project_id)
            )
            repo_links = {str(pid): int(c or 0) for pid, c in rl.all()}
        return [
            {
                "project_id": pid,
                "name": name,
                "slug": slug,
                "active_runs": active_runs.get(pid, 0),
                "open_tasks": open_tasks.get(pid, 0),
                "repository_links": repo_links.get(pid, 0),
            }
            for pid, name, slug in rows
        ]

    async def aggregate_run_events_by_type_for_owner(
        self, owner_id: str, since: datetime
    ) -> list[tuple[str, int]]:
        stmt = (
            select(RunEvent.event_type, func.count(RunEvent.id))
            .join(TaskRun, RunEvent.run_id == TaskRun.id)
            .join(OrchestratorProject, TaskRun.project_id == OrchestratorProject.id)
            .where(OrchestratorProject.owner_id == owner_id, RunEvent.created_at >= since)
            .group_by(RunEvent.event_type)
            .order_by(func.count(RunEvent.id).desc())
        )
        result = await self.db.execute(stmt)
        return [(str(et), int(c or 0)) for et, c in result.all()]

    async def list_all_orchestrator_projects(self) -> list[OrchestratorProject]:
        result = await self.db.execute(
            select(OrchestratorProject).order_by(OrchestratorProject.created_at.asc())
        )
        return list(result.scalars().all())

    async def task_has_active_run(self, project_id: str, task_id: str) -> bool:
        result = await self.db.execute(
            select(TaskRun.id)
            .where(
                TaskRun.project_id == project_id,
                TaskRun.task_id == task_id,
                TaskRun.status.in_(["queued", "in_progress"]),
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def count_pending_approvals_for_task(
        self, project_id: str, task_id: str, approval_type: str
    ) -> int:
        result = await self.db.execute(
            select(func.count())
            .select_from(ApprovalRequest)
            .where(
                ApprovalRequest.project_id == project_id,
                ApprovalRequest.task_id == task_id,
                ApprovalRequest.approval_type == approval_type,
                ApprovalRequest.status == "pending",
            )
        )
        return int(result.scalar() or 0)

    async def create_semantic_memory_entry(self, **kwargs: Any) -> SemanticMemoryEntry:
        item = SemanticMemoryEntry(**kwargs)
        self.db.add(item)
        await self.db.flush()
        return item

    async def get_semantic_memory_entry(self, owner_id: str, entry_id: str) -> SemanticMemoryEntry | None:
        result = await self.db.execute(
            select(SemanticMemoryEntry).where(
                SemanticMemoryEntry.id == entry_id,
                SemanticMemoryEntry.owner_id == owner_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_semantic_memory_entries(
        self,
        owner_id: str,
        *,
        project_id: str | None = None,
        entry_type: str | None = None,
        namespace_prefix: str | None = None,
        search: str | None = None,
        limit: int = 100,
    ) -> list[SemanticMemoryEntry]:
        stmt = select(SemanticMemoryEntry).where(SemanticMemoryEntry.owner_id == owner_id)
        if project_id is not None:
            stmt = stmt.where(SemanticMemoryEntry.project_id == project_id)
        if entry_type:
            stmt = stmt.where(SemanticMemoryEntry.entry_type == entry_type)
        if namespace_prefix:
            stmt = stmt.where(SemanticMemoryEntry.namespace.startswith(namespace_prefix))
        if search:
            q = f"%{search}%"
            stmt = stmt.where(
                or_(
                    SemanticMemoryEntry.title.ilike(q),
                    SemanticMemoryEntry.body.ilike(q),
                )
            )
        cap = max(1, min(limit, 500))
        result = await self.db.execute(
            stmt.order_by(SemanticMemoryEntry.updated_at.desc()).limit(cap)
        )
        return list(result.scalars().all())

    async def find_semantic_by_decision_id(
        self, owner_id: str, project_id: str, decision_id: str
    ) -> SemanticMemoryEntry | None:
        r = await self.db.execute(
            select(SemanticMemoryEntry).where(
                SemanticMemoryEntry.owner_id == owner_id,
                SemanticMemoryEntry.project_id == project_id,
                SemanticMemoryEntry.provenance_json["decision_id"].as_string() == decision_id,
            )
        )
        return r.scalar_one_or_none()

    async def find_semantic_by_agent_memory_id(
        self, owner_id: str, project_id: str, memory_id: str
    ) -> SemanticMemoryEntry | None:
        r = await self.db.execute(
            select(SemanticMemoryEntry).where(
                SemanticMemoryEntry.owner_id == owner_id,
                SemanticMemoryEntry.project_id == project_id,
                SemanticMemoryEntry.provenance_json["agent_memory_id"].as_string() == memory_id,
            )
        )
        return r.scalar_one_or_none()

    async def find_semantic_by_task_close(
        self, owner_id: str, project_id: str, task_id: str
    ) -> SemanticMemoryEntry | None:
        r = await self.db.execute(
            select(SemanticMemoryEntry)
            .where(
                SemanticMemoryEntry.owner_id == owner_id,
                SemanticMemoryEntry.project_id == project_id,
                SemanticMemoryEntry.provenance_json["source"].as_string() == "task_close",
                SemanticMemoryEntry.provenance_json["task_id"].as_string() == task_id,
            )
            .limit(1)
        )
        return r.scalars().first()

    async def search_semantic_memory_by_vector(
        self,
        owner_id: str,
        project_id: str,
        query_vec: list[float],
        *,
        limit: int = 12,
    ) -> list[SemanticMemoryEntry]:
        cap = max(1, min(limit, 50))
        qv = normalize_embedding_for_vector(query_vec)
        literal = "[" + ",".join(str(float(x)) for x in qv) + "]"
        sql = text(
            """
            SELECT id FROM semantic_memory_entries
            WHERE owner_id = :oid
              AND project_id = :pid
              AND embedding_vector IS NOT NULL
            ORDER BY embedding_vector <=> CAST(:qv AS vector)
            LIMIT :lim
            """
        )
        result = await self.db.execute(
            sql, {"oid": owner_id, "pid": project_id, "qv": literal, "lim": cap}
        )
        ids = [row[0] for row in result.all()]
        if not ids:
            return []
        r2 = await self.db.execute(select(SemanticMemoryEntry).where(SemanticMemoryEntry.id.in_(ids)))
        by_id = {x.id: x for x in r2.scalars().all()}
        return [by_id[i] for i in ids if i in by_id]

    async def list_procedural_playbooks(
        self, owner_id: str, project_id: str
    ) -> list[ProceduralPlaybook]:
        res = await self.db.execute(
            select(ProceduralPlaybook)
            .where(
                ProceduralPlaybook.owner_id == owner_id,
                ProceduralPlaybook.project_id == project_id,
            )
            .order_by(ProceduralPlaybook.updated_at.desc())
        )
        return list(res.scalars().all())

    async def get_procedural_playbook(
        self, owner_id: str, project_id: str, playbook_id: str
    ) -> ProceduralPlaybook | None:
        r = await self.db.execute(
            select(ProceduralPlaybook).where(
                ProceduralPlaybook.id == playbook_id,
                ProceduralPlaybook.owner_id == owner_id,
                ProceduralPlaybook.project_id == project_id,
            )
        )
        return r.scalar_one_or_none()

    async def create_procedural_playbook(self, **kwargs: Any) -> ProceduralPlaybook:
        row = ProceduralPlaybook(**kwargs)
        self.db.add(row)
        await self.db.flush()
        return row

    async def create_memory_ingest_job(self, **kwargs: Any) -> MemoryIngestJob:
        row = MemoryIngestJob(**kwargs)
        self.db.add(row)
        await self.db.flush()
        return row

    async def list_pending_memory_ingest_jobs(self, *, limit: int = 20) -> list[MemoryIngestJob]:
        res = await self.db.execute(
            select(MemoryIngestJob)
            .where(MemoryIngestJob.status == "pending")
            .order_by(MemoryIngestJob.created_at.asc())
            .limit(max(1, min(limit, 100)))
        )
        return list(res.scalars().all())

    async def list_memory_ingest_jobs_for_project(
        self, owner_id: str, project_id: str, *, limit: int = 80
    ) -> list[MemoryIngestJob]:
        res = await self.db.execute(
            select(MemoryIngestJob)
            .where(
                MemoryIngestJob.owner_id == owner_id,
                MemoryIngestJob.project_id == project_id,
            )
            .order_by(MemoryIngestJob.created_at.desc())
            .limit(max(1, min(limit, 300)))
        )
        return list(res.scalars().all())

    async def search_episodic_for_project(
        self,
        project_id: str,
        *,
        query: str | None = None,
        limit: int = 45,
        since: datetime | None = None,
        until: datetime | None = None,
        task_id: str | None = None,
        kinds: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Layer 4 — unified hits across run events, task comments, brainstorm messages."""
        cap = max(1, min(limit, 200))
        kind_set = set(kinds) if kinds else None
        valid = ("run_event", "task_comment", "brainstorm_message")
        active = [k for k in valid if kind_set is None or k in kind_set]
        n_active = max(1, len(active))
        per_source = max(5, cap // n_active)
        hits: list[dict[str, Any]] = []
        qpat = f"%{query}%" if query else None

        if "run_event" in active:
            stmt = (
                select(RunEvent)
                .join(TaskRun, RunEvent.run_id == TaskRun.id)
                .where(TaskRun.project_id == project_id)
            )
            if qpat:
                stmt = stmt.where(RunEvent.message.ilike(qpat))
            if since:
                stmt = stmt.where(RunEvent.created_at >= since)
            if until:
                stmt = stmt.where(RunEvent.created_at <= until)
            if task_id:
                stmt = stmt.where(RunEvent.task_id == task_id)
            stmt = stmt.order_by(RunEvent.created_at.desc()).limit(per_source)
            ev_rows = await self.db.execute(stmt)
            for ev in ev_rows.scalars().all():
                hits.append(
                    {
                        "kind": "run_event",
                        "id": ev.id,
                        "run_id": ev.run_id,
                        "task_id": ev.task_id,
                        "event_type": ev.event_type,
                        "snippet": (ev.message or "")[:500],
                        "created_at": ev.created_at.isoformat(),
                    }
                )

        if "task_comment" in active:
            stmt = (
                select(TaskComment)
                .join(OrchestratorTask, TaskComment.task_id == OrchestratorTask.id)
                .where(OrchestratorTask.project_id == project_id)
            )
            if qpat:
                stmt = stmt.where(TaskComment.body.ilike(qpat))
            if since:
                stmt = stmt.where(TaskComment.created_at >= since)
            if until:
                stmt = stmt.where(TaskComment.created_at <= until)
            if task_id:
                stmt = stmt.where(TaskComment.task_id == task_id)
            stmt = stmt.order_by(TaskComment.created_at.desc()).limit(per_source)
            cm_rows = await self.db.execute(stmt)
            for comment in cm_rows.scalars().all():
                hits.append(
                    {
                        "kind": "task_comment",
                        "id": comment.id,
                        "task_id": comment.task_id,
                        "snippet": (comment.body or "")[:500],
                        "created_at": comment.created_at.isoformat(),
                    }
                )

        if "brainstorm_message" in active:
            stmt = (
                select(BrainstormMessage)
                .join(Brainstorm, BrainstormMessage.brainstorm_id == Brainstorm.id)
                .where(Brainstorm.project_id == project_id)
            )
            if qpat:
                stmt = stmt.where(BrainstormMessage.content.ilike(qpat))
            if since:
                stmt = stmt.where(BrainstormMessage.created_at >= since)
            if until:
                stmt = stmt.where(BrainstormMessage.created_at <= until)
            stmt = stmt.order_by(BrainstormMessage.created_at.desc()).limit(per_source)
            msg_rows = await self.db.execute(stmt)
            for msg in msg_rows.scalars().all():
                hits.append(
                    {
                        "kind": "brainstorm_message",
                        "id": msg.id,
                        "brainstorm_id": msg.brainstorm_id,
                        "snippet": (msg.content or "")[:500],
                        "created_at": msg.created_at.isoformat(),
                    }
                )

        hits.sort(key=lambda x: x["created_at"], reverse=True)
        return hits[:cap]

    async def create_episodic_archive_manifest(self, **kwargs: Any) -> EpisodicArchiveManifest:
        row = EpisodicArchiveManifest(**kwargs)
        self.db.add(row)
        await self.db.flush()
        return row

    async def list_episodic_archive_manifests(
        self, owner_id: str, project_id: str, *, limit: int = 50
    ) -> list[EpisodicArchiveManifest]:
        res = await self.db.execute(
            select(EpisodicArchiveManifest)
            .where(
                EpisodicArchiveManifest.owner_id == owner_id,
                EpisodicArchiveManifest.project_id == project_id,
            )
            .order_by(EpisodicArchiveManifest.created_at.desc())
            .limit(max(1, min(limit, 200)))
        )
        return list(res.scalars().all())

    async def get_episodic_index_row(
        self, project_id: str, source_kind: str, source_id: str
    ) -> EpisodicSearchIndex | None:
        r = await self.db.execute(
            select(EpisodicSearchIndex).where(
                EpisodicSearchIndex.project_id == project_id,
                EpisodicSearchIndex.source_kind == source_kind,
                EpisodicSearchIndex.source_id == source_id,
            )
        )
        return r.scalar_one_or_none()

    async def create_episodic_search_index_row(self, **kwargs: Any) -> EpisodicSearchIndex:
        row = EpisodicSearchIndex(**kwargs)
        self.db.add(row)
        await self.db.flush()
        return row

    async def search_episodic_index_by_vector(
        self,
        owner_id: str,
        project_id: str,
        query_vec: list[float],
        *,
        limit: int = 16,
        require_not_archived: bool = True,
    ) -> list[EpisodicSearchIndex]:
        cap = max(1, min(limit, 80))
        qv = normalize_embedding_for_vector(query_vec)
        literal = "[" + ",".join(str(float(x)) for x in qv) + "]"
        archived_clause = " AND archived_at IS NULL" if require_not_archived else ""
        sql = text(
            f"""
            SELECT id FROM episodic_search_index
            WHERE owner_id = :oid AND project_id = :pid
              AND embedding_vector IS NOT NULL
              {archived_clause}
            ORDER BY embedding_vector <=> CAST(:qv AS vector)
            LIMIT :lim
            """
        )
        result = await self.db.execute(
            sql, {"oid": owner_id, "pid": project_id, "qv": literal, "lim": cap}
        )
        ids = [row[0] for row in result.all()]
        if not ids:
            return []
        r2 = await self.db.execute(
            select(EpisodicSearchIndex).where(EpisodicSearchIndex.id.in_(ids))
        )
        by_id = {x.id: x for x in r2.scalars().all()}
        return [by_id[i] for i in ids if i in by_id]

    async def list_episodic_index_missing_embedding(
        self, project_id: str, *, limit: int = 40
    ) -> list[EpisodicSearchIndex]:
        res = await self.db.execute(
            select(EpisodicSearchIndex)
            .where(
                EpisodicSearchIndex.project_id == project_id,
                EpisodicSearchIndex.archived_at.is_(None),
                EpisodicSearchIndex.embedding_vector.is_(None),
            )
            .order_by(EpisodicSearchIndex.created_at.asc())
            .limit(max(1, min(limit, 200)))
        )
        return list(res.scalars().all())

    async def delete_episodic_index_rows_before(self, project_id: str, before: datetime) -> int:
        res = await self.db.execute(
            delete(EpisodicSearchIndex).where(
                EpisodicSearchIndex.project_id == project_id,
                EpisodicSearchIndex.created_at < before,
            )
        )
        return int(res.rowcount or 0)

    async def list_run_events_for_project_before(
        self, project_id: str, before: datetime, *, limit: int = 3000
    ) -> list[RunEvent]:
        res = await self.db.execute(
            select(RunEvent)
            .join(TaskRun, RunEvent.run_id == TaskRun.id)
            .where(TaskRun.project_id == project_id, RunEvent.created_at < before)
            .order_by(RunEvent.created_at.asc())
            .limit(max(1, min(limit, 10_000)))
        )
        return list(res.scalars().all())

    async def create_semantic_memory_link(self, **kwargs: Any) -> SemanticMemoryLink:
        row = SemanticMemoryLink(**kwargs)
        self.db.add(row)
        await self.db.flush()
        return row

    async def list_semantic_memory_links(
        self, owner_id: str, project_id: str, entry_id: str
    ) -> list[SemanticMemoryLink]:
        res = await self.db.execute(
            select(SemanticMemoryLink)
            .where(
                SemanticMemoryLink.owner_id == owner_id,
                SemanticMemoryLink.project_id == project_id,
                or_(
                    SemanticMemoryLink.from_entry_id == entry_id,
                    SemanticMemoryLink.to_entry_id == entry_id,
                ),
            )
            .order_by(SemanticMemoryLink.created_at.desc())
        )
        return list(res.scalars().all())

    async def delete_semantic_memory_link(
        self, owner_id: str, project_id: str, link_id: str
    ) -> bool:
        r = await self.db.execute(
            select(SemanticMemoryLink).where(
                SemanticMemoryLink.id == link_id,
                SemanticMemoryLink.owner_id == owner_id,
                SemanticMemoryLink.project_id == project_id,
            )
        )
        row = r.scalar_one_or_none()
        if row is None:
            return False
        await self.db.delete(row)
        return True

    async def update_memory_ingest_job(
        self,
        job_id: str,
        *,
        status: str | None = None,
        error_text: str | None = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
    ) -> None:
        from sqlalchemy import update as sa_update

        vals: dict[str, Any] = {}
        if status is not None:
            vals["status"] = status
        if error_text is not None:
            vals["error_text"] = error_text
        if started_at is not None:
            vals["started_at"] = started_at
        if finished_at is not None:
            vals["finished_at"] = finished_at
        if vals:
            await self.db.execute(
                sa_update(MemoryIngestJob).where(MemoryIngestJob.id == job_id).values(**vals)
            )
