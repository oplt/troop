from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.companies.models import Company


class CompanyRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, **kwargs: Any) -> Company:
        item = Company(**kwargs)
        self.db.add(item)
        await self.db.flush()
        return item

    async def get(self, owner_id: str, company_id: str) -> Company | None:
        res = await self.db.execute(
            select(Company).where(Company.id == company_id, Company.owner_id == owner_id)
        )
        return res.scalar_one_or_none()

    async def list_for_owner(self, owner_id: str) -> list[Company]:
        res = await self.db.execute(
            select(Company).where(Company.owner_id == owner_id).order_by(Company.created_at.asc())
        )
        return list(res.scalars().all())

    async def get_default_for_owner(self, owner_id: str) -> Company | None:
        res = await self.db.execute(
            select(Company)
            .where(Company.owner_id == owner_id)
            .order_by(Company.created_at.asc())
            .limit(1)
        )
        return res.scalar_one_or_none()

    async def find_by_slug(self, owner_id: str, slug: str) -> Company | None:
        res = await self.db.execute(
            select(Company).where(Company.owner_id == owner_id, Company.slug == slug)
        )
        return res.scalar_one_or_none()
