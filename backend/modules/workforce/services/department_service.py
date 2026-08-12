"""Department service for workforce organization."""

from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.companies.repository import CompanyRepository
from backend.modules.workforce.models import Department
from backend.modules.workforce.repository import WorkforceRepository

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-]*$")


def _normalize_slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9-]+", "-", value.strip().lower()).strip("-")
    return cleaned[:255]


class DepartmentService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = WorkforceRepository(db)
        self.company_repo = CompanyRepository(db)

    async def create(
        self,
        owner_id: str,
        company_id: str,
        *,
        name: str,
        slug: str,
        description: str | None = None,
        parent_department_id: str | None = None,
        default_knowledge_policy_json: dict[str, Any] | None = None,
        default_tool_policy_json: dict[str, Any] | None = None,
        default_model_policy_json: dict[str, Any] | None = None,
        default_approval_policy_json: dict[str, Any] | None = None,
        budget_policy_json: dict[str, Any] | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> Department:
        company = await self.company_repo.get(owner_id, company_id)
        if company is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="company not found")

        slug_norm = _normalize_slug(slug)
        if not _SLUG_RE.match(slug_norm):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid slug")

        if await self.repo.find_department_by_slug(company_id, slug_norm):
            raise HTTPException(status.HTTP_409_CONFLICT, detail="slug exists")

        if parent_department_id:
            parent = await self.repo.get_department(parent_department_id, company_id)
            if parent is None:
                raise HTTPException(
                    status.HTTP_404_NOT_FOUND, detail="parent department not found"
                )

        dept = await self.repo.create_department(
            company_id=company_id,
            name=name.strip(),
            slug=slug_norm,
            description=description or "",
            parent_department_id=parent_department_id,
            default_knowledge_policy_json=default_knowledge_policy_json or {},
            default_tool_policy_json=default_tool_policy_json or {},
            default_model_policy_json=default_model_policy_json or {},
            default_approval_policy_json=default_approval_policy_json or {},
            budget_policy_json=budget_policy_json or {},
            metadata_json=metadata_json or {},
        )
        await self.db.commit()
        return dept

    async def update(
        self,
        owner_id: str,
        company_id: str,
        department_id: str,
        **kwargs: Any,
    ) -> Department:
        company = await self.company_repo.get(owner_id, company_id)
        if company is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="company not found")

        dept = await self.repo.get_department(department_id, company_id)
        if dept is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="department not found")

        if "name" in kwargs and kwargs["name"] is not None:
            dept.name = kwargs["name"].strip()
        if "description" in kwargs:
            dept.description = kwargs["description"]
        if "parent_department_id" in kwargs:
            parent_id = kwargs["parent_department_id"]
            if parent_id:
                parent = await self.repo.get_department(parent_id, company_id)
                if parent is None:
                    raise HTTPException(
                        status.HTTP_404_NOT_FOUND, detail="parent department not found"
                    )
            dept.parent_department_id = parent_id
        if "default_knowledge_policy_json" in kwargs and kwargs["default_knowledge_policy_json"]:
            dept.default_knowledge_policy_json = kwargs["default_knowledge_policy_json"]
        if "default_tool_policy_json" in kwargs and kwargs["default_tool_policy_json"]:
            dept.default_tool_policy_json = kwargs["default_tool_policy_json"]
        if "default_model_policy_json" in kwargs and kwargs["default_model_policy_json"]:
            dept.default_model_policy_json = kwargs["default_model_policy_json"]
        if "default_approval_policy_json" in kwargs and kwargs["default_approval_policy_json"]:
            dept.default_approval_policy_json = kwargs["default_approval_policy_json"]
        if "budget_policy_json" in kwargs and kwargs["budget_policy_json"]:
            dept.budget_policy_json = kwargs["budget_policy_json"]
        if "metadata_json" in kwargs and kwargs["metadata_json"]:
            dept.metadata_json = kwargs["metadata_json"]
        if "is_archived" in kwargs and kwargs["is_archived"] is not None:
            dept.is_archived = kwargs["is_archived"]

        await self.db.commit()
        await self.db.refresh(dept)
        return dept

    async def list(
        self, owner_id: str, company_id: str, include_archived: bool = False
    ) -> list[Department]:
        company = await self.company_repo.get(owner_id, company_id)
        if company is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="company not found")
        return await self.repo.list_departments(company_id, include_archived=include_archived)

    async def get(self, owner_id: str, company_id: str, department_id: str) -> Department:
        company = await self.company_repo.get(owner_id, company_id)
        if company is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="company not found")

        dept = await self.repo.get_department(department_id, company_id)
        if dept is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="department not found")
        return dept

    async def get_for_owner(self, owner_id: str, department_id: str) -> Department:
        """Resolve department by id, verifying the company is owned by the user."""
        dept = await self.repo.get_department_by_id(department_id)
        if dept is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="department not found")
        company = await self.company_repo.get(owner_id, dept.company_id)
        if company is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="company access denied")
        return dept

    async def update_for_owner(
        self,
        owner_id: str,
        department_id: str,
        **kwargs: Any,
    ) -> Department:
        dept = await self.get_for_owner(owner_id, department_id)
        return await self.update(owner_id, dept.company_id, department_id, **kwargs)
