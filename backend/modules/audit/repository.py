import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.request_context import get_request_context
from backend.modules.audit.models import AuditLog


class AuditRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _merge_request_context(metadata: dict | None) -> dict:
        merged = dict(metadata or {})
        for key, value in get_request_context().as_log_fields().items():
            merged.setdefault(key, value)
        return merged

    async def log(
        self,
        action: str,
        *,
        user_id: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        metadata: dict | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            action=action,
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata_json=json.dumps(self._merge_request_context(metadata)),
        )
        self.db.add(entry)
        await self.db.flush()
        return entry

    async def list_recent(self, limit: int = 100) -> list[AuditLog]:
        result = await self.db.execute(
            select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def list_for_user(self, user_id: str, limit: int = 50) -> list[AuditLog]:
        result = await self.db.execute(
            select(AuditLog)
            .where(AuditLog.user_id == user_id)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
