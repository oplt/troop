"""Per-run artifact persistence."""

from __future__ import annotations

from typing import Any

from backend.modules.orchestration.models import TaskRun


class ExecutionArtifactsEvidenceMixin:
    async def _write_artifact(
        self,
        run: TaskRun,
        *,
        kind: str,
        title: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if run.task_id is None:
            return
        await self.repo.create_task_artifact(
            task_id=run.task_id,
            run_id=run.id,
            kind=kind,
            title=title,
            content=content,
            metadata_json=metadata or {},
        )
        await self.db.commit()
