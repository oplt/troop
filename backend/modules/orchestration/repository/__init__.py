from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, delete, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.pagination import (
    apply_asc_position_time_id_cursor,
    apply_asc_time_id_cursor,
    apply_desc_time_id_cursor,
    fetch_limit,
)
from backend.modules.audit.models import AuditLog
from backend.modules.github.repository import GithubRepositoryMixin
from backend.modules.memory.repository import MemoryRepositoryMixin
from backend.modules.orchestration.list_load_options import (
    approval_list_load,
    notification_list_load,
    project_list_load,
    run_event_list_load,
    task_list_load,
    task_run_list_load,
)
from backend.modules.orchestration._helpers import resolve_query_limit
from backend.modules.orchestration.models import (
    AgentMemoryEntry,
    AgentProfile,
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
    ModelCapability,
    OrchestratorProject,
    OrchestratorTask,
    ProceduralPlaybook,
    ProjectAgentMembership,
    ProjectDecision,
    ProjectDocument,
    ProjectDocumentChunk,
    ProjectMilestone,
    ProjectRepositoryLink,
    ProviderConfig,
    RunEvent,
    SemanticMemoryEntry,
    SemanticMemoryLink,
    TaskArtifact,
    TaskComment,
    TaskDependency,
    TaskRun,
    normalize_embedding_for_vector,
)
from backend.modules.orchestration.repository.agents import OrchestrationAgentsRepositoryMixin
from backend.modules.projects.orchestration_repository import OrchestrationProjectsRepositoryMixin
from backend.modules.team.repository import TeamRepositoryMixin


