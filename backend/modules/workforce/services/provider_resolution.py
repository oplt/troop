"""Resolve configured LLM providers for workforce intelligence."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.orchestration.models import ProviderConfig
from backend.modules.orchestration.repository import OrchestrationRepository

# Preferred model hints by purpose (used when provider exposes model lists).
_PURPOSE_HINTS: dict[str, dict[str, object]] = {
    "task_analysis": {"prefer_cheap": True, "structured": True},
    "skill_generation": {"prefer_strong": True, "structured": True},
    "project_analysis": {"prefer_strong": True, "structured": True},
    "default": {"prefer_cheap": False, "structured": False},
}


async def resolve_owner_provider(
    db: AsyncSession,
    owner_id: str,
    *,
    project_id: str | None = None,
    purpose: str = "default",
) -> ProviderConfig | None:
    """Pick a provider using project scope, default flag, then capability hints.

    Full cost/latency routing lives in orchestration; this selects among the
    owner's active ProviderConfig rows with purpose-aware preference.
    """
    repo = OrchestrationRepository(db)
    providers = await repo.list_providers(owner_id, project_id)
    active = [p for p in providers if getattr(p, "is_active", True) is not False]
    if not active:
        return None

    hints = _PURPOSE_HINTS.get(purpose) or _PURPOSE_HINTS["default"]

    def _score(provider: ProviderConfig) -> tuple:
        meta = getattr(provider, "metadata_json", None) or {}
        if not isinstance(meta, dict):
            meta = {}
        caps = meta.get("capabilities") or meta.get("models") or []
        model = (provider.default_model or "").lower()
        cheap_markers = ("mini", "haiku", "flash", "small", "nano")
        strong_markers = ("opus", "sonnet", "gpt-4", "large", "pro")
        is_cheap = any(m in model for m in cheap_markers)
        is_strong = any(m in model for m in strong_markers)
        structured_ok = bool(meta.get("supports_structured_output", True))
        if hints.get("structured") and not structured_ok:
            return (0, 0, 0, 0)
        score_default = 1 if getattr(provider, "is_default", False) else 0
        score_purpose = 0
        if hints.get("prefer_cheap"):
            score_purpose = 2 if is_cheap else (1 if not is_strong else 0)
        elif hints.get("prefer_strong"):
            score_purpose = 2 if is_strong else (1 if not is_cheap else 0)
        # Prefer project-scoped over global if list_providers already ordered that way
        score_project = 1 if getattr(provider, "project_id", None) else 0
        return (score_default, score_purpose, score_project, 1 if caps else 0)

    ranked = sorted(active, key=_score, reverse=True)
    return ranked[0]
