"""Task DAG dependency validation and readiness helpers."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from fastapi import HTTPException

from backend.modules.identity_access.models import User


def task_dependency_path_exists(
    adjacency: dict[str, Sequence[str]],
    start_id: str,
    target_id: str,
) -> bool:
    stack = [start_id]
    seen: set[str] = set()
    while stack:
        current = stack.pop()
        if current == target_id:
            return True
        if current in seen:
            continue
        seen.add(current)
        stack.extend(str(item) for item in adjacency.get(current, []))
    return False


class TaskDependenciesMixin:
    async def _validate_task_dependencies(
        self,
        project_id: str,
        task_id: str,
        dependency_ids: Sequence[str],
    ) -> None:
        normalized = [str(item) for item in dependency_ids if str(item).strip()]
        if len(set(normalized)) != len(normalized):
            raise HTTPException(
                status_code=409, detail="Duplicate task dependencies are not allowed."
            )
        if task_id in normalized:
            raise HTTPException(status_code=409, detail="A task cannot depend on itself.")

        tasks = await self.repo.list_tasks(project_id, limit=0)
        task_ids = {item.id for item in tasks}
        missing = [dep_id for dep_id in normalized if dep_id not in task_ids]
        if missing:
            raise HTTPException(
                status_code=404,
                detail=f"Dependency tasks not found in this project: {', '.join(missing[:5])}",
            )

        dependencies = await self.repo.list_task_dependencies(project_id)
        adjacency: dict[str, list[str]] = {item.id: [] for item in tasks}
        for dep in dependencies:
            adjacency.setdefault(dep.task_id, []).append(str(dep.depends_on_task_id))
        adjacency[task_id] = normalized
        for dep_id in normalized:
            if task_dependency_path_exists(adjacency, dep_id, task_id):
                raise HTTPException(
                    status_code=409,
                    detail="Dependency update would create a cycle in the task DAG.",
                )

    def _task_dependency_path_exists(
        self,
        adjacency: dict[str, Sequence[str]],
        start_id: str,
        target_id: str,
    ) -> bool:
        return task_dependency_path_exists(adjacency, start_id, target_id)

    async def _task_dependencies_met_for_run(self, task_id: str) -> bool:
        for dep in await self.repo.list_task_dependencies_for_task(task_id):
            dep_task = await self.repo.get_task_by_id(dep.depends_on_task_id)
            if dep_task and dep_task.status not in {"completed", "approved"}:
                return False
        return True

    async def list_dag_ready_tasks(self, user: User, project_id: str) -> list[dict[str, Any]]:
        await self.get_project(user, project_id)
        tasks = await self.repo.list_tasks(project_id, limit=0)
        deps_all = await self.repo.list_task_dependencies(project_id)
        dep_count: dict[str, int] = {}
        for dep in deps_all:
            dep_count[dep.task_id] = dep_count.get(dep.task_id, 0) + 1
        ready: list[dict[str, Any]] = []
        ready_statuses = {"backlog", "planned"}
        for task in tasks:
            if task.status not in ready_statuses:
                continue
            if await self.repo.task_has_active_run(project_id, task.id):
                continue
            if not await self._task_dependencies_met_for_run(task.id):
                continue
            ready.append(
                {
                    "id": task.id,
                    "title": task.title,
                    "status": task.status,
                    "dependency_count": dep_count.get(task.id, 0),
                }
            )
        return ready

    async def start_parallel_dag_ready_runs(
        self,
        user: User,
        project_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        run_mode = str(payload.get("run_mode") or "single_agent")
        limit = min(max(int(payload.get("limit") or 8), 1), 24)
        filter_ids = payload.get("task_ids")
        base_input = dict(payload.get("input_payload") or {})
        ready = await self.list_dag_ready_tasks(user, project_id)
        if filter_ids:
            filtered = {str(item) for item in filter_ids}
            ready = [row for row in ready if row["id"] in filtered]
        started: list[str] = []
        skipped: list[str] = []
        messages: list[str] = []
        for row in ready[:limit]:
            try:
                run, _warnings = await self.start_task_run(
                    user,
                    project_id,
                    row["id"],
                    {
                        "run_mode": run_mode,
                        "input_payload": {**base_input, "dag_parallel_wave": True},
                    },
                )
                started.append(run.id)
            except HTTPException as exc:
                skipped.append(row["id"])
                detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
                messages.append(f"{row['title']}: {detail}")
        return {"started_run_ids": started, "skipped_task_ids": skipped, "messages": messages}
