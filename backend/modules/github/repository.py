from __future__ import annotations

from datetime import datetime
from typing import Any, Sequence

from sqlalchemy import or_, select

from backend.modules.github.models import (
    GithubConnection,
    GithubIssueLink,
    GithubRepository,
    GithubSyncEvent,
)
from backend.modules.orchestration.models import RunEvent, TaskRun
from backend.modules.projects.orchestration_models import OrchestratorProject


class GithubRepositoryMixin:
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
