"""Resolve configured LLM providers for workforce intelligence."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.orchestration.models import ProviderConfig
from backend.modules.orchestration.repository import OrchestrationRepository


async def resolve_owner_provider(
    db: AsyncSession,
    owner_id: str,
    *,
    project_id: str | None = None,
) -> ProviderConfig | None:
    """Pick the owner's default provider (project-scoped preferred, then global)."""
    repo = OrchestrationRepository(db)
    providers = await repo.list_providers(owner_id, project_id)
    if not providers:
        return None
    # list_providers already orders is_default desc
    for provider in providers:
        if getattr(provider, "is_active", True) is False:
            continue
        return provider
    return providers[0]
