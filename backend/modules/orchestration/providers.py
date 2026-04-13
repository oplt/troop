from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import HTTPException

from backend.core.config import settings
from backend.modules.ai.providers import LocalHeuristicProvider
from backend.modules.orchestration.models import ProviderConfig
from backend.modules.orchestration.security import decrypt_secret


@dataclass(slots=True)
class ProviderExecutionResult:
    model_name: str
    output_text: str
    output_json: dict[str, Any] | None
    input_tokens: int
    output_tokens: int
    latency_ms: int

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


def estimate_tokens(value: str) -> int:
    return max(1, math.ceil(len(value) / 4))


async def execute_prompt(
    provider: ProviderConfig | None,
    *,
    model_name: str | None,
    system_prompt: str,
    user_prompt: str,
    response_format: str = "text",
) -> ProviderExecutionResult:
    if settings.ORCHESTRATION_OFFLINE_MODE:
        provider = None
    if provider is None or provider.provider_type == "local":
        started = time.perf_counter()
        result = await LocalHeuristicProvider().generate(
            request=type(
                "ProviderGenerateRequestCompat",
                (),
                {
                    "model": model_name or "local-heuristic",
                    "system_prompt": system_prompt,
                    "user_prompt": user_prompt,
                    "response_format": response_format,
                    "temperature": 0.2,
                },
            )()
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        return ProviderExecutionResult(
            model_name=model_name or "local-heuristic",
            output_text=result.output_text,
            output_json=result.output_json,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            latency_ms=latency_ms,
        )

    provider_type = provider.provider_type
    if provider_type in {"openai", "openai_compatible"}:
        return await _execute_openai_compatible(
            provider,
            model_name=model_name or provider.default_model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_format=response_format,
        )
    if provider_type == "ollama":
        return await _execute_ollama(
            provider,
            model_name=model_name or provider.default_model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_format=response_format,
        )
    raise HTTPException(status_code=422, detail=f"Unsupported provider type: {provider_type}")


async def test_provider(provider: ProviderConfig) -> dict[str, Any]:
    result = await execute_prompt(
        provider,
        model_name=provider.default_model,
        system_prompt="You are a connectivity probe.",
        user_prompt="Reply with the word healthy.",
    )
    return {
        "status": "healthy",
        "model_name": result.model_name,
        "preview": result.output_text[:120],
        "latency_ms": result.latency_ms,
        "total_tokens": result.total_tokens,
    }


async def list_provider_models(provider: ProviderConfig) -> list[dict[str, Any]]:
    if provider.provider_type == "ollama":
        async with httpx.AsyncClient(
            timeout=float(provider.timeout_seconds),
            base_url=provider.base_url or "http://localhost:11434",
        ) as client:
            response = await client.get("/api/tags")
        if response.status_code >= 400:
            raise HTTPException(
                status_code=502, detail=f"Ollama model discovery failed: {response.text[:300]}"
            )
        payload = response.json()
        return list(payload.get("models", []))

    models: list[dict[str, Any]] = []
    if provider.default_model:
        models.append({"name": provider.default_model, "source": "default"})
    if provider.fallback_model and provider.fallback_model not in {
        item["name"] for item in models
    }:
        models.append({"name": provider.fallback_model, "source": "fallback"})
    for item in provider.metadata_json.get("discovered_models", []):
        name = str(item.get("name") or "").strip()
        if name and name not in {existing["name"] for existing in models}:
            models.append(item)
    return models


async def _execute_openai_compatible(
    provider: ProviderConfig,
    *,
    model_name: str,
    system_prompt: str,
    user_prompt: str,
    response_format: str,
) -> ProviderExecutionResult:
    api_key = decrypt_secret(provider.encrypted_api_key)
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if provider.organization:
        headers["OpenAI-Organization"] = provider.organization
    started = time.perf_counter()
    async with httpx.AsyncClient(
        timeout=float(provider.timeout_seconds),
        base_url=provider.base_url or "https://api.openai.com/v1",
    ) as client:
        response = await client.post(
            "/chat/completions",
            headers=headers,
            json={
                "model": model_name,
                "temperature": provider.temperature,
                "max_tokens": provider.max_tokens,
                "response_format": {"type": "json_object"}
                if response_format == "json"
                else {"type": "text"},
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            },
        )
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Provider request failed: {response.text[:300]}")
    payload = response.json()
    content = payload["choices"][0]["message"]["content"]
    usage = payload.get("usage", {})
    latency_ms = int((time.perf_counter() - started) * 1000)
    parsed_json = None
    if response_format == "json":
        try:
            parsed_json = json.loads(content)
        except json.JSONDecodeError:
            parsed_json = {"raw": content}
    return ProviderExecutionResult(
        model_name=model_name,
        output_text=content,
        output_json=parsed_json,
        input_tokens=int(usage.get("prompt_tokens", estimate_tokens(system_prompt + user_prompt))),
        output_tokens=int(usage.get("completion_tokens", estimate_tokens(content))),
        latency_ms=latency_ms,
    )


async def _execute_ollama(
    provider: ProviderConfig,
    *,
    model_name: str,
    system_prompt: str,
    user_prompt: str,
    response_format: str,
) -> ProviderExecutionResult:
    started = time.perf_counter()
    async with httpx.AsyncClient(
        timeout=float(provider.timeout_seconds),
        base_url=provider.base_url or "http://localhost:11434",
    ) as client:
        response = await client.post(
            "/api/generate",
            json={
                "model": model_name,
                "system": system_prompt,
                "prompt": user_prompt,
                "stream": False,
                "format": "json" if response_format == "json" else None,
                "options": {
                    "temperature": provider.temperature,
                    "num_predict": provider.max_tokens,
                },
            },
        )
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Ollama request failed: {response.text[:300]}")
    payload = response.json()
    content = payload.get("response", "")
    parsed_json = None
    if response_format == "json":
        try:
            parsed_json = json.loads(content)
        except json.JSONDecodeError:
            parsed_json = {"raw": content}
    latency_ms = int((time.perf_counter() - started) * 1000)
    return ProviderExecutionResult(
        model_name=model_name,
        output_text=content,
        output_json=parsed_json,
        input_tokens=int(payload.get("prompt_eval_count", estimate_tokens(system_prompt + user_prompt))),
        output_tokens=int(payload.get("eval_count", estimate_tokens(content))),
        latency_ms=latency_ms,
    )
