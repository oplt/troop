from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import func, select

from backend.modules.orchestration.models import ApprovalRequest, TaskRun
from backend.modules.projects.orchestration_models import (
    OrchestratorProject,
    OrchestratorTask,
    ProjectDecision,
    ProjectMilestone,
    ProjectRepositoryLink,
    TaskArtifact,
    TaskComment,
    TaskDependency,
)


class OrchestrationProjectsRepositoryMixin:
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
        result = await self.db.execute(select(OrchestratorTask).where(OrchestratorTask.id == task_id))
        return result.scalar_one_or_none()

    async def create_task(self, **kwargs) -> OrchestratorTask:
        item = OrchestratorTask(**kwargs)
        self.db.add(item)
        await self.db.flush()
        return item

    async def replace_task_dependencies(self, task_id: str, dependency_ids: Sequence[str]) -> None:
        existing = await self.db.execute(select(TaskDependency).where(TaskDependency.task_id == task_id))
        for item in existing.scalars().all():
            await self.db.delete(item)
        for dependency_id in dependency_ids:
            self.db.add(TaskDependency(task_id=task_id, depends_on_task_id=dependency_id))
        await self.db.flush()

    async def list_task_dependencies(self, project_id: str) -> list[TaskDependency]:
        task_ids_query = select(OrchestratorTask.id).where(OrchestratorTask.project_id == project_id)
        result = await self.db.execute(select(TaskDependency).where(TaskDependency.task_id.in_(task_ids_query)))
        return list(result.scalars().all())

    async def list_task_dependencies_for_task(self, task_id: str) -> list[TaskDependency]:
        result = await self.db.execute(select(TaskDependency).where(TaskDependency.task_id == task_id))
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
        result = await self.db.execute(select(ProjectMilestone).where(ProjectMilestone.id == milestone_id))
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

    async def summarize_portfolio_for_owner(self, owner_id: str) -> list[dict[str, object]]:
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
                .where(TaskRun.project_id.in_(project_ids), TaskRun.status.in_(["queued", "in_progress", "blocked"]))
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
