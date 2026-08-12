"""Shared model/provider routing for orchestration and workforce.

Candidates are ranked as (provider, exact ModelCapability) pairs.
Hard requirements (structured output / tools) never fall back silently.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.orchestration.models import ModelCapability, ProviderConfig
from backend.modules.orchestration.repository import OrchestrationRepository

_PURPOSE_DEFAULTS: dict[str, dict[str, bool]] = {
    "task_analysis": {"prefer_cheap": True, "require_structured": True, "require_tools": False},
    "skill_generation": {"prefer_cheap": False, "require_structured": True, "require_tools": False},
    "project_analysis": {"prefer_cheap": False, "require_structured": True, "require_tools": False},
    "default": {"prefer_cheap": False, "require_structured": False, "require_tools": False},
}


@dataclass(frozen=True)
class ModelRouteResult:
    provider: ProviderConfig | None
    model_slug: str | None
    fallback_reason: str | None = None
    capability_id: str | None = None


def _exact_capabilities(
    provider: ProviderConfig,
    caps: list[ModelCapability],
) -> list[ModelCapability]:
    """Return capabilities that exactly match this provider (+ optional default model)."""
    default_model = (provider.default_model or "").strip().lower()
    exact: list[ModelCapability] = []
    for cap in caps:
        if not cap.is_active:
            continue
        if cap.provider_id and cap.provider_id != provider.id:
            continue
        if not cap.provider_id and cap.provider_type != provider.provider_type:
            continue
        if default_model and cap.model_slug.lower() != default_model:
            # Prefer exact default model; still allow other provider models as separate candidates
            pass
        exact.append(cap)
    # Prefer default model first when present
    if default_model:
        preferred = [c for c in exact if c.model_slug.lower() == default_model]
        others = [c for c in exact if c.model_slug.lower() != default_model]
        return preferred + others
    return exact


def _cap_satisfies(
    cap: ModelCapability,
    *,
    require_tools: bool,
    require_structured: bool,
) -> bool:
    meta = dict(cap.metadata_json or {})
    structured = bool(meta.get("supports_structured_output", cap.supports_tools))
    if require_structured and not structured:
        return False
    if require_tools and not cap.supports_tools:
        return False
    return True


def _rank_candidate(
    provider: ProviderConfig,
    cap: ModelCapability,
    *,
    prefer_cheap: bool,
) -> tuple[int, ...]:
    meta = dict(cap.metadata_json or {})
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
    return (
        1 if provider.is_enabled else 0,
        health,
        1 if provider.is_default else 0,
        1 if provider.project_id else 0,
        tools_bonus,
        ctx_score,
        cost_score,
        latency_score,
    )


async def resolve_provider_and_model(
    db: AsyncSession,
    owner_id: str,
    *,
    project_id: str | None = None,
    purpose: str = "default",
    require_tools: bool = False,
    require_structured: bool = False,
) -> tuple[ProviderConfig | None, str | None]:
    """Pick provider + exact model slug. Hard requirements stay hard."""
    result = await resolve_route(
        db,
        owner_id,
        project_id=project_id,
        purpose=purpose,
        require_tools=require_tools,
        require_structured=require_structured,
    )
    return result.provider, result.model_slug


async def resolve_route(
    db: AsyncSession,
    owner_id: str,
    *,
    project_id: str | None = None,
    purpose: str = "default",
    require_tools: bool = False,
    require_structured: bool = False,
) -> ModelRouteResult:
    repo = OrchestrationRepository(db)
    providers = await repo.list_providers(owner_id, project_id)
    active = [p for p in providers if p.is_enabled]
    if not active:
        return ModelRouteResult(None, None, fallback_reason="no_enabled_providers")

    hints = _PURPOSE_DEFAULTS.get(purpose) or _PURPOSE_DEFAULTS["default"]
    prefer_cheap = bool(hints.get("prefer_cheap"))
    need_structured = require_structured or bool(hints.get("require_structured"))
    need_tools = require_tools or bool(hints.get("require_tools"))

    try:
        caps = await repo.list_model_capabilities_for_owner(owner_id)
    except Exception:
        caps = []

    candidates: list[tuple[tuple[int, ...], ProviderConfig, ModelCapability]] = []
    for provider in active:
        for cap in _exact_capabilities(provider, caps):
            if not _cap_satisfies(
                cap, require_tools=need_tools, require_structured=need_structured
            ):
                continue
            rank = _rank_candidate(provider, cap, prefer_cheap=prefer_cheap)
            candidates.append((rank, provider, cap))

    if candidates:
        candidates.sort(key=lambda item: item[0], reverse=True)
        _rank, provider, cap = candidates[0]
        return ModelRouteResult(
            provider=provider,
            model_slug=cap.model_slug,
            capability_id=cap.id,
        )

    if need_tools or need_structured:
        return ModelRouteResult(
            None,
            None,
            fallback_reason=(
                "no_capability_satisfies_hard_requirements:"
                f"structured={need_structured},tools={need_tools}"
            ),
        )

    # Soft path only when no hard requirements: prefer default provider model.
    for provider in active:
        if provider.is_default and provider.default_model:
            return ModelRouteResult(provider, provider.default_model, fallback_reason="default_flag")
    fallback = active[0]
    return ModelRouteResult(
        fallback,
        fallback.default_model or None,
        fallback_reason="first_enabled_provider",
    )
