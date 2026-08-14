"""Run list/get query helpers."""

from __future__ import annotations

from fastapi import HTTPException

from backend.modules.identity_access.models import User


class ExecutionRunQueriesMixin:
    async def list_task_runs(
        self,
        user: User,
        project_id: str | None = None,
        *,
        limit: int | None = None,
        cursor_created_at=None,
        cursor_id: str | None = None,
    ):
        return await self.repo.list_runs(
            user.id,
            project_id,
            limit=limit,
            cursor_created_at=cursor_created_at,
            cursor_id=cursor_id,
        )

    async def get_run(self, user: User, run_id: str):
        run = await self.repo.get_run(user.id, run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        return run
    async def list_run_events(
        self,
        user: User,
        run_id: str,
        *,
        limit: int | None = None,
        offset: int = 0,
    ):
        run = await self.get_run(user, run_id)
        return await self.repo.list_run_events(run.id, limit=limit, offset=offset)
