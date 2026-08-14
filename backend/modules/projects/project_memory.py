"""Project memory ingest job queries."""

from __future__ import annotations

from typing import Any

from backend.modules.identity_access.models import User


class ProjectMemoryMixin:
    async def list_project_memory_ingest_jobs(
        self, user: User, project_id: str, *, limit: int = 60
    ) -> list[dict[str, Any]]:
        await self.get_project(user, project_id)
        rows = await self.repo.list_memory_ingest_jobs_for_project(user.id, project_id, limit=limit)
        return [
            {
                "id": row.id,
                "project_id": row.project_id,
                "job_type": row.job_type,
                "status": row.status,
                "error_text": row.error_text,
                "created_at": row.created_at,
                "started_at": row.started_at,
                "finished_at": row.finished_at,
                "payload": row.payload_json or {},
            }
            for row in rows
        ]
