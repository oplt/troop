"""Resolve configured LLM providers for workforce intelligence via shared model router."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.orchestration.model_router import resolve_provider_and_model
from backend.modules.orchestration.models import ProviderConfig

_PURPOSE_REQUIREMENTS: dict[str, dict[str, bool]] = {
    "task_analysis": {"require_structured": True, "require_tools": False},
    "skill_generation": {"require_structured": True, "require_tools": False},
    "workflow_generation": {"require_structured": True, "require_tools": False},
    "project_analysis": {"require_structured": True, "require_tools": False},
    "default": {"require_structured": False, "require_tools": False},
}


async def resolve_owner_provider(
    db: AsyncSession,
    owner_id: str,
    *,
    project_id: str | None = None,
    purpose: str = "default",
) -> ProviderConfig | None:
    """Pick a provider using the shared orchestration model router."""
    hints = _PURPOSE_REQUIREMENTS.get(purpose) or _PURPOSE_REQUIREMENTS["default"]
    provider, _model = await resolve_provider_and_model(
        db,
        owner_id,
        project_id=project_id,
        purpose=purpose,
        require_tools=bool(hints.get("require_tools")),
        require_structured=bool(hints.get("require_structured")),
    )
    return provider
