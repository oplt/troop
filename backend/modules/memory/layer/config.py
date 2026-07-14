from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.core.config import settings
from backend.modules.memory.settings import merge_memory_settings


@dataclass(frozen=True, slots=True)
class MemoryConfig:
    enabled: bool = True
    provider: str = "semantic_pgvector"
    default_search_limit: int = 5
    extraction_enabled: bool = True
    llm_extraction_enabled: bool = False
    dedup_enabled: bool = True
    min_extraction_confidence: float = 0.45
    log_latency: bool = True
    default_ttl_days: int = 0
    max_ttl_days: int = 3650
    context_max_tokens: int = 700

    @classmethod
    def from_settings(cls, project_settings_json: dict[str, Any] | None = None) -> MemoryConfig:
        ms = merge_memory_settings(project_settings_json)
        layer = ms.get("layer") if isinstance(ms.get("layer"), dict) else {}
        return cls(
            enabled=bool(getattr(settings, "MEMORY_LAYER_ENABLED", True))
            and bool(layer.get("enabled", ms.get("memory_layer_enabled", True))),
            provider=str(getattr(settings, "MEMORY_PROVIDER", "semantic_pgvector")),
            default_search_limit=int(
                layer.get("default_search_limit")
                or getattr(settings, "MEMORY_DEFAULT_SEARCH_LIMIT", 5)
            ),
            extraction_enabled=bool(
                layer.get(
                    "extraction_enabled",
                    getattr(settings, "MEMORY_EXTRACTION_ENABLED", True),
                )
            ),
            llm_extraction_enabled=bool(
                layer.get(
                    "llm_extraction_enabled",
                    getattr(settings, "MEMORY_LLM_EXTRACTION_ENABLED", False),
                )
            ),
            dedup_enabled=bool(
                layer.get("dedup_enabled", getattr(settings, "MEMORY_DEDUP_ENABLED", True))
            ),
            min_extraction_confidence=float(
                layer.get(
                    "min_extraction_confidence",
                    getattr(settings, "MEMORY_MIN_EXTRACTION_CONFIDENCE", 0.45),
                )
            ),
            log_latency=bool(layer.get("log_latency", True)),
            default_ttl_days=max(
                0,
                int(
                    layer.get(
                        "default_ttl_days",
                        ms.get("default_ttl_days", getattr(settings, "MEMORY_DEFAULT_TTL_DAYS", 0)),
                    )
                ),
            ),
            max_ttl_days=max(
                1,
                int(
                    layer.get(
                        "max_ttl_days",
                        ms.get("max_ttl_days", getattr(settings, "MEMORY_MAX_TTL_DAYS", 3650)),
                    )
                ),
            ),
            context_max_tokens=max(
                64,
                int(
                    layer.get(
                        "context_max_tokens",
                        ms.get(
                            "context_max_tokens",
                            getattr(settings, "MEMORY_CONTEXT_MAX_TOKENS", 700),
                        ),
                    )
                ),
            ),
        )


def resolve_memory_config(project_settings_json: dict[str, Any] | None = None) -> MemoryConfig:
    return MemoryConfig.from_settings(project_settings_json)
