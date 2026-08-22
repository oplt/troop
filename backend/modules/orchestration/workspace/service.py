"""Application-facing run workspace service."""

from __future__ import annotations

from backend.modules.orchestration.models import TaskRun
from backend.modules.orchestration.workspace.storage import (
    LocalWorkspaceStorage,
    StoredWorkspaceFile,
    WorkspaceStorage,
)


class RunWorkspaceError(ValueError):
    """A run cannot be represented as a task workspace."""


class RunWorkspaceService:
    def __init__(self, storage: WorkspaceStorage | None = None) -> None:
        self.storage = storage or LocalWorkspaceStorage()

    @staticmethod
    def workspace_key(run: TaskRun) -> str:
        if not run.task_id:
            raise RunWorkspaceError("Run has no task workspace.")
        return f"projects/{run.project_id}/tasks/{run.task_id}/runs/{run.id}"

    async def list_files(self, run: TaskRun) -> list[StoredWorkspaceFile]:
        return await self.storage.list_files(self.workspace_key(run))

    async def write_artifact(
        self,
        run: TaskRun,
        filename: str,
        content: str,
    ) -> StoredWorkspaceFile:
        return await self.storage.write_text(self.workspace_key(run), filename, content)


__all__ = ["RunWorkspaceError", "RunWorkspaceService"]
