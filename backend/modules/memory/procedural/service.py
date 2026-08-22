from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.identity_access.models import User
from backend.modules.memory.domain_errors import MemoryDomainError
from backend.modules.memory.models import ProceduralPlaybook
from backend.modules.projects.orchestration_models import OrchestratorProject, OrchestratorTask

ProjectLoader = Callable[[User, str], Awaitable[OrchestratorProject]]


class ProceduralMemoryService:
    """Procedural playbook lifecycle with explicit persistence and ACL access."""

    def __init__(self, db: AsyncSession, repo: Any, get_project: ProjectLoader) -> None:
        self.db = db
        self.repo = repo
        self.get_project = get_project

    async def excerpt(
        self,
        project: OrchestratorProject | None,
        task: OrchestratorTask | None,
    ) -> str:
        if not project or not task:
            return ""
        rows = await self.repo.list_procedural_playbooks(project.owner_id, project.id)
        if not rows:
            return ""
        labels = {str(item).lower() for item in (task.labels_json or [])}
        task_type = (task.task_type or "").lower()
        bits: list[str] = []
        for playbook in rows[:16]:
            tags = [str(tag).lower() for tag in (playbook.tags_json or []) if tag]
            if tags and task_type not in tags and not labels.intersection(tags):
                continue
            bits.append(
                f"**{playbook.title}** (`{playbook.slug}`):\n{(playbook.body_md or '')[:900]}"
            )
        return "\n\n".join(bits)[:2400]

    async def list_for_project(
        self,
        user: User,
        project_id: str,
    ) -> list[ProceduralPlaybook]:
        project = await self.get_project(user, project_id)
        return await self.repo.list_procedural_playbooks(project.owner_id, project_id)

    async def create_for_project(
        self,
        user: User,
        project_id: str,
        payload: dict[str, Any],
    ) -> ProceduralPlaybook:
        project = await self.get_project(user, project_id)
        slug = (
            re.sub(r"[^a-z0-9]+", "-", str(payload.get("slug") or "").lower()).strip("-")[:128]
            or "playbook"
        )
        title = str(payload.get("title") or slug).strip()[:255]
        body = str(payload.get("body_md") or "").strip()
        if not body:
            raise MemoryDomainError(422, "body_md is required")
        namespace = (
            str(payload.get("namespace") or "").strip() or f"project/{project_id}/procedural/{slug}"
        )
        tags = payload.get("tags") if isinstance(payload.get("tags"), list) else []
        row = await self.repo.create_procedural_playbook(
            owner_id=project.owner_id,
            project_id=project_id,
            slug=slug,
            title=title,
            body_md=body,
            version=int(payload.get("version") or 1),
            tags_json=list(tags),
            namespace=namespace[:512],
        )
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def update_for_project(
        self,
        user: User,
        project_id: str,
        playbook_id: str,
        updates: dict[str, Any],
    ) -> ProceduralPlaybook:
        project = await self.get_project(user, project_id)
        row = await self.repo.get_procedural_playbook(project.owner_id, project_id, playbook_id)
        if row is None:
            raise MemoryDomainError(404, "Playbook not found")
        field_mappings = {
            "title": ("title", lambda value: str(value)[:255]),
            "body_md": ("body_md", str),
            "tags": ("tags_json", list),
            "namespace": ("namespace", lambda value: str(value)[:512]),
            "version": ("version", int),
        }
        for request_field, (model_field, coerce) in field_mappings.items():
            if request_field in updates and updates[request_field] is not None:
                setattr(row, model_field, coerce(updates[request_field]))
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def delete_for_project(
        self,
        user: User,
        project_id: str,
        playbook_id: str,
    ) -> None:
        project = await self.get_project(user, project_id)
        row = await self.repo.get_procedural_playbook(project.owner_id, project_id, playbook_id)
        if row is None:
            raise MemoryDomainError(404, "Playbook not found")
        await self.db.delete(row)
        await self.db.commit()
