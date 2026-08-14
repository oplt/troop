"""Shared helpers for native connector providers."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.workforce.models import ConnectorDefinition, ConnectorInstallation


async def load_installation(
    db: AsyncSession,
    installation_id: str,
    *,
    provider_slug: str | None = None,
    owner_id: str | None = None,
) -> ConnectorInstallation:
    query = (
        select(ConnectorInstallation, ConnectorDefinition)
        .join(
            ConnectorDefinition,
            ConnectorDefinition.id == ConnectorInstallation.connector_definition_id,
        )
        .where(ConnectorInstallation.id == installation_id)
    )
    if owner_id is not None:
        query = query.where(ConnectorInstallation.owner_id == owner_id)
    if provider_slug is not None:
        query = query.where(ConnectorDefinition.slug == provider_slug)
    row = (await db.execute(query)).first()
    if row is None:
        raise ValueError(f"Connector installation not found: {installation_id}")
    return row[0]
