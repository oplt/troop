"""Prompt template and version management."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from backend.modules.identity_access.models import User


class AiPromptsMixin:
    async def list_prompt_templates(self, user: User):
        return await self.repo.list_prompt_templates_for_user(user.id)

    async def create_prompt_template(
        self, user: User, key: str, name: str, description: str | None
    ):
        existing = await self.repo.get_prompt_template_by_key_for_user(user.id, key)
        if existing:
            raise HTTPException(
                status_code=409,
                detail="A prompt template with this key already exists",
            )
        template = await self.repo.create_prompt_template(
            user_id=user.id,
            key=key,
            name=name,
            description=description,
        )
        await self.db.commit()
        await self.db.refresh(template)
        return template

    async def update_prompt_template(
        self, user: User, template_id: str, updates: dict[str, Any]
    ):
        template = await self.repo.get_prompt_template_for_user(user.id, template_id)
        if not template:
            raise HTTPException(status_code=404, detail="Prompt template not found")
        if "active_version_id" in updates and updates["active_version_id"]:
            version = await self.repo.get_prompt_version(updates["active_version_id"])
            if not version or version.prompt_template_id != template.id:
                raise HTTPException(
                    status_code=404,
                    detail="Prompt version not found for this template",
                )
            if not version.is_published:
                raise HTTPException(
                    status_code=422,
                    detail="Only published versions can be activated",
                )
        for field, value in updates.items():
            setattr(template, field, value)
        await self.db.commit()
        await self.db.refresh(template)
        return template

    async def create_prompt_version(self, user: User, template_id: str, payload: dict[str, Any]):
        template = await self.repo.get_prompt_template_for_user(user.id, template_id)
        if not template:
            raise HTTPException(status_code=404, detail="Prompt template not found")
        versions = await self.repo.list_prompt_versions(template.id)
        next_version_number = (versions[0].version_number + 1) if versions else 1
        version = await self.repo.create_prompt_version(
            prompt_template_id=template.id,
            version_number=next_version_number,
            provider_key=payload["provider_key"],
            model_name=payload["model_name"],
            system_prompt=payload["system_prompt"],
            user_prompt_template=payload["user_prompt_template"],
            variable_definitions_json=[
                item.model_dump() for item in payload["variable_definitions"]
            ],
            response_format=payload["response_format"],
            temperature=payload["temperature"],
            rollout_percentage=payload["rollout_percentage"],
            is_published=payload["is_published"],
            input_cost_per_million=payload["input_cost_per_million"],
            output_cost_per_million=payload["output_cost_per_million"],
            created_by_user_id=user.id,
        )
        if template.active_version_id is None and version.is_published:
            template.active_version_id = version.id
        await self.db.commit()
        await self.db.refresh(version)
        await self.db.refresh(template)
        return version

    async def update_prompt_version(
        self, user: User, template_id: str, version_id: str, updates: dict[str, Any]
    ):
        template = await self.repo.get_prompt_template_for_user(user.id, template_id)
        if not template:
            raise HTTPException(status_code=404, detail="Prompt template not found")
        version = await self.repo.get_prompt_version(version_id)
        if not version or version.prompt_template_id != template.id:
            raise HTTPException(status_code=404, detail="Prompt version not found")
        for field, value in updates.items():
            if field == "variable_definitions":
                version.variable_definitions_json = [item.model_dump() for item in value]
            else:
                setattr(version, field, value)
        await self.db.commit()
        await self.db.refresh(version)
        return version

    async def list_prompt_versions(self, user: User, template_id: str):
        template = await self.repo.get_prompt_template_for_user(user.id, template_id)
        if not template:
            raise HTTPException(status_code=404, detail="Prompt template not found")
        return await self.repo.list_prompt_versions(template.id)
