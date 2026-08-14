"""Task artifact CRUD."""

from __future__ import annotations

from typing import Any

from backend.modules.identity_access.models import User
from backend.modules.projects.orchestration_models import TaskArtifact


class TaskArtifactsMixin:
    async def list_task_artifacts(self, user: User, project_id: str, task_id: str):
        await self.get_task(user, project_id, task_id)
        return await self.repo.list_task_artifacts(task_id)

    async def create_task_artifact(
        self,
        user: User,
        project_id: str,
        task_id: str,
        kind: str,
        title: str,
        content: str | None,
        metadata: dict,
    ) -> TaskArtifact:
        await self.get_task(user, project_id, task_id)
        artifact = await self.repo.create_task_artifact(
            task_id=task_id,
            kind=kind,
            title=title,
            content=content,
            metadata_json=metadata,
        )
        await self.db.commit()
        await self.db.refresh(artifact)
        return artifact
