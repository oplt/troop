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
        cursor_created_at=None,
        cursor_id: str | None = None,
    ):
        run = await self.get_run(user, run_id)
        return await self.repo.list_run_events(
            run.id,
            limit=limit,
            cursor_created_at=cursor_created_at,
            cursor_id=cursor_id,
        )

    async def list_run_trace(
        self,
        user: User,
        run_id: str,
        *,
        limit: int | None = None,
        cursor_created_at=None,
        cursor_id: str | None = None,
    ):
        from backend.core.config import settings
        from backend.modules.orchestration._helpers import resolve_query_limit
        from backend.modules.orchestration.execution.run_trace import RunTraceService

        run = await self.get_run(user, run_id)
        effective_limit = resolve_query_limit(
            limit,
            default=settings.RUN_EVENTS_DEFAULT_LIMIT,
            maximum=settings.RUN_EVENTS_MAX_LIMIT,
        )
        return await RunTraceService(self.db).list_run_trace_spans(
            run,
            limit=effective_limit,
            cursor_created_at=cursor_created_at,
            cursor_id=cursor_id,
        )
