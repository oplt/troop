"""Pure helpers for LLM routing, failover, and attempt budgeting."""

from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException

from backend.core.config import settings
from backend.modules.orchestration.models import ProviderConfig

GLOBAL_POLICY_ROUTING_RULES: list[dict[str, Any]] = [
    {
        "field": "task.labels",
        "operator": "contains",
        "value": "triage",
        "route_to": "cheap_model_slug",
    },
    {
        "field": "task.task_type",
        "operator": "equals",
        "value": "architecture",
        "route_to": "strong_model_slug",
    },
    {
        "field": "project.is_sensitive",
        "operator": "equals",
        "value": True,
        "route_to": "local_model_slug",
    },
]


def format_routing_attempt_error(exc: BaseException) -> str:
    if isinstance(exc, HTTPException):
        detail = exc.detail
        if isinstance(detail, str) and detail.strip():
            return detail.strip()
        if detail is not None:
            try:
                dumped = json.dumps(detail) if not isinstance(detail, str) else detail
            except (TypeError, ValueError):
                dumped = repr(detail)
            if str(dumped).strip():
                return str(dumped).strip()
        code = getattr(exc, "status_code", "") or ""
        return f"HTTPException(status_code={code})"
    exc_mod = getattr(type(exc), "__module__", "")
    exc_type = type(exc).__name__
    if exc_mod.startswith("httpx") and exc_type in {
        "ReadTimeout",
        "ConnectTimeout",
        "WriteTimeout",
        "PoolTimeout",
    }:
        raw = str(exc).strip()
        if not raw:
            raw = exc_type
        return (
            f"{raw}: HTTP client timed out waiting for the LLM provider response "
            f"(raise timeout_seconds on the provider, use a faster model, or fix base_url if the API "
            f"cannot reach Ollama — e.g. Docker vs localhost)."
        )
    if exc_mod.startswith("httpx") and exc_type == "ConnectError":
        raw = str(exc).strip() or exc_type
        return f"{raw}: could not connect to the LLM provider (wrong base_url, firewall, or service down)."
    text = str(exc).strip()
    if text:
        return text
    return repr(exc)


def summarize_provider_chain_for_error(chain: list[ProviderConfig | None]) -> str:
    parts: list[str] = []
    for item in chain:
        if item is None:
            parts.append("null→local-heuristic")
        else:
            short_id = (item.id or "")[:10]
            ptype = str(item.provider_type or "").strip().lower()
            base = getattr(item, "base_url", None) or ""
            base_hint = f", base_url={base!r}" if base else ""
            parts.append(f"{item.name!r}({ptype}:{short_id}{base_hint})")
    return ", ".join(parts) if parts else "(empty)"


def build_model_candidates(
    *,
    target_model: str | None,
    fallback_model: str | None,
    offline_local_only: bool,
    local_model_slug: str | None,
    provider_failover_enabled: bool | None = None,
) -> list[str | None]:
    candidates: list[str | None] = []
    for candidate in (target_model, fallback_model):
        if candidate and candidate not in candidates:
            candidates.append(candidate)
    if not candidates:
        candidates = [None]
    if offline_local_only and not target_model:
        candidates = [local_model_slug, None]
    if provider_failover_enabled is False:
        candidates = candidates[:1]
    return candidates


def filter_model_candidates_by_policy(
    candidates: list[str | None],
    *,
    allowed_model_slugs: set[str],
    enforce: bool,
) -> list[str | None]:
    if not enforce or not allowed_model_slugs:
        return candidates
    filtered = [c for c in candidates if c is None or c in allowed_model_slugs]
    return filtered


def build_provider_failover_chain(
    target_provider: ProviderConfig | None,
    project_providers: list[ProviderConfig],
    *,
    failover_enabled: bool,
    failover_max: int | None = None,
) -> list[ProviderConfig | None]:
    chain: list[ProviderConfig | None] = [target_provider]
    if not failover_enabled or target_provider is None:
        return chain
    seen_ids = {target_provider.id}
    cap = max(1, int(failover_max or settings.ORCHESTRATION_PROVIDER_FAILOVER_MAX))
    for provider in project_providers:
        if len(chain) >= cap:
            break
        if provider.is_enabled and provider.id not in seen_ids:
            seen_ids.add(provider.id)
            chain.append(provider)
    return chain


def filter_provider_chain_offline_local(
    chain: list[ProviderConfig | None],
    *,
    offline_local_only: bool,
) -> list[ProviderConfig | None]:
    if not offline_local_only:
        return chain
    filtered = [p for p in chain if p is None or p.provider_type in {"ollama", "local"}]
    return filtered or [None]


def filter_provider_chain_by_policy(
    chain: list[ProviderConfig | None],
    *,
    allowed_provider_types: set[str],
    enforce: bool,
) -> list[ProviderConfig | None]:
    if not enforce or not allowed_provider_types:
        return chain
    return [p for p in chain if p is None or p.provider_type.lower() in allowed_provider_types]


def llm_attempt_budget() -> int:
    return max(1, int(settings.ORCHESTRATION_LLM_ATTEMPT_BUDGET))


def attempt_budget_exhausted(attempts_used: int, budget: int | None = None) -> bool:
    cap = budget if budget is not None else llm_attempt_budget()
    return attempts_used >= cap
