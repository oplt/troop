"""Shared model/provider routing for orchestration and workforce."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.orchestration.models import ModelCapability, ProviderConfig
from backend.modules.orchestration.repository import OrchestrationRepository

_PURPOSE_DEFAULTS: dict[str, dict[str, bool]] = {
    "task_analysis": {"prefer_cheap": True, "require_structured": True, "require_tools": False},
    "skill_generation": {"prefer_cheap": False, "require_structured": True, "require_tools": False},
    "project_analysis": {"prefer_cheap": False, "require_structured": True, "require_tools": False},
    "default": {"prefer_cheap": False, "require_structured": False, "require_tools": False},
}


def _matching_capabilities(
    provider: ProviderConfig,
    caps: list[ModelCapability],
    *,
    model_slug: str | None = None,
) -> list[ModelCapability]:
    model = (model_slug or provider.default_model or "").strip().lower()
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
        matching = [c for c in caps if c.is_active and c.provider_type == provider.provider_type]
    return matching


def _capability_rank(
    cap: ModelCapability | None,
    *,
    prefer_cheap: bool,
    require_tools: bool,
    require_structured: bool,
) -> tuple[int, int, int, int, int]:
    if cap is None:
        return (0, 0, 0, 0, 0)
    meta = dict(cap.metadata_json or {})
    structured = bool(meta.get("supports_structured_output", cap.supports_tools))
    if require_structured and not structured:
        return (0, 0, 0, 0, 0)
    if require_tools and not cap.supports_tools:
        return (0, 0, 0, 0, 0)

    cost = float(cap.cost_per_1k_input or 0.0) + float(cap.cost_per_1k_output or 0.0)
    ctx = int(cap.max_context_tokens or 0)
    latency_ms = int(meta.get("latency_ms") or meta.get("p50_latency_ms") or 0)
    health = 1 if meta.get("is_healthy", True) else 0
    tools_bonus = 1 if cap.supports_tools else 0

    if prefer_cheap:
        cost_score = max(0, int(1000 - cost * 500))
        ctx_score = max(0, int(ctx / 2000))
    else:
        cost_score = max(0, int(1000 - cost * 200))
        ctx_score = max(0, int(ctx / 500))
    latency_score = max(0, 500 - latency_ms) if latency_ms else 250
    return (health, tools_bonus, ctx_score, cost_score, latency_score)


def _provider_rank_key(
    provider: ProviderConfig,
    caps: list[ModelCapability],
    *,
    prefer_cheap: bool,
    require_tools: bool,
    require_structured: bool,
    model_slug: str | None = None,
) -> tuple:
    matching = _matching_capabilities(provider, caps, model_slug=model_slug)
    best = matching[0] if matching else None
    cap_rank = _capability_rank(
        best,
        prefer_cheap=prefer_cheap,
        require_tools=require_tools,
        require_structured=require_structured,
    )
    if cap_rank[0] == 0 and (require_tools or require_structured):
        return (0, 0, 0, 0, 0, 0)
    score_default = 1 if provider.is_default else 0
    score_project = 1 if provider.project_id else 0
    score_enabled = 1 if provider.is_enabled else 0
    return (score_enabled, cap_rank[0], score_default, score_project, *cap_rank[1:])


async def resolve_provider_and_model(
    db: AsyncSession,
    owner_id: str,
    *,
    project_id: str | None = None,
    purpose: str = "default",
    require_tools: bool = False,
    require_structured: bool = False,
) -> tuple[ProviderConfig | None, str | None]:
    """Pick provider + model slug using ModelCapability health/cost/context/tools."""
    repo = OrchestrationRepository(db)
    providers = await repo.list_providers(owner_id, project_id)
    active = [p for p in providers if p.is_enabled]
    if not active:
        return None, None

    hints = _PURPOSE_DEFAULTS.get(purpose) or _PURPOSE_DEFAULTS["default"]
    prefer_cheap = bool(hints.get("prefer_cheap"))
    need_structured = require_structured or bool(hints.get("require_structured"))
    need_tools = require_tools or bool(hints.get("require_tools"))

    try:
        caps = await repo.list_model_capabilities_for_owner(owner_id)
    except Exception:
        caps = []

    if caps:
        ranked = sorted(
            active,
            key=lambda p: _provider_rank_key(
                p,
                caps,
                prefer_cheap=prefer_cheap,
                require_tools=need_tools,
                require_structured=need_structured,
            ),
            reverse=True,
        )
        for provider in ranked:
            rank = _provider_rank_key(
                provider,
                caps,
                prefer_cheap=prefer_cheap,
                require_tools=need_tools,
                require_structured=need_structured,
            )
            if rank[0] == 0:
                continue
            matching = _matching_capabilities(provider, caps)
            model = (provider.default_model or "").strip() or (
                matching[0].model_slug if matching else None
            )
            if model:
                return provider, model

    for provider in active:
        if provider.is_default and provider.default_model:
            return provider, provider.default_model
    fallback = active[0]
    return fallback, fallback.default_model or None
