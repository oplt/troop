"""Enterprise audit query and export helpers."""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.audit.models import AuditLog
from backend.modules.audit.repository import AuditRepository


def audit_log_to_dict(log: AuditLog) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    if log.metadata_json:
        try:
            parsed = json.loads(log.metadata_json)
            if isinstance(parsed, dict):
                metadata = parsed
        except json.JSONDecodeError:
            metadata = {"raw": log.metadata_json}
    return {
        "id": log.id,
        "user_id": log.user_id,
        "workspace_id": log.workspace_id,
        "action": log.action,
        "resource_type": log.resource_type,
        "resource_id": log.resource_id,
        "ip_address": log.ip_address,
        "user_agent": log.user_agent,
        "metadata": metadata,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }


class AuditExportService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = AuditRepository(db)

    async def list_filtered(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        action: str | None = None,
        user_id: str | None = None,
        resource_type: str | None = None,
        workspace_id: str | None = None,
        from_ts: datetime | None = None,
        to_ts: datetime | None = None,
    ) -> tuple[list[AuditLog], int]:
        query = select(AuditLog)
        count_query = select(func.count()).select_from(AuditLog)

        filters = []
        if action:
            filters.append(AuditLog.action == action)
        if user_id:
            filters.append(AuditLog.user_id == user_id)
        if resource_type:
            filters.append(AuditLog.resource_type == resource_type)
        if workspace_id:
            filters.append(AuditLog.workspace_id == workspace_id)
        if from_ts:
            filters.append(AuditLog.created_at >= from_ts)
        if to_ts:
            filters.append(AuditLog.created_at <= to_ts)

        if filters:
            query = query.where(*filters)
            count_query = count_query.where(*filters)

        total = int(await self.db.scalar(count_query) or 0)
        offset = max(page - 1, 0) * page_size
        result = await self.db.execute(
            query.order_by(AuditLog.created_at.desc()).offset(offset).limit(page_size)
        )
        return list(result.scalars().all()), total

    async def export_rows(
        self,
        *,
        action: str | None = None,
        user_id: str | None = None,
        resource_type: str | None = None,
        workspace_id: str | None = None,
        from_ts: datetime | None = None,
        to_ts: datetime | None = None,
        limit: int = 5000,
    ) -> list[dict[str, Any]]:
        logs, _ = await self.list_filtered(
            page=1,
            page_size=limit,
            action=action,
            user_id=user_id,
            resource_type=resource_type,
            workspace_id=workspace_id,
            from_ts=from_ts,
            to_ts=to_ts,
        )
        return [audit_log_to_dict(log) for log in logs]

    @staticmethod
    def to_ndjson(rows: list[dict[str, Any]]) -> str:
        return "\n".join(json.dumps(row, separators=(",", ":")) for row in rows) + (
            "\n" if rows else ""
        )

    @staticmethod
    def to_csv(rows: list[dict[str, Any]]) -> str:
        buffer = io.StringIO()
        fieldnames = [
            "id",
            "created_at",
            "action",
            "user_id",
            "workspace_id",
            "resource_type",
            "resource_id",
            "ip_address",
            "metadata",
        ]
        writer = csv.DictWriter(buffer, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "id": row.get("id"),
                    "created_at": row.get("created_at"),
                    "action": row.get("action"),
                    "user_id": row.get("user_id"),
                    "workspace_id": row.get("workspace_id"),
                    "resource_type": row.get("resource_type"),
                    "resource_id": row.get("resource_id"),
                    "ip_address": row.get("ip_address"),
                    "metadata": json.dumps(row.get("metadata") or {}),
                }
            )
        return buffer.getvalue()
