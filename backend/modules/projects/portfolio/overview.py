"""Portfolio overview and lightweight snapshot read models."""

from __future__ import annotations

from typing import Any

from backend.core.cache import get_or_set_portfolio_summary
from backend.modules.identity_access.models import User


class PortfolioOverviewMixin:
    async def get_overview(self, user: User) -> dict[str, Any]:
        ensure_catalog_seeded = getattr(self, "_ensure_catalog_seeded", None)
        if callable(ensure_catalog_seeded):
            await ensure_catalog_seeded()
        projects = await self.repo.list_projects(user.id)
        return {
            "projects": projects[:20],
            "agents": (await self.repo.list_agents(user.id))[:20],
            "active_runs": await self.repo.list_runs(user.id, limit=10),
            "pending_approvals": (await self.repo.list_approvals(user.id, "pending"))[:10],
            "github_events": (await self.repo.list_sync_events(user.id))[:10],
        }

    async def summarize_portfolio(self, user: User) -> list[dict[str, Any]]:
        async def _load() -> list[dict[str, Any]]:
            return await self.repo.summarize_portfolio_for_owner(user.id)

        cached = await get_or_set_portfolio_summary(user.id, _load)
        if isinstance(cached, list):
            return cached
        return await _load()

    async def portfolio_live_snapshot(self, user: User) -> dict[str, Any]:
        rows = await self.summarize_portfolio(user)
        return {
            "projects": rows,
            "totals": {
                "projects": len(rows),
                "active_runs": sum(int(row.get("active_runs") or 0) for row in rows),
                "open_tasks": sum(int(row.get("open_tasks") or 0) for row in rows),
                "repository_links": sum(int(row.get("repository_links") or 0) for row in rows),
            },
        }

    async def hierarchy_live_snapshot(self, user: User) -> dict[str, Any]:
        agents = await self.repo.list_agents(user.id, None)
        run_counts = await self.repo.count_runs_by_status_for_owner(user.id)
        latest_run_id = await self.repo.get_latest_run_id_for_owner(user.id)
        active = (
            int(run_counts.get("queued", 0))
            + int(run_counts.get("in_progress", 0))
            + int(run_counts.get("blocked", 0))
        )
        return {
            "agents": len(agents),
            "runs": {
                "active": active,
                "failed": int(run_counts.get("failed", 0)),
            },
            "latest_run_id": latest_run_id,
        }

    async def workspace_shell_snapshot(self, user: User) -> dict[str, Any]:
        from backend.modules.notifications.repository import NotificationsRepository

        pending_approvals = len(await self.repo.list_approvals(user.id, status="pending"))
        unread_notifications = await NotificationsRepository(self.db).count_unread_for_user(user.id)
        return {
            "pending_approvals": pending_approvals,
            "unread_notifications": unread_notifications,
        }
