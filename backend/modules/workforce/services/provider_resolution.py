"""Resolve configured LLM providers for workforce intelligence via ModelCapability."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.orchestration.models import ModelCapability, ProviderConfig
from backend.modules.orchestration.repository import OrchestrationRepository

_PURPOSE_HINTS: dict[str, dict[str, object]] = {
    "task_analysis": {
        "prefer_cheap": True,
        "need_structured": True,
        "need_tools": False,
    },
    "skill_generation": {
        "prefer_cheap": False,
        "need_structured": True,
        "need_tools": False,
    },
    "project_analysis": {
        "prefer_cheap": False,
        "need_structured": True,
        "need_tools": False,
    },
    "default": {
        "prefer_cheap": False,
        "need_structured": False,
        "need_tools": False,
    },
}


def _cap_score(
    provider: ProviderConfig,
    caps: list[ModelCapability],
    *,
    hints: dict[str, object],
) -> tuple:
    """Score provider using ModelCapability rows (cost, context, structured/tools)."""
    model = (provider.default_model or "").strip().lower()
    matching = [
        c
        for c in caps
        if c.is_active
        and (
            (c.provider_id and c.provider_id == provider.id)
            or (not c.provider_id and c.provider_type == provider.provider_type)
        )
        and (not model or c.model_slug.lower() == model or model in c.model_slug.lower())
    ]
    if not matching and provider.default_model:
        # Fallback: any active cap for provider type
        matching = [c for c in caps if c.is_active and c.provider_type == provider.provider_type]

    best = matching[0] if matching else None
    meta = dict((best.metadata_json if best else None) or {})
    structured = bool(meta.get("supports_structured_output", best.supports_tools if best else True))
    supports_tools = bool(best.supports_tools) if best else False
    if hints.get("need_structured") and not structured:
        return (0, 0, 0, 0, 0)
    if hints.get("need_tools") and not supports_tools:
        return (0, 0, 0, 0, 0)

    cost = float(best.cost_per_1k_input) if best else 1.0
    ctx = int(best.max_context_tokens) if best else 0
    score_default = 1 if getattr(provider, "is_default", False) else 0
    score_project = 1 if getattr(provider, "project_id", None) else 0
    # prefer_cheap → invert cost; otherwise prefer lower cost still but weaker
    if hints.get("prefer_cheap"):
        cost_score = max(0, int(1000 - cost * 1000))
    else:
        # Prefer capable (higher context) with moderate cost
        cost_score = max(0, int(ctx / 1000) - int(cost * 100))
    health = 1 if getattr(provider, "is_active", True) else 0
    return (health, score_default, score_project, cost_score, 1 if best else 0)


async def resolve_owner_provider(
    db: AsyncSession,
    owner_id: str,
    *,
    project_id: str | None = None,
    purpose: str = "default",
) -> ProviderConfig | None:
    """Pick a provider using ModelCapability routing signals when available."""
    repo = OrchestrationRepository(db)
    providers = await repo.list_providers(owner_id, project_id)
    active = [p for p in providers if getattr(p, "is_active", True) is not False]
    if not active:
        return None

    hints = _PURPOSE_HINTS.get(purpose) or _PURPOSE_HINTS["default"]
    try:
        caps = await repo.list_model_capabilities()
    except Exception:
        caps = []

    if caps:
        ranked = sorted(
            active,
            key=lambda p: _cap_score(p, caps, hints=hints),
            reverse=True,
        )
        top = ranked[0]
        if _cap_score(top, caps, hints=hints)[0] > 0:
            return top

    # Fallback: default flag then first active
    for provider in active:
        if getattr(provider, "is_default", False):
            return provider
    return active[0]
