from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import AsyncIterator

from fastapi import HTTPException

from backend.core.cache import (
    cache_singleflight,
    embedding_cache_key,
    get_cached_embeddings,
    set_cached_embeddings,
)
from backend.core.config import settings
from backend.core.logging import get_logger
from backend.modules.ai.gateway.pricing import estimate_tokens
from backend.modules.ai.providers.implementations import (
    AnthropicProvider,
    BaseAiProvider,
    LocalHeuristicProvider,
    OpenAIProvider,
    ProviderGenerateRequest,
    ProviderGenerateResult,
)
from backend.modules.observability.metrics import record_embed_tokens

logger = get_logger(__name__)


class AiProviderRegistry:
    def __init__(self):
        self._providers = {
            provider.key: provider
            for provider in (
                LocalHeuristicProvider(),
                OpenAIProvider(),
                AnthropicProvider(),
            )
        }

    def get(self, key: str | None) -> BaseAiProvider:
        provider_key = (key or settings.AI_DEFAULT_PROVIDER).strip().lower()
        if settings.is_production and provider_key == "openai" and not settings.OPENAI_API_KEY:
            raise HTTPException(
                status_code=503,
                detail="OPENAI_API_KEY is required when AI_DEFAULT_PROVIDER=openai in production",
            )
        provider = self._providers.get(provider_key)
        if not provider:
            raise HTTPException(status_code=404, detail=f"Unknown AI provider: {provider_key}")
        return provider

    async def embed_texts(self, texts: list[str], *, model: str | None = None) -> list[list[float]]:
        if not texts:
            return []
        provider = self.get(settings.AI_EMBEDDING_PROVIDER)
        model_name = model or (
            settings.OPENAI_EMBEDDING_MODEL
            if provider.key == "openai"
            else settings.AI_LOCAL_MODEL_NAME
        )
        keys = [embedding_cache_key(text, model_name) for text in texts]
        cached = await get_cached_embeddings(keys)
        missing_indices = [index for index, value in enumerate(cached) if value is None]
        if not missing_indices:
            return [value for value in cached if value is not None]

        results: list[list[float] | None] = list(cached)
        missing_texts = [texts[index] for index in missing_indices]
        batch_key = (
            "embedding-fill:"
            + hashlib.sha256(
                json.dumps(
                    {"model": model_name, "keys": [keys[index] for index in missing_indices]},
                    sort_keys=True,
                ).encode()
            ).hexdigest()
        )
        try:
            fresh_vectors = await cache_singleflight(
                batch_key,
                lambda: provider.embed_texts(missing_texts, model=model_name),
            )
        except Exception:
            record_embed_tokens(
                provider=provider.key,
                tokens=sum(estimate_tokens(text) for text in missing_texts),
                outcome="error",
            )
            raise
        record_embed_tokens(
            provider=provider.key,
            tokens=sum(estimate_tokens(text) for text in missing_texts),
            outcome="success",
        )
        to_store: list[tuple[str, list[float]]] = []
        for index, vector in zip(missing_indices, fresh_vectors, strict=True):
            results[index] = vector
            to_store.append((keys[index], vector))
        await set_cached_embeddings(to_store)
        return [vector for vector in results if vector is not None]

    async def generate(
        self,
        request: ProviderGenerateRequest,
        *,
        provider_key: str | None = None,
        max_attempts: int = 3,
    ) -> ProviderGenerateResult:
        provider = self.get(provider_key or settings.AI_DEFAULT_PROVIDER)
        delay = 0.25
        last_error: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                return await provider.generate(request)
            except HTTPException:
                raise
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "ai_generate_retry provider=%s attempt=%s error=%s",
                    provider.key,
                    attempt,
                    exc,
                )
                if attempt >= max_attempts:
                    break
                await asyncio.sleep(delay)
                delay *= 2
        raise HTTPException(
            status_code=502,
            detail=f"AI generation failed after {max_attempts} attempts: {last_error}",
        )

    async def stream_generate(
        self,
        request: ProviderGenerateRequest,
        *,
        provider_key: str | None = None,
    ) -> AsyncIterator[str]:
        provider = self.get(provider_key or settings.AI_DEFAULT_PROVIDER)
        async for chunk in provider.stream_generate(request):
            yield chunk
