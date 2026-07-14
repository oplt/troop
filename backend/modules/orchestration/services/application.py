"""Application use cases for orchestration transport adapters.

Routers and agent-facing APIs use this small contract instead of constructing
the large compatibility facade at every call site.  Domain services remain
the owners of authorization, transactions, and invariants; this layer owns
use-case composition and keeps delivery adapters interchangeable.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.identity_access.models import User
from backend.modules.orchestration.models import TaskRun
from backend.modules.orchestration.services.service import OrchestrationService


class OrchestrationApplicationService:
    """Stable application boundary for agent, task, and run use cases."""

    def __init__(self, db: AsyncSession) -> None:
        self._domain = OrchestrationService(db)

    @property
    def repo(self):
        """Expose the repository only for legacy workflow adapters.

        New use cases should be added as methods here.  The property is kept
        temporarily because the agent-plan compatibility endpoint still emits
        durable run events directly as part of its existing contract.
        """

        return self._domain.repo

    async def list_agents(self, user: User, project_id: str | None = None):
        return await self._domain.list_agents(user, project_id)

    async def create_agent(self, user: User, payload: dict[str, Any]):
        return await self._domain.create_agent(user, payload)

    async def get_agent(self, user: User, agent_id: str):
        return await self._domain.get_agent(user, agent_id)

    async def update_agent(self, user: User, agent_id: str, payload: dict[str, Any]):
        return await self._domain.update_agent(user, agent_id, payload)

    async def delete_agent(self, user: User, agent_id: str) -> None:
        await self._domain.delete_agent(user, agent_id)

    async def import_agent_markdown(
        self,
        user: User,
        *,
        content: str,
        project_id: str | None,
        existing_agent_id: str | None,
    ):
        return await self._domain.import_agent_markdown(
            user,
            content=content,
            project_id=project_id,
            existing_agent_id=existing_agent_id,
        )

    async def create_task(self, user: User, project_id: str, payload: dict[str, Any]):
        return await self._domain.create_task(user, project_id, payload)

    async def list_tasks(self, user: User, project_id: str):
        return await self._domain.list_tasks(user, project_id)

    async def get_task(self, user: User, project_id: str, task_id: str):
        return await self._domain.get_task(user, project_id, task_id)

    async def get_run(self, user: User, run_id: str) -> TaskRun:
        return await self._domain.get_run(user, run_id)

    async def cancel_run(self, user: User, run_id: str) -> TaskRun:
        return await self._domain.cancel_run(user, run_id)


__all__ = ["OrchestrationApplicationService"]
