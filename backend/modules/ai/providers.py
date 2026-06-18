from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx
from fastapi import HTTPException

from backend.core.cache import (
    embedding_cache_key,
    get_cached_embeddings,
    set_cached_embeddings,
)
from backend.core.config import settings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ProviderGenerateRequest:
    model: str
    system_prompt: str
    user_prompt: str
    response_format: str
    temperature: float


@dataclass(slots=True)
class ProviderGenerateResult:
    provider_key: str
    model: str
    output_text: str
    output_json: dict | None
    input_tokens: int
    output_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class BaseAiProvider:
    key = "base"

    async def generate(self, request: ProviderGenerateRequest) -> ProviderGenerateResult:
        raise NotImplementedError

    async def stream_generate(self, request: ProviderGenerateRequest) -> AsyncIterator[str]:
        result = await self.generate(request)
        if result.output_text:
            yield result.output_text

    async def embed_texts(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        raise NotImplementedError


def _estimate_tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / 4))


def _hash_embedding(text: str, dimensions: int = 32) -> list[float]:
    values: list[float] = []
    for index in range(dimensions):
        digest = hashlib.sha256(f"{index}:{text}".encode()).digest()
        integer = int.from_bytes(digest[:8], "big")
        values.append(((integer % 2000) / 1000.0) - 1.0)
    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    return [value / norm for value in values]


def _line_value_after_prefix(text: str, prefix: str) -> str | None:
    needle = prefix.lower()
    for raw in text.splitlines():
        line = raw.strip()
        if line.lower().startswith(needle):
            rest = line[len(prefix) :].lstrip(" \t:-")
            return rest[:500] if rest else None
    return None


def _heuristic_json_payload(*, model: str, system_prompt: str, user_prompt: str) -> dict:
    """Minimal JSON when no remote LLM runs: no invented answers, only task-derived labels + explicit stub flag."""
    prompt = user_prompt.strip()
    system = system_prompt.strip()
    title = _line_value_after_prefix(prompt, "Task title:") or _line_value_after_prefix(prompt, "task title:")
    desc = _line_value_after_prefix(prompt, "Task description:") or _line_value_after_prefix(prompt, "task description:")
    stub_notice = (
        "No remote language model executed this step (local heuristic / missing provider). "
        "Configure an OpenAI-compatible, Anthropic, or Ollama provider on the project to get real LLM output."
    )
    short_summary = (title or "Task").strip()
    if desc:
        short_summary = f"{short_summary}: {desc.strip()[:220]}".strip()
    if len(short_summary) > 280:
        short_summary = short_summary[:277] + "…"

    return {
        "provider": "local",
        "model": model,
        "summary": short_summary or "No live model output.",
        "system_context": system[:400],
        "local_heuristic": True,
        "stub_notice": stub_notice,
        "tool_calls": [],
        "sub_tasks": [],
    }


