"""Skill service managing versioned skills and drafts."""

from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.workforce.constants import SKILL_SCOPES, SKILL_STATUSES
from backend.modules.workforce.models import Skill, SkillDraft, SkillVersion
from backend.modules.workforce.repository import WorkforceRepository

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-]*$")


def _normalize_slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9-]+", "-", value.strip().lower()).strip("-")
    return cleaned[:255]


class SkillService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = WorkforceRepository(db)

    async def create(
        self,
        owner_id: str,
        *,
        name: str,
        slug: str,
        description: str | None = None,
        scope: str = "organization",
        project_id: str | None = None,
        task_id: str | None = None,
        company_id: str | None = None,
    ) -> Skill:
        if scope not in SKILL_SCOPES:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid scope")

        slug_norm = _normalize_slug(slug)
        if not _SLUG_RE.match(slug_norm):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid slug")

        if await self.repo.find_skill_by_slug(owner_id, slug_norm):
            raise HTTPException(status.HTTP_409_CONFLICT, detail="slug exists")

        skill = await self.repo.create_skill(
            owner_id=owner_id,
            company_id=company_id,
            name=name.strip(),
            slug=slug_norm,
            description=description or "",
            scope=scope,
            status="draft",
            project_id=project_id,
            task_id=task_id,
        )
        await self.db.commit()
        return skill

    async def update(
        self, owner_id: str, skill_id: str, **kwargs: Any
    ) -> Skill:
        skill = await self.repo.get_skill(skill_id, owner_id)
        if skill is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="skill not found")

        if "name" in kwargs and kwargs["name"] is not None:
            skill.name = kwargs["name"].strip()
        if "description" in kwargs:
            skill.description = kwargs["description"]
        if "scope" in kwargs and kwargs["scope"] is not None:
            if kwargs["scope"] not in SKILL_SCOPES:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid scope")
            skill.scope = kwargs["scope"]
        if "status" in kwargs and kwargs["status"] is not None:
            if kwargs["status"] not in SKILL_STATUSES:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid status")
            skill.status = kwargs["status"]

        await self.db.commit()
        await self.db.refresh(skill)
        return skill

    async def list(self, owner_id: str, status: str | None = None) -> list[Skill]:
        return await self.repo.list_skills(owner_id, status=status)

    async def get(self, owner_id: str, skill_id: str) -> Skill:
        skill = await self.repo.get_skill(skill_id, owner_id)
        if skill is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="skill not found")
        return skill

    async def publish_draft(
        self, owner_id: str, draft_id: str, created_by: str | None = None
    ) -> Skill:
        draft = await self.repo.get_skill_draft(draft_id, owner_id)
        if draft is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="draft not found")

        if draft.skill_id:
            skill = await self.repo.get_skill(draft.skill_id, owner_id)
            if skill is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="linked skill not found")
        else:
            slug_norm = _normalize_slug(draft.slug or draft.name)
            if not _SLUG_RE.match(slug_norm):
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid slug")
            if await self.repo.find_skill_by_slug(owner_id, slug_norm):
                raise HTTPException(status.HTTP_409_CONFLICT, detail="slug exists")

            skill = await self.repo.create_skill(
                owner_id=owner_id,
                company_id=draft.company_id,
                name=draft.name,
                slug=slug_norm,
                description=draft.description,
                scope=draft.scope,
                status="draft",
                project_id=draft.source_project_id,
                task_id=draft.source_task_id,
                created_by=created_by,
            )
            draft.skill_id = skill.id

        version_number = await self.repo.get_latest_skill_version_number(skill.id) + 1
        version = await self.repo.create_skill_version(
            skill_id=skill.id,
            version_number=version_number,
            purpose=draft.purpose,
            when_to_use=draft.when_to_use,
            instructions_markdown=draft.instructions_markdown,
            input_schema_json=draft.input_schema_json,
            output_schema_json=draft.output_schema_json,
            capabilities_json=draft.capabilities_json,
            required_tools_json=draft.required_tools_json,
            knowledge_requirements_json=draft.knowledge_requirements_json,
            constraints_markdown=draft.constraints_markdown,
            risk_level=draft.risk_level,
            approval_policy_json=draft.approval_policy_json,
            examples_json=draft.examples_json,
            evaluation_criteria_json=draft.evaluation_criteria_json,
            source_type=draft.source_type,
            source_task_id=draft.source_task_id,
            source_project_id=draft.source_project_id,
            generation_metadata_json=draft.generation_metadata_json,
            is_published=True,
            created_by=created_by,
        )

        skill.current_version_id = version.id
        skill.status = "active"
        draft.status = "published"

        await self.db.commit()
        await self.db.refresh(skill)
        return skill

    async def promote_scope(
        self, owner_id: str, skill_id: str, target_scope: str, reason: str | None = None
    ) -> Skill:
        skill = await self.repo.get_skill(skill_id, owner_id)
        if skill is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="skill not found")

        if target_scope not in {"project", "organization"}:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, detail="target_scope must be project or organization"
            )

        current_hierarchy = ["task", "project", "organization"]
        if current_hierarchy.index(skill.scope) >= current_hierarchy.index(target_scope):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"cannot promote from {skill.scope} to {target_scope}",
            )

        skill.scope = target_scope
        await self.db.commit()
        await self.db.refresh(skill)
        return skill

    async def create_draft(
        self,
        owner_id: str,
        company_id: str | None = None,
        **kwargs: Any,
    ) -> SkillDraft:
        draft = await self.repo.create_skill_draft(
            owner_id=owner_id,
            company_id=company_id,
            **kwargs,
        )
        await self.db.commit()
        return draft

    async def update_draft(
        self, owner_id: str, draft_id: str, **kwargs: Any
    ) -> SkillDraft:
        draft = await self.repo.get_skill_draft(draft_id, owner_id)
        if draft is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="draft not found")

        for key, value in kwargs.items():
            if value is not None and hasattr(draft, key):
                setattr(draft, key, value)

        await self.db.commit()
        await self.db.refresh(draft)
        return draft

    async def list_drafts(self, owner_id: str, status: str | None = None) -> list[SkillDraft]:
        return await self.repo.list_skill_drafts(owner_id, status=status)

    async def get_draft(self, owner_id: str, draft_id: str) -> SkillDraft:
        draft = await self.repo.get_skill_draft(draft_id, owner_id)
        if draft is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="draft not found")
        return draft

    async def list_versions(self, owner_id: str, skill_id: str) -> list[SkillVersion]:
        skill = await self.repo.get_skill(skill_id, owner_id)
        if skill is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="skill not found")
        return await self.repo.list_skill_versions(skill_id)

    async def get_version(self, owner_id: str, version_id: str) -> SkillVersion:
        version = await self.repo.get_skill_version(version_id)
        if version is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="version not found")
        skill = await self.repo.get_skill(version.skill_id, owner_id)
        if skill is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="access denied")
        return version
