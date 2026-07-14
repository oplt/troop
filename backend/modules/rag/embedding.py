from __future__ import annotations

import asyncio
import time

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.modules.ai.providers import AiProviderRegistry
from backend.modules.rag.config import RagConfig
from backend.modules.rag.observability import log_rag_event

logger = get_logger(__name__)


class EmbeddingService:
    """Embedding abstraction with batching and transient retry."""

    def __init__(
        self,
        config: RagConfig | None = None,
        registry: AiProviderRegistry | None = None,
    ):
        self._config = config or RagConfig.from_settings()
        self._registry = registry or AiProviderRegistry()

    async def embed_texts(
        self,
        texts: list[str],
        *,
        model: str | None = None,
        batch_size: int | None = None,
    ) -> list[list[float]]:
        if not texts:
            return []

        size = batch_size or self._config.indexing_batch_size
        model_name = model or self._config.embedding_model or settings.OPENAI_EMBEDDING_MODEL
        out: list[list[float]] = []
        timer = time.perf_counter()

        for start in range(0, len(texts), size):
            batch = texts[start : start + size]
            vectors = await self._embed_batch_with_retry(batch, model_name)
            out.extend(vectors)

        log_rag_event(
            "embed_complete",
            count=len(texts),
            duration_ms=(time.perf_counter() - timer) * 1000,
        )
        return out

    async def _embed_batch_with_retry(
        self,
        batch: list[str],
        model: str,
        *,
        max_attempts: int = 3,
    ) -> list[list[float]]:
        delay = 0.25
        last_error: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                return await asyncio.wait_for(
                    self._registry.embed_texts(batch, model=model),
                    timeout=60.0,
                )
            except Exception as exc:
                last_error = exc
                log_rag_event(
                    "embed_retry",
                    error=str(exc),
                    count=len(batch),
                    attempt=attempt,
                    level="warning" if attempt < max_attempts else "error",
                )
                if attempt >= max_attempts:
                    break
                await asyncio.sleep(delay)
                delay *= 2
        raise RuntimeError(f"Embedding batch failed after retries: {last_error}")