class LocalHeuristicProvider(BaseAiProvider):
    key = "local"

    async def generate(self, request: ProviderGenerateRequest) -> ProviderGenerateResult:
        prompt = request.user_prompt.strip()
        system = request.system_prompt.strip()
        summary = prompt[:1500]
        if request.response_format == "json":
            payload = _heuristic_json_payload(
                model=request.model,
                system_prompt=system,
                user_prompt=prompt,
            )
            output_text = json.dumps(payload, indent=2)
            output_json = payload
        else:
            output_text = (
                f"[{request.model}] Heuristic response\n\n"
                f"System context:\n{system[:400] or 'None'}\n\n"
                f"User prompt:\n{summary}"
            )
            output_json = None
        return ProviderGenerateResult(
            provider_key=self.key,
            model=request.model,
            output_text=output_text,
            output_json=output_json,
            # Local heuristic is a fallback stub, not billable model usage.
            input_tokens=0,
            output_tokens=0,
        )

    async def embed_texts(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        return [_hash_embedding(text) for text in texts]


class OpenAIProvider(BaseAiProvider):
    key = "openai"

    async def generate(self, request: ProviderGenerateRequest) -> ProviderGenerateResult:
        if not settings.OPENAI_API_KEY:
            raise HTTPException(status_code=422, detail="OPENAI_API_KEY is not configured")
        async with httpx.AsyncClient(timeout=60.0, base_url=settings.OPENAI_BASE_URL) as client:
            response = await client.post(
                "/chat/completions",
                headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                json={
                    "model": request.model,
                    "temperature": request.temperature,
                    "response_format": {"type": "json_object"}
                    if request.response_format == "json"
                    else {"type": "text"},
                    "messages": [
                        {"role": "system", "content": request.system_prompt},
                        {"role": "user", "content": request.user_prompt},
                    ],
                },
            )
        if response.status_code >= 400:
            raise HTTPException(
                status_code=502,
                detail=f"OpenAI request failed: {response.text[:300]}",
            )
        payload = response.json()
        output_text = payload["choices"][0]["message"]["content"]
        output_json = None
        if request.response_format == "json":
            try:
                output_json = json.loads(output_text)
            except json.JSONDecodeError:
                output_json = {"raw": output_text}
        usage = payload.get("usage", {})
        return ProviderGenerateResult(
            provider_key=self.key,
            model=request.model,
            output_text=output_text,
            output_json=output_json,
            input_tokens=int(usage.get("prompt_tokens", 0)),
            output_tokens=int(usage.get("completion_tokens", 0)),
        )

    async def stream_generate(self, request: ProviderGenerateRequest) -> AsyncIterator[str]:
        if not settings.OPENAI_API_KEY:
            raise HTTPException(status_code=422, detail="OPENAI_API_KEY is not configured")
        async with httpx.AsyncClient(timeout=60.0, base_url=settings.OPENAI_BASE_URL) as client:
            async with client.stream(
                "POST",
                "/chat/completions",
                headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                json={
                    "model": request.model,
                    "temperature": request.temperature,
                    "stream": True,
                    "messages": [
                        {"role": "system", "content": request.system_prompt},
                        {"role": "user", "content": request.user_prompt},
                    ],
                },
            ) as response:
                if response.status_code >= 400:
                    body = await response.aread()
                    raise HTTPException(
                        status_code=502,
                        detail=f"OpenAI stream failed: {body.decode(errors='replace')[:300]}",
                    )
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    payload_text = line[6:].strip()
                    if payload_text == "[DONE]":
                        break
                    try:
                        payload = json.loads(payload_text)
                        delta = payload["choices"][0]["delta"].get("content")
                    except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                        continue
                    if delta:
                        yield str(delta)

    async def embed_texts(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        if not settings.OPENAI_API_KEY:
            raise HTTPException(status_code=422, detail="OPENAI_API_KEY is not configured")
        async with httpx.AsyncClient(timeout=60.0, base_url=settings.OPENAI_BASE_URL) as client:
            response = await client.post(
                "/embeddings",
                headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                json={
                    "model": model or settings.OPENAI_EMBEDDING_MODEL,
                    "input": texts,
                },
            )
        if response.status_code >= 400:
            raise HTTPException(
                status_code=502,
                detail=f"OpenAI embeddings request failed: {response.text[:300]}",
            )
        payload = response.json()
        return [item["embedding"] for item in payload.get("data", [])]


class AnthropicProvider(BaseAiProvider):
    key = "anthropic"

    async def generate(self, request: ProviderGenerateRequest) -> ProviderGenerateResult:
        if not settings.ANTHROPIC_API_KEY:
            raise HTTPException(status_code=422, detail="ANTHROPIC_API_KEY is not configured")
        async with httpx.AsyncClient(timeout=60.0, base_url=settings.ANTHROPIC_BASE_URL) as client:
            response = await client.post(
                "/messages",
                headers={
                    "x-api-key": settings.ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                },
                json={
                    "model": request.model,
                    "system": request.system_prompt,
                    "temperature": request.temperature,
                    "max_tokens": settings.AI_MAX_OUTPUT_TOKENS,
                    "messages": [{"role": "user", "content": request.user_prompt}],
                },
            )
        if response.status_code >= 400:
            raise HTTPException(
                status_code=502,
                detail=f"Anthropic request failed: {response.text[:300]}",
            )
        payload = response.json()
        content_blocks = payload.get("content", [])
        output_text = "\n".join(
            block.get("text", "") for block in content_blocks if block.get("type") == "text"
        )
        output_json = None
        if request.response_format == "json":
            try:
                output_json = json.loads(output_text)
            except json.JSONDecodeError:
                output_json = {"raw": output_text}
        usage = payload.get("usage", {})
        return ProviderGenerateResult(
            provider_key=self.key,
            model=request.model,
            output_text=output_text,
            output_json=output_json,
            input_tokens=int(usage.get("input_tokens", 0)),
            output_tokens=int(usage.get("output_tokens", 0)),
        )

    async def embed_texts(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        if settings.AI_EMBEDDING_PROVIDER == "local":
            return await LocalHeuristicProvider().embed_texts(texts)
        raise HTTPException(
            status_code=422,
            detail="Anthropic embeddings are not configured. Use the local embedding provider.",
        )


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
        fresh_vectors = await provider.embed_texts(missing_texts, model=model_name)
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
