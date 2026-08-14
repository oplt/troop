"""Shared token and cost estimation for AI / orchestration provider calls."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from backend.modules.orchestration._helpers import _provider_type_aliases

if TYPE_CHECKING:
    from backend.modules.orchestration.models import ModelCapability, ProviderConfig


def estimate_tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / 4))


def estimate_cost_micros(
    provider: ProviderConfig | None,
    input_tokens: int,
    output_tokens: int,
    *,
    model_name: str | None = None,
    capabilities: list[ModelCapability] | None = None,
) -> int:
    # Ollama and built-in local heuristic are not metered like cloud APIs; using generic defaults
    # ($/1k from capability fallbacks) falsely trips expensive-model approval for models like qwen3:4b.
    if provider is not None and str(getattr(provider, "provider_type", None) or "").strip().lower() in {
        "ollama",
        "local",
    }:
        return 0
    capability = None
    if model_name and capabilities:
        capability = next(
            (
                item
                for item in capabilities
                if item.model_slug == model_name
                and (
                    provider is None
                    or item.provider_id == getattr(provider, "id", None)
                    or item.provider_type in _provider_type_aliases(provider.provider_type)
                )
            ),
            None,
        )
    if capability:
        cost_in = float(capability.cost_per_1k_input)
        cost_out = float(capability.cost_per_1k_output)
    elif provider and provider.metadata_json:
        cost_in = float(provider.metadata_json.get("cost_per_1k_input", 1.0))
        cost_out = float(provider.metadata_json.get("cost_per_1k_output", 2.0))
    else:
        cost_in, cost_out = 1.0, 2.0
    return int((input_tokens / 1000.0 * cost_in + output_tokens / 1000.0 * cost_out) * 1_000_000)