class OrchestrationRepository(
    OrchestrationAgentsRepositoryMixin,
    TeamRepositoryMixin,
    OrchestrationProjectsRepositoryMixin,
    GithubRepositoryMixin,
    MemoryRepositoryMixin,
):
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_projects(self, owner_id: str) -> list[OrchestratorProject]:
        result = await self.db.execute(
            select(OrchestratorProject)
            .where(OrchestratorProject.owner_id == owner_id)
            .order_by(OrchestratorProject.updated_at.desc())
            .options(project_list_load())
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

    async def get_project_live_snapshot(self, owner_id: str, project_id: str) -> dict[str, Any]:
        summary = (
            await self.db.execute(
                select(
                    select(func.count(ProjectAgentMembership.id))
                    .where(ProjectAgentMembership.project_id == project_id)
                    .scalar_subquery()
                    .label("agent_total"),
                    select(func.count(ProjectRepositoryLink.id))
                    .where(ProjectRepositoryLink.project_id == project_id)
                    .scalar_subquery()
                    .label("repository_total"),
                    select(func.count(ProjectDocument.id))
                    .where(
                        ProjectDocument.project_id == project_id,
                        ProjectDocument.deleted_at.is_(None),
                    )
                    .scalar_subquery()
                    .label("document_total"),
                    select(func.count(ProjectDecision.id))
                    .where(ProjectDecision.project_id == project_id)
                    .scalar_subquery()
                    .label("decision_total"),
                    select(func.count(AgentMemoryEntry.id))
                    .where(
                        AgentMemoryEntry.owner_id == owner_id,
                        AgentMemoryEntry.project_id == project_id,
                        AgentMemoryEntry.deleted_at.is_(None),
                    )
                    .scalar_subquery()
                    .label("memory_entry_total"),
                    select(func.count(ApprovalRequest.id))
                    .where(
                        ApprovalRequest.project_id == project_id,
                        ApprovalRequest.status == "pending",
                    )
                    .scalar_subquery()
                    .label("pending_approvals"),
                )
            )
        ).one()

        task_counts = {"total": 0, "open": 0, "blocked": 0, "review": 0}
        latest_task_updated_at: datetime | None = None
        task_rows = await self.db.execute(
            select(
                OrchestratorTask.status,
                func.count(OrchestratorTask.id),
                func.max(OrchestratorTask.updated_at),
            )
            .where(OrchestratorTask.project_id == project_id)
            .group_by(OrchestratorTask.status)
        )
        for status, count, updated_at in task_rows.all():
            count_value = int(count or 0)
            task_counts["total"] += count_value
            if status not in {"completed", "archived", "synced_to_github"}:
                task_counts["open"] += count_value
            if status == "blocked":
                task_counts["blocked"] += count_value
            if status == "needs_review":
                task_counts["review"] += count_value
            if updated_at and (
                latest_task_updated_at is None or updated_at > latest_task_updated_at
            ):
                latest_task_updated_at = updated_at

        run_counts = {"total": 0, "active": 0, "failed": 0}
        latest_run_created_at: datetime | None = None
        run_rows = await self.db.execute(
            select(
                TaskRun.status,
                func.count(TaskRun.id),
                func.max(TaskRun.created_at),
            )
            .where(TaskRun.project_id == project_id)
            .group_by(TaskRun.status)
        )
        for status, count, created_at in run_rows.all():
            count_value = int(count or 0)
            run_counts["total"] += count_value
            if status in {"queued", "in_progress", "blocked"}:
                run_counts["active"] += count_value
            if status == "failed":
                run_counts["failed"] += count_value
            if created_at and (latest_run_created_at is None or created_at > latest_run_created_at):
                latest_run_created_at = created_at

        sync_counts = {"pending": 0, "failed": 0}
        latest_sync_created_at: datetime | None = None
        sync_rows = await self.db.execute(
            select(
                GithubSyncEvent.status,
                func.count(GithubSyncEvent.id),
                func.max(GithubSyncEvent.created_at),
            )
            .join(GithubRepository, GithubSyncEvent.repository_id == GithubRepository.id)
            .where(GithubRepository.project_id == project_id)
            .group_by(GithubSyncEvent.status)
        )
        for status, count, created_at in sync_rows.all():
            count_value = int(count or 0)
            if status in {"queued", "pending"}:
                sync_counts["pending"] += count_value
            if status in {"failed", "error"}:
                sync_counts["failed"] += count_value
            if created_at and (
                latest_sync_created_at is None or created_at > latest_sync_created_at
            ):
                latest_sync_created_at = created_at

        ingest_counts = {"pending": 0, "running": 0, "failed": 0}
        ingest_rows = await self.db.execute(
            select(MemoryIngestJob.status, func.count(MemoryIngestJob.id))
            .where(
                MemoryIngestJob.owner_id == owner_id,
                MemoryIngestJob.project_id == project_id,
            )
            .group_by(MemoryIngestJob.status)
        )
        for status, count in ingest_rows.all():
            count_value = int(count or 0)
            if status == "pending":
                ingest_counts["pending"] += count_value
            elif status == "running":
                ingest_counts["running"] += count_value
            elif status == "failed":
                ingest_counts["failed"] += count_value

        return {
            "project_id": project_id,
            "agent_counts": {
                "total": int(summary.agent_total or 0),
            },
            "resource_counts": {
                "repositories": int(summary.repository_total or 0),
                "documents": int(summary.document_total or 0),
                "decisions": int(summary.decision_total or 0),
                "memory_entries": int(summary.memory_entry_total or 0),
            },
            "task_counts": task_counts,
            "run_counts": run_counts,
            "approval_counts": {
                "pending": int(summary.pending_approvals or 0),
            },
            "sync_counts": sync_counts,
            "ingest_counts": ingest_counts,
            "latest": {
                "task_updated_at": latest_task_updated_at,
                "run_created_at": latest_run_created_at,
                "sync_created_at": latest_sync_created_at,
            },
        }

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

    async def get_project_repository(
        self, project_id: str, repository_link_id: str
    ) -> ProjectRepositoryLink | None:
        result = await self.db.execute(
            select(ProjectRepositoryLink).where(
                ProjectRepositoryLink.project_id == project_id,
                ProjectRepositoryLink.id == repository_link_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_tasks(
        self, project_id: str, *, limit: int | None = None
    ) -> list[OrchestratorTask]:
        stmt = (
            select(OrchestratorTask)
            .where(OrchestratorTask.project_id == project_id)
            .order_by(OrchestratorTask.position.asc(), OrchestratorTask.created_at.asc())
        )
        cap = resolve_query_limit(
            limit,
            default=settings.ORCHESTRATION_LIST_TASKS_DEFAULT_LIMIT,
            maximum=settings.ORCHESTRATION_LIST_TASKS_MAX_LIMIT,
        )
        if cap is not None:
            stmt = stmt.limit(cap)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_tasks_with_dependencies(
        self,
        project_id: str,
        *,
        limit: int | None = None,
        cursor_position: int | None = None,
        cursor_created_at: datetime | None = None,
        cursor_id: str | None = None,
    ) -> tuple[list[OrchestratorTask], dict[str, list[str]]]:
        """Load a bounded task page and all of its dependencies in one SQL read.

        The limited task-id subquery is important: applying ``LIMIT`` after an
        outer join would truncate dependency rows and return incomplete graphs.
        """
        task_ids = select(OrchestratorTask.id).where(OrchestratorTask.project_id == project_id)
        task_ids = apply_asc_position_time_id_cursor(
            task_ids,
            OrchestratorTask,
            cursor_position=cursor_position,
            cursor_created_at=cursor_created_at,
            cursor_id=cursor_id,
        )
        task_ids = task_ids.order_by(
            OrchestratorTask.position.asc(),
            OrchestratorTask.created_at.asc(),
            OrchestratorTask.id.asc(),
        ).options(task_list_load())
        cap = resolve_query_limit(
            limit,
            default=settings.ORCHESTRATION_LIST_TASKS_DEFAULT_LIMIT,
            maximum=settings.ORCHESTRATION_LIST_TASKS_MAX_LIMIT,
        )
        task_ids = task_ids.limit(fetch_limit(cap))

        id_rows = await self.db.execute(task_ids)
        ordered_task_ids = [str(row[0]) for row in id_rows.all()]
        if not ordered_task_ids:
            return [], {}

        result = await self.db.execute(
            select(OrchestratorTask, TaskDependency)
            .outerjoin(TaskDependency, TaskDependency.task_id == OrchestratorTask.id)
            .where(OrchestratorTask.id.in_(ordered_task_ids))
            .order_by(
                OrchestratorTask.position.asc(),
                OrchestratorTask.created_at.asc(),
                TaskDependency.created_at.asc(),
            )
        )
        tasks_by_id: dict[str, OrchestratorTask] = {}
        dependencies: dict[str, list[str]] = {}
        for task, dependency in result.all():
            tasks_by_id.setdefault(task.id, task)
            if dependency is not None:
                dependencies.setdefault(task.id, []).append(dependency.depends_on_task_id)
        tasks = [tasks_by_id[task_id] for task_id in ordered_task_ids if task_id in tasks_by_id]
        return tasks, dependencies

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
        task_ids_query = select(OrchestratorTask.id).where(
            OrchestratorTask.project_id == project_id
        )
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
            select(func.max(OrchestratorTask.position)).where(
                OrchestratorTask.project_id == project_id
            )
        )
        return int(value or -1) + 1

    async def create_run(self, **kwargs) -> TaskRun:
        item = TaskRun(**kwargs)
        self.db.add(item)
        await self.db.flush()
        return item

    async def list_child_runs(self, parent_run_id: str) -> list[TaskRun]:
        result = await self.db.execute(
            select(TaskRun)
            .where(TaskRun.parent_run_id == parent_run_id)
            .order_by(TaskRun.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_run(self, owner_id: str, run_id: str) -> TaskRun | None:
        result = await self.db.execute(
            select(TaskRun)
            .join(OrchestratorProject, TaskRun.project_id == OrchestratorProject.id)
            .where(TaskRun.id == run_id, OrchestratorProject.owner_id == owner_id)
        )
        return result.scalar_one_or_none()

    async def list_runs(
        self,
        owner_id: str,
        project_id: str | None = None,
        *,
        limit: int | None = None,
        cursor_created_at: datetime | None = None,
        cursor_id: str | None = None,
    ) -> list[TaskRun]:
        stmt = (
            select(TaskRun)
            .join(OrchestratorProject, TaskRun.project_id == OrchestratorProject.id)
            .where(OrchestratorProject.owner_id == owner_id)
        )
        if project_id:
            stmt = stmt.where(TaskRun.project_id == project_id)
        stmt = apply_desc_time_id_cursor(
            stmt,
            TaskRun,
            cursor_created_at=cursor_created_at,
            cursor_id=cursor_id,
        )
        stmt = stmt.order_by(TaskRun.created_at.desc(), TaskRun.id.desc()).options(task_run_list_load())
        cap = resolve_query_limit(
            limit,
            default=settings.ORCHESTRATION_LIST_RUNS_DEFAULT_LIMIT,
            maximum=settings.ORCHESTRATION_LIST_RUNS_MAX_LIMIT,
        )
        stmt = stmt.limit(fetch_limit(cap))
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_runs_for_owner_since(
        self, owner_id: str, since: datetime, *, limit: int = 2000
    ) -> list[TaskRun]:
        cap = max(1, min(limit, 5000))
        result = await self.db.execute(
            select(TaskRun)
            .join(OrchestratorProject, TaskRun.project_id == OrchestratorProject.id)
            .where(OrchestratorProject.owner_id == owner_id, TaskRun.created_at >= since)
            .order_by(TaskRun.created_at.desc(), TaskRun.id.desc())
            .limit(cap)
        )
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

    async def sum_estimated_cost_micros_for_agent(
        self, owner_id: str, agent_id: str, since: datetime
    ) -> int:
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
        stmt = select(func.coalesce(func.sum(RunEvent.cost_usd_micros), 0)).where(
            RunEvent.run_id == run_id
        )
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

    async def count_active_runs_by_worker(
        self, project_id: str, agent_ids: Sequence[str]
    ) -> dict[str, int]:
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

    async def count_run_events(self, run_id: str) -> int:
        result = await self.db.execute(
            select(func.count()).select_from(RunEvent).where(RunEvent.run_id == run_id)
        )
        return int(result.scalar_one() or 0)

    async def count_run_events_by_types(self, run_id: str, event_types: Sequence[str]) -> int:
        if not event_types:
            return 0
        result = await self.db.execute(
            select(func.count())
            .select_from(RunEvent)
            .where(RunEvent.run_id == run_id, RunEvent.event_type.in_(event_types))
        )
        return int(result.scalar_one() or 0)

    async def list_run_events(
        self,
        run_id: str,
        *,
        limit: int | None = None,
        offset: int = 0,
        descending: bool = False,
        cursor_created_at: datetime | None = None,
        cursor_id: str | None = None,
    ) -> list[RunEvent]:
        cap = resolve_query_limit(
            limit,
            default=settings.RUN_EVENTS_DEFAULT_LIMIT,
            maximum=settings.RUN_EVENTS_MAX_LIMIT,
        )
        offset = max(int(offset), 0)
        stmt = select(RunEvent).where(RunEvent.run_id == run_id)
        if descending:
            stmt = apply_desc_time_id_cursor(
                stmt,
                RunEvent,
                cursor_created_at=cursor_created_at,
                cursor_id=cursor_id,
            )
            order_cols = (RunEvent.created_at.desc(), RunEvent.id.desc())
        else:
            stmt = apply_asc_time_id_cursor(
                stmt,
                RunEvent,
                cursor_created_at=cursor_created_at,
                cursor_id=cursor_id,
            )
            order_cols = (RunEvent.created_at.asc(), RunEvent.id.asc())
        if cursor_created_at is None and cursor_id is None and offset:
            stmt = stmt.offset(offset)
        result = await self.db.execute(
            stmt.order_by(*order_cols).limit(fetch_limit(cap)).options(run_event_list_load())
        )
        events = list(result.scalars().all())
        if descending:
            events.reverse()
        return events

    async def list_run_events_tail(self, run_id: str, *, limit: int = 12) -> list[RunEvent]:
        cap = min(max(int(limit), 1), settings.RUN_EVENTS_MAX_LIMIT)
        result = await self.db.execute(
            select(RunEvent)
            .where(RunEvent.run_id == run_id)
            .order_by(RunEvent.created_at.desc(), RunEvent.id.desc())
            .limit(cap)
        )
        events = list(result.scalars().all())
        events.reverse()
        return events

    async def list_run_events_since(
        self,
        run_id: str,
        *,
        created_after: datetime | None,
        after_id: str | None = None,
        limit: int = 200,
    ) -> list[RunEvent]:
        stmt = select(RunEvent).where(RunEvent.run_id == run_id)
        if created_after is not None:
            cursor = RunEvent.created_at > created_after
            if after_id is not None:
                cursor = or_(
                    cursor,
                    and_(RunEvent.created_at == created_after, RunEvent.id > after_id),
                )
            stmt = stmt.where(cursor)
        result = await self.db.execute(
            stmt.order_by(RunEvent.created_at.asc(), RunEvent.id.asc()).limit(limit)
        )
        return list(result.scalars().all())

    async def get_run_for_worker(self, run_id: str) -> TaskRun | None:
        result = await self.db.execute(
            select(TaskRun).where(TaskRun.id == run_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def list_stale_in_progress_runs(
        self, older_than: datetime, *, limit: int = 100
    ) -> list[TaskRun]:
        result = await self.db.execute(
            select(TaskRun)
            .where(
                TaskRun.status == "in_progress",
                TaskRun.started_at.is_not(None),
                TaskRun.started_at < older_than,
            )
            .order_by(TaskRun.started_at.asc())
            .limit(max(1, min(limit, 500)))
        )
        return list(result.scalars().all())

    async def list_providers(
        self, owner_id: str, project_id: str | None = None
    ) -> list[ProviderConfig]:
        stmt = select(ProviderConfig).where(ProviderConfig.owner_id == owner_id)
        if project_id is None:
            stmt = stmt.where(ProviderConfig.project_id.is_(None))
        else:
            stmt = stmt.where(
                or_(ProviderConfig.project_id == project_id, ProviderConfig.project_id.is_(None))
            )
        result = await self.db.execute(
            stmt.order_by(ProviderConfig.is_default.desc(), ProviderConfig.updated_at.desc())
        )
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

    async def list_projects_using_provider(
        self, owner_id: str, provider_id: str
    ) -> list[OrchestratorProject]:
        result = await self.db.execute(
            select(OrchestratorProject).where(OrchestratorProject.owner_id == owner_id)
        )
        projects = list(result.scalars().all())
        connected: list[OrchestratorProject] = []
        connected_ids: set[str] = set()
        for project in projects:
            execution = (project.settings_json or {}).get("execution") or {}
            if execution.get("provider_config_id") == provider_id:
                connected.append(project)
                connected_ids.add(project.id)
        agent_result = await self.db.execute(
            select(OrchestratorProject)
            .join(AgentProfile, AgentProfile.project_id == OrchestratorProject.id)
            .where(
                OrchestratorProject.owner_id == owner_id,
                AgentProfile.provider_config_id == provider_id,
            )
        )
        for project in agent_result.scalars().all():
            if project.id not in connected_ids:
                connected.append(project)
                connected_ids.add(project.id)
        return connected

    async def delete_provider(self, provider: ProviderConfig) -> None:
        await self.db.delete(provider)
        await self.db.flush()

    async def list_all_providers(self, *, enabled_only: bool = True) -> list[ProviderConfig]:
        stmt = select(ProviderConfig)
        if enabled_only:
            stmt = stmt.where(ProviderConfig.is_enabled.is_(True))
        result = await self.db.execute(stmt.order_by(ProviderConfig.updated_at.desc()))
        return list(result.scalars().all())

    async def list_owned_providers(
        self, owner_id: str, *, enabled_only: bool = False
    ) -> list[ProviderConfig]:
        stmt = select(ProviderConfig).where(ProviderConfig.owner_id == owner_id)
        if enabled_only:
            stmt = stmt.where(ProviderConfig.is_enabled.is_(True))
        result = await self.db.execute(
            stmt.order_by(ProviderConfig.is_default.desc(), ProviderConfig.updated_at.desc())
        )
        return list(result.scalars().all())

    async def list_model_capabilities(
        self,
        provider_type: str | None = None,
        *,
        provider_id: str | None = None,
        active_only: bool = True,
    ) -> list[ModelCapability]:
        stmt = select(ModelCapability)
        if provider_id:
            stmt = stmt.where(ModelCapability.provider_id == provider_id)
        if provider_type:
            stmt = stmt.where(ModelCapability.provider_type == provider_type)
        if active_only:
            stmt = stmt.where(ModelCapability.is_active.is_(True))
        result = await self.db.execute(
            stmt.order_by(ModelCapability.provider_type.asc(), ModelCapability.model_slug.asc())
        )
        return list(result.scalars().all())

    async def list_model_capabilities_for_owner(
        self,
        owner_id: str,
        *,
        active_only: bool = True,
    ) -> list[ModelCapability]:
        """Return shared catalog rows plus rows belonging to this owner only."""
        stmt = (
            select(ModelCapability)
            .outerjoin(ProviderConfig, ModelCapability.provider_id == ProviderConfig.id)
            .where(or_(ModelCapability.provider_id.is_(None), ProviderConfig.owner_id == owner_id))
        )
        if active_only:
            stmt = stmt.where(ModelCapability.is_active.is_(True))
        result = await self.db.execute(
            stmt.order_by(ModelCapability.provider_type.asc(), ModelCapability.model_slug.asc())
        )
        return list(result.scalars().all())

    async def get_model_capability(
        self,
        model_slug: str,
        provider_type: str | None = None,
        *,
        provider_id: str | None = None,
    ) -> ModelCapability | None:
        stmt = select(ModelCapability).where(ModelCapability.model_slug == model_slug)
        if provider_id:
            stmt = stmt.where(ModelCapability.provider_id == provider_id)
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

    async def list_brainstorms(
        self, owner_id: str, project_id: str | None = None
    ) -> list[Brainstorm]:
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

    async def list_brainstorm_runs(self, brainstorm_id: str) -> list[TaskRun]:
        result = await self.db.execute(
            select(TaskRun)
            .where(TaskRun.brainstorm_id == brainstorm_id)
            .order_by(TaskRun.created_at.asc())
        )
        return list(result.scalars().all())

    async def create_project_decision(self, **kwargs) -> ProjectDecision:
        item = ProjectDecision(**kwargs)
        self.db.add(item)
        await self.db.flush()
        return item

    async def list_project_decisions(
        self, project_id: str, *, limit: int | None = None, query: str | None = None
    ) -> list[ProjectDecision]:
        cap = max(1, min(int(limit or settings.PROJECT_DECISIONS_MERGE_LIMIT), 1000))
        stmt = select(ProjectDecision).where(ProjectDecision.project_id == project_id)
        if query and query.strip():
            tokens = [t for t in query.lower().split() if len(t) >= 3][:8]
            for token in tokens:
                pattern = f"%{token}%"
                stmt = stmt.where(
                    or_(
                        ProjectDecision.title.ilike(pattern),
                        ProjectDecision.decision.ilike(pattern),
                        ProjectDecision.rationale.ilike(pattern),
                    )
                )
        stmt = stmt.order_by(ProjectDecision.created_at.desc()).limit(cap)
        result = await self.db.execute(stmt)
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

    async def update_project_milestone(
        self, milestone_id: str, updates: dict
    ) -> ProjectMilestone | None:
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

    async def get_github_connection(
        self, owner_id: str, connection_id: str
    ) -> GithubConnection | None:
        result = await self.db.execute(
            select(GithubConnection).where(
                GithubConnection.owner_id == owner_id,
                GithubConnection.id == connection_id,
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

    async def get_github_repository(
        self, owner_id: str, repository_id: str
    ) -> GithubRepository | None:
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

    async def list_issue_links(
        self, owner_id: str, project_id: str | None = None
    ) -> list[GithubIssueLink]:
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

    async def list_issue_links_stale(
        self, *, older_than: datetime, limit: int = 40
    ) -> list[GithubIssueLink]:
        stmt = (
            select(GithubIssueLink)
            .join(GithubRepository, GithubIssueLink.repository_id == GithubRepository.id)
            .join(GithubConnection, GithubRepository.connection_id == GithubConnection.id)
            .where(
                GithubConnection.is_active.is_(True),
                or_(
                    GithubIssueLink.last_synced_at.is_(None),
                    GithubIssueLink.last_synced_at < older_than,
                ),
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

    async def get_sync_event_by_delivery_id(self, delivery_id: str) -> GithubSyncEvent | None:
        result = await self.db.execute(
            select(GithubSyncEvent).where(
                GithubSyncEvent.payload_json["_webhook_meta"]["delivery_id"].as_string()
                == delivery_id
            )
        )
        return result.scalar_one_or_none()

    async def list_sync_events(
        self, owner_id: str, project_id: str | None = None
    ) -> list[GithubSyncEvent]:
        stmt = (
            select(GithubSyncEvent)
            .join(
                GithubRepository, GithubSyncEvent.repository_id == GithubRepository.id, isouter=True
            )
            .join(
                GithubConnection,
                GithubRepository.connection_id == GithubConnection.id,
                isouter=True,
            )
            .where(GithubConnection.owner_id == owner_id)
        )
        if project_id:
            stmt = stmt.where(GithubRepository.project_id == project_id)
        result = await self.db.execute(stmt.order_by(GithubSyncEvent.created_at.desc()))
        return list(result.scalars().all())

    async def list_sync_events_for_owner_since(
        self, owner_id: str, since: datetime
    ) -> list[GithubSyncEvent]:
        stmt = (
            select(GithubSyncEvent)
            .join(GithubRepository, GithubSyncEvent.repository_id == GithubRepository.id)
            .join(GithubConnection, GithubRepository.connection_id == GithubConnection.id)
            .where(GithubConnection.owner_id == owner_id, GithubSyncEvent.created_at >= since)
            .order_by(GithubSyncEvent.created_at.desc())
        )
        result = await self.db.execute(stmt)
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

    async def list_documents(
        self,
        project_id: str,
        task_id: str | None = None,
        *,
        limit: int | None = None,
    ) -> list[ProjectDocument]:
        stmt = select(ProjectDocument).where(
            ProjectDocument.project_id == project_id,
            ProjectDocument.deleted_at.is_(None),
        )
        if task_id is not None:
            stmt = stmt.where(
                or_(ProjectDocument.task_id == task_id, ProjectDocument.task_id.is_(None))
            )
        stmt = stmt.order_by(ProjectDocument.created_at.desc())
        cap = resolve_query_limit(
            limit,
            default=settings.ORCHESTRATION_LIST_DOCUMENTS_DEFAULT_LIMIT,
            maximum=settings.ORCHESTRATION_LIST_DOCUMENTS_MAX_LIMIT,
        )
        if cap is not None:
            stmt = stmt.limit(cap)
        result = await self.db.execute(stmt)
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
        await self.db.execute(
            delete(ProjectDocumentChunk).where(
                ProjectDocumentChunk.project_document_id == document.id
            )
        )
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
                    embedding_json=embedding if settings.VECTOR_WRITE_EMBEDDING_JSON else [],
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
        params: dict[str, str | int] = {
            "pid": project_id,
            "qv": literal,
            "lim": max(1, min(top_k, 20)),
        }
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
        limit: int | None = None,
    ) -> list[ProjectDocumentChunk]:
        cap = settings.RAG_CHUNK_FALLBACK_MAX if limit is None else limit
        cap = min(max(int(cap), 1), settings.RAG_CHUNK_FALLBACK_MAX)
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
            stmt.order_by(
                ProjectDocumentChunk.project_document_id.asc(),
                ProjectDocumentChunk.chunk_index.asc(),
            ).limit(cap)
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

    async def list_pending_approvals_for_run(
        self, owner_id: str, run_id: str
    ) -> list[ApprovalRequest]:
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

    async def list_approvals_for_run(
        self, run_id: str, *, status: str | None = None
    ) -> list[ApprovalRequest]:
        """List approvals attached to a run for worker-side grant consumption.

        This intentionally does not take an owner id: it is only called by a worker
        after the run has already been resolved through the durable execution path.
        HTTP callers use the owner-scoped methods above.
        """
        stmt = select(ApprovalRequest).where(ApprovalRequest.run_id == run_id)
        if status is not None:
            stmt = stmt.where(ApprovalRequest.status == status)
        result = await self.db.execute(stmt.order_by(ApprovalRequest.created_at.asc()))
        return list(result.scalars().all())

    async def list_approvals_for_task(
        self, owner_id: str, project_id: str, task_id: str
    ) -> list[ApprovalRequest]:
        by_task = (
            select(ApprovalRequest)
            .join(
                OrchestratorProject,
                ApprovalRequest.project_id == OrchestratorProject.id,
                isouter=True,
            )
            .where(
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
        merged.sort(key=lambda item: item.created_at)
        return merged

    async def create_approval(self, **kwargs) -> ApprovalRequest:
        from backend.modules.orchestration.execution.hitl.approver_resolver import (
            snapshot_routing_on_approval,
        )

        item = ApprovalRequest(**kwargs)
        self.db.add(item)
        await self.db.flush()
        await snapshot_routing_on_approval(self.db, item)
        self.db.add(
            AuditLog(
                user_id=kwargs.get("requested_by_user_id"),
                action="orchestration.approval.requested",
                resource_type="approval_request",
                resource_id=item.id,
                metadata_json=json.dumps(
                    {
                        "approval_type": item.approval_type,
                        "project_id": item.project_id,
                        "task_id": item.task_id,
                        "run_id": item.run_id,
                        "issue_link_id": item.issue_link_id,
                        "payload_keys": sorted((item.payload_json or {}).keys()),
                    }
                ),
            )
        )
        await self.db.flush()
        return item

    @staticmethod
    def _approval_owner_clause(owner_id: str):
        """Tenant ACL: project owner, or requester for unscoped (null project) rows only."""
        return or_(
            OrchestratorProject.owner_id == owner_id,
            and_(
                ApprovalRequest.project_id.is_(None),
                ApprovalRequest.requested_by_user_id == owner_id,
            ),
        )

    async def list_approvals(
        self,
        owner_id: str,
        status: str | None = None,
        *,
        limit: int | None = None,
        cursor_created_at: datetime | None = None,
        cursor_id: str | None = None,
    ) -> list[ApprovalRequest]:
        from backend.modules.identity_access.workspace_permissions import (
            PERM_APPROVAL_DECIDE,
            role_has_permission,
        )
        from backend.modules.identity_access.workspace_repository import WorkspaceRepository

        stmt = (
            select(ApprovalRequest)
            .join(
                OrchestratorProject,
                ApprovalRequest.project_id == OrchestratorProject.id,
                isouter=True,
            )
            .where(self._approval_owner_clause(owner_id))
        )
        if status:
            stmt = stmt.where(ApprovalRequest.status == status)
        stmt = apply_desc_time_id_cursor(
            stmt,
            ApprovalRequest,
            cursor_created_at=cursor_created_at,
            cursor_id=cursor_id,
        )
        cap = resolve_query_limit(
            limit,
            default=settings.APPROVALS_LIST_DEFAULT_LIMIT,
            maximum=settings.APPROVALS_LIST_MAX_LIMIT,
        )
        result = await self.db.execute(
            stmt.order_by(ApprovalRequest.created_at.desc(), ApprovalRequest.id.desc())
            .limit(fetch_limit(cap))
            .options(approval_list_load())
        )
        owner_rows = list(result.scalars().all())

        ws_repo = WorkspaceRepository(self.db)
        memberships = await ws_repo.list_memberships_for_user(owner_id)
        workspace_ids = [
            workspace.id
            for workspace, membership in memberships
            if role_has_permission(membership.role, PERM_APPROVAL_DECIDE)
        ]
        if not workspace_ids:
            return owner_rows[:cap]

        approver_stmt = select(ApprovalRequest).where(
            ApprovalRequest.workspace_id.in_(workspace_ids)
        )
        if status:
            approver_stmt = approver_stmt.where(ApprovalRequest.status == status)
        approver_stmt = apply_desc_time_id_cursor(
            approver_stmt,
            ApprovalRequest,
            cursor_created_at=cursor_created_at,
            cursor_id=cursor_id,
        )
        approver_result = await self.db.execute(
            approver_stmt.order_by(
                ApprovalRequest.created_at.desc(),
                ApprovalRequest.id.desc(),
            )
            .limit(fetch_limit(cap))
            .options(approval_list_load())
        )
        approver_rows = list(approver_result.scalars().all())

        seen = {row.id for row in owner_rows}
        merged = list(owner_rows)
        for row in approver_rows:
            if row.id in seen:
                continue
            seen.add(row.id)
            merged.append(row)
        merged.sort(key=lambda item: (item.created_at, item.id), reverse=True)
        return merged[:cap]

    async def get_approval(self, owner_id: str, approval_id: str) -> ApprovalRequest | None:
        from backend.modules.orchestration.execution.hitl.approver_resolver import (
            user_can_access_approval,
        )

        result = await self.db.execute(
            select(ApprovalRequest).where(ApprovalRequest.id == approval_id)
        )
        approval = result.scalar_one_or_none()
        if approval is None:
            return None
        if not await user_can_access_approval(self.db, owner_id, approval):
            return None
        return approval

    async def get_approval_for_update(
        self, owner_id: str, approval_id: str
    ) -> ApprovalRequest | None:
        """Lock a pending approval row for decide (prevents double side effects)."""
        from backend.modules.orchestration.execution.hitl.approver_resolver import (
            user_can_access_approval,
        )

        result = await self.db.execute(
            select(ApprovalRequest)
            .where(ApprovalRequest.id == approval_id)
            .with_for_update()
        )
        approval = result.scalar_one_or_none()
        if approval is None:
            return None
        if not await user_can_access_approval(self.db, owner_id, approval):
            return None
        return approval

    async def list_eval_records(self, project_id: str) -> list[EvalRecord]:
        result = await self.db.execute(
            select(EvalRecord)
            .where(EvalRecord.project_id == project_id)
            .order_by(EvalRecord.created_at.desc())
        )
        return list(result.scalars().all())

    async def count_eval_records_for_owner_since(self, owner_id: str, since: datetime) -> int:
        stmt = (
            select(func.count(EvalRecord.id))
            .join(OrchestratorProject, EvalRecord.project_id == OrchestratorProject.id)
            .where(OrchestratorProject.owner_id == owner_id, EvalRecord.created_at >= since)
        )
        result = await self.db.execute(stmt)
        return int(result.scalar_one() or 0)

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
                "by_task": [],
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

        task_rows = await self.db.execute(
            select(
                TaskRun.task_id,
                func.coalesce(func.sum(TaskRun.estimated_cost_micros), 0),
                func.coalesce(func.sum(TaskRun.token_total), 0),
                func.count(TaskRun.id),
            )
            .where(base_filter, TaskRun.task_id.isnot(None))
            .group_by(TaskRun.task_id)
        )
        task_cost_rows = task_rows.all()
        task_names: dict[str, str] = {}
        if task_cost_rows:
            task_ids = [row[0] for row in task_cost_rows]
            task_result = await self.db.execute(
                select(OrchestratorTask.id, OrchestratorTask.title).where(
                    OrchestratorTask.id.in_(task_ids)
                )
            )
            task_names = {str(task_id): str(title) for task_id, title in task_result.all()}
        by_task = [
            {
                "task_id": task_id,
                "name": task_names.get(str(task_id), "Task"),
                "cost_usd": int(cost) / 1_000_000,
                "tokens": int(tokens),
                "runs": int(runs),
            }
            for task_id, cost, tokens, runs in task_cost_rows
        ]
        by_task.sort(key=lambda item: item["cost_usd"], reverse=True)

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
            "by_task": by_task,
            "by_provider": by_provider,
            "most_expensive_runs": most_expensive,
            "total_cost_micros": int(total_cost_micros or 0),
            "total_tokens": int(total_tokens or 0),
        }

    async def summarize_portfolio_for_owner(self, owner_id: str) -> list[dict[str, Any]]:
        """Per-project counts for multi-repo / portfolio dashboards (owner-scoped)."""
        pr = await self.db.execute(
            select(
                OrchestratorProject.id, OrchestratorProject.name, OrchestratorProject.slug
            ).where(OrchestratorProject.owner_id == owner_id)
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

    async def count_runs_by_status_for_owner(self, owner_id: str) -> dict[str, int]:
        result = await self.db.execute(
            select(TaskRun.status, func.count())
            .join(OrchestratorProject, TaskRun.project_id == OrchestratorProject.id)
            .where(OrchestratorProject.owner_id == owner_id)
            .group_by(TaskRun.status)
        )
        return {str(status): int(count or 0) for status, count in result.all()}

    async def get_latest_run_id_for_owner(self, owner_id: str) -> str | None:
        result = await self.db.execute(
            select(TaskRun.id)
            .join(OrchestratorProject, TaskRun.project_id == OrchestratorProject.id)
            .where(OrchestratorProject.owner_id == owner_id)
            .order_by(TaskRun.created_at.desc(), TaskRun.id.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        return str(row) if row else None

    async def load_portfolio_control_plane_bundle(
        self,
        owner_id: str,
        project_ids: Sequence[str],
        *,
        cost_since: datetime,
        stuck_before: datetime,
    ) -> dict[str, Any]:
        """Batched aggregates for portfolio control-plane (O(1) vs project count)."""
        empty: dict[str, Any] = {
            "managers": {},
            "task_status_counts": {},
            "blocked_tasks": {},
            "run_status_counts": {},
            "run_cost_30d": {},
            "run_tokens_30d": {},
            "latest_runs": {},
            "repo_link_counts": {},
            "sync_failure_counts": {},
            "ingest_failure_counts": {},
            "queued_run_count": 0,
            "active_run_count": 0,
            "stuck_runs": [],
            "pending_webhooks": [],
            "replay_backlog": [],
            "ingest_running_count": 0,
            "ingest_failed_count": 0,
        }
        if not project_ids:
            return empty

        memberships_result = await self.db.execute(
            select(ProjectAgentMembership)
            .where(ProjectAgentMembership.project_id.in_(project_ids))
            .order_by(ProjectAgentMembership.created_at.asc())
        )
        memberships = list(memberships_result.scalars().all())
        agent_ids = {m.agent_id for m in memberships if m.agent_id}
        agents_by_id: dict[str, AgentProfile] = {}
        if agent_ids:
            agents_result = await self.db.execute(
                select(AgentProfile).where(AgentProfile.id.in_(agent_ids))
            )
            agents_by_id = {a.id: a for a in agents_result.scalars().all()}
        managers: dict[str, AgentProfile | None] = {pid: None for pid in project_ids}
        memberships_by_project: dict[str, list[ProjectAgentMembership]] = {}
        for membership in memberships:
            memberships_by_project.setdefault(membership.project_id, []).append(membership)
        for pid, items in memberships_by_project.items():
            chosen = next(
                (item for item in items if item.is_default_manager),
                next((item for item in items if item.role == "manager"), None),
            )
            managers[pid] = agents_by_id.get(chosen.agent_id) if chosen else None

        task_counts_result = await self.db.execute(
            select(OrchestratorTask.project_id, OrchestratorTask.status, func.count())
            .where(OrchestratorTask.project_id.in_(project_ids))
            .group_by(OrchestratorTask.project_id, OrchestratorTask.status)
        )
        task_status_counts: dict[str, dict[str, int]] = {}
        for pid, status, count in task_counts_result.all():
            task_status_counts.setdefault(str(pid), {})[str(status)] = int(count or 0)

        blocked_cap = max(6, min(6 * len(project_ids), 240))
        blocked_result = await self.db.execute(
            select(OrchestratorTask)
            .where(
                OrchestratorTask.project_id.in_(project_ids),
                OrchestratorTask.status == "blocked",
            )
            .order_by(OrchestratorTask.updated_at.desc())
            .limit(blocked_cap)
        )
        blocked_tasks: dict[str, list[OrchestratorTask]] = {}
        for task in blocked_result.scalars().all():
            bucket = blocked_tasks.setdefault(task.project_id, [])
            if len(bucket) < 6:
                bucket.append(task)

        run_counts_result = await self.db.execute(
            select(TaskRun.project_id, TaskRun.status, func.count())
            .where(TaskRun.project_id.in_(project_ids))
            .group_by(TaskRun.project_id, TaskRun.status)
        )
        run_status_counts: dict[str, dict[str, int]] = {}
        queued_run_count = 0
        active_run_count = 0
        for pid, status, count in run_counts_result.all():
            run_status_counts.setdefault(str(pid), {})[str(status)] = int(count or 0)
            if status == "queued":
                queued_run_count += int(count or 0)
            elif status in {"in_progress", "blocked"}:
                active_run_count += int(count or 0)

        cost_result = await self.db.execute(
            select(
                TaskRun.project_id,
                func.coalesce(func.sum(TaskRun.estimated_cost_micros), 0),
                func.coalesce(func.sum(TaskRun.token_total), 0),
            )
            .where(TaskRun.project_id.in_(project_ids), TaskRun.created_at >= cost_since)
            .group_by(TaskRun.project_id)
        )
        run_cost_30d: dict[str, float] = {}
        run_tokens_30d: dict[str, int] = {}
        for pid, cost_micros, tokens in cost_result.all():
            run_cost_30d[str(pid)] = float(cost_micros or 0) / 1_000_000
            run_tokens_30d[str(pid)] = int(tokens or 0)

        latest_subq = (
            select(
                TaskRun.project_id.label("project_id"),
                func.max(TaskRun.created_at).label("max_created"),
            )
            .where(TaskRun.project_id.in_(project_ids))
            .group_by(TaskRun.project_id)
            .subquery()
        )
        latest_result = await self.db.execute(
            select(TaskRun).join(
                latest_subq,
                and_(
                    TaskRun.project_id == latest_subq.c.project_id,
                    TaskRun.created_at == latest_subq.c.max_created,
                ),
            )
        )
        latest_runs: dict[str, TaskRun] = {}
        for run in latest_result.scalars().all():
            latest_runs.setdefault(run.project_id, run)

        repo_result = await self.db.execute(
            select(ProjectRepositoryLink.project_id, func.count())
            .where(ProjectRepositoryLink.project_id.in_(project_ids))
            .group_by(ProjectRepositoryLink.project_id)
        )
        repo_link_counts = {str(pid): int(c or 0) for pid, c in repo_result.all()}

        sync_fail_result = await self.db.execute(
            select(GithubRepository.project_id, func.count())
            .select_from(GithubSyncEvent)
            .join(GithubRepository, GithubSyncEvent.repository_id == GithubRepository.id)
            .join(GithubConnection, GithubRepository.connection_id == GithubConnection.id)
            .where(
                GithubConnection.owner_id == owner_id,
                GithubRepository.project_id.in_(project_ids),
                GithubSyncEvent.status.in_(["failed", "error"]),
            )
            .group_by(GithubRepository.project_id)
        )
        sync_failure_counts = {str(pid): int(c or 0) for pid, c in sync_fail_result.all()}

        ingest_fail_result = await self.db.execute(
            select(MemoryIngestJob.project_id, func.count())
            .where(
                MemoryIngestJob.owner_id == owner_id,
                MemoryIngestJob.project_id.in_(project_ids),
                MemoryIngestJob.status == "failed",
            )
            .group_by(MemoryIngestJob.project_id)
        )
        ingest_failure_counts = {str(pid): int(c or 0) for pid, c in ingest_fail_result.all()}

        stuck_result = await self.db.execute(
            select(TaskRun)
            .where(
                TaskRun.project_id.in_(project_ids),
                TaskRun.status.in_(["in_progress", "blocked"]),
                func.coalesce(TaskRun.started_at, TaskRun.created_at) <= stuck_before,
            )
            .order_by(func.coalesce(TaskRun.started_at, TaskRun.created_at).asc())
            .limit(100)
        )
        stuck_runs = list(stuck_result.scalars().all())

        pending_wh_result = await self.db.execute(
            select(GithubSyncEvent)
            .join(GithubRepository, GithubSyncEvent.repository_id == GithubRepository.id)
            .join(GithubConnection, GithubRepository.connection_id == GithubConnection.id)
            .where(
                GithubConnection.owner_id == owner_id,
                GithubRepository.project_id.in_(project_ids),
                GithubSyncEvent.status.in_(["queued", "pending"]),
            )
            .order_by(GithubSyncEvent.created_at.asc())
            .limit(200)
        )
        pending_webhooks = list(pending_wh_result.scalars().all())

        candidate_result = await self.db.execute(
            select(GithubSyncEvent)
            .join(GithubRepository, GithubSyncEvent.repository_id == GithubRepository.id)
            .join(GithubConnection, GithubRepository.connection_id == GithubConnection.id)
            .where(
                GithubConnection.owner_id == owner_id,
                GithubRepository.project_id.in_(project_ids),
                GithubSyncEvent.status.in_(["queued", "pending", "failed", "error"]),
            )
            .order_by(GithubSyncEvent.created_at.desc())
            .limit(200)
        )
        replay_backlog = [
            event
            for event in candidate_result.scalars().all()
            if (
                ((event.payload_json or {}).get("_webhook_meta") or {}).get("replay_history")
                or "replay" in str(event.action or "").lower()
            )
        ][:100]

        ingest_status_result = await self.db.execute(
            select(MemoryIngestJob.status, func.count())
            .where(
                MemoryIngestJob.owner_id == owner_id,
                MemoryIngestJob.project_id.in_(project_ids),
                MemoryIngestJob.status.in_(["running", "failed"]),
            )
            .group_by(MemoryIngestJob.status)
        )
        ingest_running_count = 0
        ingest_failed_count = 0
        for status, count in ingest_status_result.all():
            if status == "running":
                ingest_running_count = int(count or 0)
            elif status == "failed":
                ingest_failed_count = int(count or 0)

        return {
            "managers": managers,
            "task_status_counts": task_status_counts,
            "blocked_tasks": blocked_tasks,
            "run_status_counts": run_status_counts,
            "run_cost_30d": run_cost_30d,
            "run_tokens_30d": run_tokens_30d,
            "latest_runs": latest_runs,
            "repo_link_counts": repo_link_counts,
            "sync_failure_counts": sync_failure_counts,
            "ingest_failure_counts": ingest_failure_counts,
            "queued_run_count": queued_run_count,
            "active_run_count": active_run_count,
            "stuck_runs": stuck_runs,
            "pending_webhooks": pending_webhooks,
            "replay_backlog": replay_backlog,
            "ingest_running_count": ingest_running_count,
            "ingest_failed_count": ingest_failed_count,
        }

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

    async def list_observability_events_for_owner(
        self, owner_id: str, since: datetime
    ) -> list[tuple[str, str | None, str, dict[str, Any]]]:
        """Load the small event projection needed for owner-scoped analytics.

        The projection deliberately excludes messages and raw model output. It
        keeps the analytics endpoint useful without turning it into a transcript
        export or exposing prompt/completion content.
        """
        stmt = (
            select(RunEvent.run_id, RunEvent.task_id, RunEvent.event_type, RunEvent.payload_json)
            .join(TaskRun, RunEvent.run_id == TaskRun.id)
            .join(OrchestratorProject, TaskRun.project_id == OrchestratorProject.id)
            .where(OrchestratorProject.owner_id == owner_id, RunEvent.created_at >= since)
        )
        result = await self.db.execute(stmt)
        return [
            (
                str(run_id),
                str(task_id) if task_id else None,
                str(event_type),
                payload if isinstance(payload, dict) else {},
            )
            for run_id, task_id, event_type, payload in result.all()
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

    async def create_semantic_memory_entry(self, **kwargs: Any) -> SemanticMemoryEntry:
        item = SemanticMemoryEntry(**kwargs)
        self.db.add(item)
        await self.db.flush()
        return item

    async def get_semantic_memory_entry(
        self, owner_id: str, entry_id: str
    ) -> SemanticMemoryEntry | None:
        result = await self.db.execute(
            select(SemanticMemoryEntry).where(
                SemanticMemoryEntry.id == entry_id,
                SemanticMemoryEntry.owner_id == owner_id,
                SemanticMemoryEntry.deleted_at.is_(None),
                or_(
                    SemanticMemoryEntry.expires_at.is_(None),
                    SemanticMemoryEntry.expires_at > func.now(),
                ),
            )
        )
        return result.scalar_one_or_none()

    async def list_semantic_memory_entries(
        self,
        owner_id: str,
        *,
        source_task_id: str | None = None,
        project_id: str | None = None,
        entry_type: str | None = None,
        namespace_prefix: str | None = None,
        agent_id: str | None = None,
        company_id: str | None = None,
        scope: str | None = None,
        search: str | None = None,
        limit: int = 100,
        include_expired: bool = False,
    ) -> list[SemanticMemoryEntry]:
        stmt = select(SemanticMemoryEntry).where(
            SemanticMemoryEntry.owner_id == owner_id,
            SemanticMemoryEntry.deleted_at.is_(None),
        )
        if not include_expired:
            stmt = stmt.where(
                or_(
                    SemanticMemoryEntry.expires_at.is_(None),
                    SemanticMemoryEntry.expires_at > func.now(),
                )
            )
        if project_id is not None:
            stmt = stmt.where(SemanticMemoryEntry.project_id == project_id)
        if company_id is not None:
            stmt = stmt.where(SemanticMemoryEntry.company_id == company_id)
        if agent_id is not None:
            stmt = stmt.where(SemanticMemoryEntry.agent_id == agent_id)
        if scope is not None:
            stmt = stmt.where(SemanticMemoryEntry.scope == scope)
        if source_task_id is not None:
            stmt = stmt.where(SemanticMemoryEntry.source_task_id == source_task_id)
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
        r2 = await self.db.execute(
            select(SemanticMemoryEntry).where(SemanticMemoryEntry.id.in_(ids))
        )
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

    async def get_memory_ingest_job(self, job_id: str) -> MemoryIngestJob | None:
        res = await self.db.execute(select(MemoryIngestJob).where(MemoryIngestJob.id == job_id))
        return res.scalar_one_or_none()

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

    async def get_episodic_archive_manifest(
        self, owner_id: str, project_id: str, archive_id: str
    ) -> EpisodicArchiveManifest | None:
        res = await self.db.execute(
            select(EpisodicArchiveManifest).where(
                EpisodicArchiveManifest.id == archive_id,
                EpisodicArchiveManifest.owner_id == owner_id,
                EpisodicArchiveManifest.project_id == project_id,
            )
        )
        return res.scalar_one_or_none()

    async def list_episodic_index_rows_for_sources(
        self, project_id: str, source_kind: str, source_ids: Sequence[str]
    ) -> list[EpisodicSearchIndex]:
        unique = [item for item in dict.fromkeys(source_ids) if item]
        if not unique:
            return []
        result = await self.db.execute(
            select(EpisodicSearchIndex).where(
                EpisodicSearchIndex.project_id == project_id,
                EpisodicSearchIndex.source_kind == source_kind,
                EpisodicSearchIndex.source_id.in_(unique),
            )
        )
        return list(result.scalars().all())

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

    async def collect_durable_engine_evidence(
        self, owner_id: str, since: datetime
    ) -> dict[str, Any]:
        """Owner-scoped production signals for durable-engine migration review (ARCH-001)."""
        from datetime import UTC

        now = datetime.now(UTC)
        window = now - since
        total_result = await self.db.execute(
            select(func.count(TaskRun.id))
            .join(OrchestratorProject, TaskRun.project_id == OrchestratorProject.id)
            .where(OrchestratorProject.owner_id == owner_id, TaskRun.created_at >= since)
        )
        total_runs = int(total_result.scalar() or 0)

        duration = func.coalesce(TaskRun.completed_at, now) - func.coalesce(
            TaskRun.started_at, TaskRun.created_at
        )
        base_stmt = (
            select(func.count())
            .select_from(TaskRun)
            .join(OrchestratorProject, TaskRun.project_id == OrchestratorProject.id)
            .where(OrchestratorProject.owner_id == owner_id, TaskRun.created_at >= since)
        )
        over_48h = int(
            (
                await self.db.execute(base_stmt.where(duration > timedelta(hours=48)))
            ).scalar()
            or 0
        )
        over_7d = int(
            (
                await self.db.execute(base_stmt.where(duration > timedelta(days=7)))
            ).scalar()
            or 0
        )

        event_counts = dict(
            await self.aggregate_run_events_by_type_for_owner(owner_id, since)
        )
        workflow_recovery_events = int(event_counts.get("workflow_recovery") or 0)
        workflow_signal_events = int(event_counts.get("workflow_signal_queued") or 0)

        wf_key = "durable_workflow_v1"
        from sqlalchemy import Integer, cast

        resume_json = TaskRun.checkpoint_json[wf_key]["resume_count"].astext
        recovery_json = TaskRun.checkpoint_json[wf_key]["recovery_count"].astext
        runs_high_resume = int(
            (
                await self.db.execute(
                    base_stmt.where(cast(resume_json, Integer) >= 2)
                )
            ).scalar()
            or 0
        )
        runs_high_recovery = int(
            (
                await self.db.execute(
                    base_stmt.where(cast(recovery_json, Integer) >= 2)
                )
            ).scalar()
            or 0
        )

        queue_failure_runs = int(
            (
                await self.db.execute(
                    base_stmt.where(
                        or_(
                            TaskRun.error_message.ilike("%celery%"),
                            TaskRun.error_message.ilike("%broker%"),
                            TaskRun.error_message.ilike("%redis%"),
                            TaskRun.error_message.ilike("%queue%"),
                        )
                    )
                )
            ).scalar()
            or 0
        )

        stale_recovery_events = 0
        for _run_id, _task_id, event_type, payload in await self.list_observability_events_for_owner(
            owner_id, since
        ):
            if event_type != "workflow_recovery":
                continue
            if isinstance(payload, dict) and payload.get("stale_after_seconds") is not None:
                stale_recovery_events += 1

        return {
            "window_start": since.isoformat(),
            "window_end": now.isoformat(),
            "window_days": max(1, int(window.total_seconds() // 86400)),
            "total_runs": total_runs,
            "runs_over_48h": over_48h,
            "runs_over_7d": over_7d,
            "workflow_recovery_events": workflow_recovery_events,
            "workflow_signal_events": workflow_signal_events,
            "runs_high_resume_count": runs_high_resume,
            "runs_high_recovery_count": runs_high_recovery,
            "stale_in_progress_recoveries": stale_recovery_events,
            "queue_failure_runs": queue_failure_runs,
            "manual_cross_language_requirement": 0,
        }
