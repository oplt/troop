"""Fire-and-forget activation milestone hooks."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.platform.activation_milestones import ActivationMilestoneKey
from backend.modules.platform.activation_service import ActivationService


async def record_activation_for_owner(
    db: AsyncSession,
    owner_id: str,
    key: ActivationMilestoneKey,
    *,
    at: datetime | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    try:
        await ActivationService(db).record_for_owner(
            owner_id,
            key,
            at=at or datetime.now(UTC),
            resource_type=resource_type,
            resource_id=resource_id,
            metadata=metadata,
        )
    except Exception:
        # Activation telemetry must not block primary flows.
        return
