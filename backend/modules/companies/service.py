from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.companies.models import Company
from backend.modules.companies.repository import CompanyRepository

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-]*$")


def _normalize_slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9-]+", "-", value.strip().lower()).strip("-")
    return cleaned[:255]


class CompanyService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = CompanyRepository(db)

    async def get_or_create_default(self, owner_id: str) -> Company:
        existing = await self.repo.get_default_for_owner(owner_id)
        if existing is not None:
            return existing
        slug = "default"
        if await self.repo.find_by_slug(owner_id, slug):
            slug = f"default-{owner_id[:8]}"
        company = await self.repo.create(
            owner_id=owner_id,
            name="Default workspace",
            slug=slug,
            brief_markdown="",
            settings_json={},
        )
        await self.db.commit()
        return company

    async def create(
        self,
        owner_id: str,
        *,
        name: str,
        slug: str,
        brief_markdown: str = "",
        settings_json: dict[str, Any] | None = None,
    ) -> Company:
        slug_norm = _normalize_slug(slug)
        if not _SLUG_RE.match(slug_norm):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid slug")
        if await self.repo.find_by_slug(owner_id, slug_norm):
            raise HTTPException(status.HTTP_409_CONFLICT, detail="slug exists")
        company = await self.repo.create(
            owner_id=owner_id,
            name=name.strip(),
            slug=slug_norm,
            brief_markdown=brief_markdown or "",
            settings_json=settings_json or {},
        )
        await self.db.commit()
        return company

    async def update(
        self,
        owner_id: str,
        company_id: str,
        *,
        name: str | None = None,
        brief_markdown: str | None = None,
        settings_json: dict[str, Any] | None = None,
    ) -> Company:
        company = await self.repo.get(owner_id, company_id)
        if company is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="company not found")
        if name is not None:
            company.name = name.strip()
        if brief_markdown is not None:
            company.brief_markdown = brief_markdown
        if settings_json is not None:
            company.settings_json = settings_json
        await self.db.commit()
        await self.db.refresh(company)
        return company

    async def list_for(self, owner_id: str) -> list[Company]:
        return await self.repo.list_for_owner(owner_id)

    async def require(self, owner_id: str, company_id: str) -> Company:
        company = await self.repo.get(owner_id, company_id)
        if company is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="company not found")
        return company
