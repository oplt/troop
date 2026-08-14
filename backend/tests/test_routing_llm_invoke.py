"""Behavioral tests for routing llm_invoke pure helpers."""

from __future__ import annotations

import httpx
from fastapi import HTTPException

from backend.modules.orchestration.models import ProviderConfig
from backend.modules.orchestration.services.routing.llm_invoke import (
    attempt_budget_exhausted,
    build_model_candidates,
    build_provider_failover_chain,
    filter_model_candidates_by_policy,
    filter_provider_chain_by_policy,
    filter_provider_chain_offline_local,
    format_routing_attempt_error,
    llm_attempt_budget,
    summarize_provider_chain_for_error,
)


def test_format_routing_attempt_error_http_detail():
    exc = HTTPException(status_code=502, detail="upstream refused")
    assert format_routing_attempt_error(exc) == "upstream refused"


def test_format_routing_attempt_error_httpx_timeout():
    exc = httpx.ReadTimeout("read timed out")
    text = format_routing_attempt_error(exc)
    assert "timed out" in text.lower()
    assert "timeout_seconds" in text


def test_build_model_candidates_dedupes_and_respects_failover_flag():
    candidates = build_model_candidates(
        target_model="gpt-4",
        fallback_model="gpt-4",
        offline_local_only=False,
        local_model_slug="llama3",
        provider_failover_enabled=False,
    )
    assert candidates == ["gpt-4"]


def test_build_model_candidates_offline_local_only():
    candidates = build_model_candidates(
        target_model=None,
        fallback_model=None,
        offline_local_only=True,
        local_model_slug="llama3",
    )
    assert candidates == ["llama3", None]


def test_filter_model_candidates_by_policy():
    allowed = {"gpt-4", "claude-3"}
    filtered = filter_model_candidates_by_policy(
        ["gpt-4", "unknown", None],
        allowed_model_slugs=allowed,
        enforce=True,
    )
    assert filtered == ["gpt-4", None]


def _provider(
    *,
    pid: str,
    name: str,
    provider_type: str = "openai_compatible",
    enabled: bool = True,
) -> ProviderConfig:
    return ProviderConfig(
        id=pid,
        owner_id="owner-1",
        name=name,
        provider_type=provider_type,
        is_enabled=enabled,
    )


def test_build_provider_failover_chain_caps_and_skips_disabled():
    primary = _provider(pid="p1", name="Primary")
    extras = [
        _provider(pid="p2", name="Backup"),
        _provider(pid="p3", name="Disabled", enabled=False),
        _provider(pid="p4", name="Extra"),
    ]
    chain = build_provider_failover_chain(
        primary,
        extras,
        failover_enabled=True,
        failover_max=2,
    )
    assert [p.id if p else None for p in chain] == ["p1", "p2"]


def test_filter_provider_chain_offline_local_only():
    chain: list[ProviderConfig | None] = [
        _provider(pid="p1", name="Cloud", provider_type="openai_compatible"),
        _provider(pid="p2", name="Local", provider_type="ollama"),
    ]
    filtered = filter_provider_chain_offline_local(chain, offline_local_only=True)
    assert len(filtered) == 1
    assert filtered[0] is not None
    assert filtered[0].provider_type == "ollama"


def test_filter_provider_chain_by_policy():
    chain: list[ProviderConfig | None] = [
        _provider(pid="p1", name="Cloud", provider_type="OpenAI_Compatible"),
        None,
    ]
    filtered = filter_provider_chain_by_policy(
        chain,
        allowed_provider_types={"openai_compatible"},
        enforce=True,
    )
    assert filtered == [chain[0], None]


def test_summarize_provider_chain_for_error_includes_null_local():
    chain: list[ProviderConfig | None] = [None]
    assert "local-heuristic" in summarize_provider_chain_for_error(chain)


def test_attempt_budget_exhausted_uses_settings_floor():
    budget = llm_attempt_budget()
    assert budget >= 1
    assert attempt_budget_exhausted(budget - 1, budget) is False
    assert attempt_budget_exhausted(budget, budget) is True
