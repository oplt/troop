from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.identity_access.models import User
from backend.modules.orchestration.local_runtime import start_local_runtime
from backend.modules.orchestration.repository import OrchestrationRepository


class ProviderRuntimeService:
    """Owns permission-aware lifecycle operations for managed local providers."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = OrchestrationRepository(db)

    async def start(self, user: User, provider_id: str) -> dict[str, object]:
        provider = await self.repo.get_provider(user.id, provider_id)
        if provider is None:
            raise HTTPException(status_code=404, detail="Provider not found")
        result = await start_local_runtime(self.db, provider)
        await self.db.commit()
        return result


__all__ = ["ProviderRuntimeService"]
