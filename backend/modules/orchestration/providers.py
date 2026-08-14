from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import HTTPException

from backend.core.external_http import external_headers
from backend.core.http_clients import managed_http_client
from backend.modules.ai.gateway.pricing import estimate_cost_micros, estimate_tokens
from backend.modules.ai.providers import LocalHeuristicProvider
from backend.modules.observability.decorators import observe_provider_call
from backend.modules.observability.metrics import record_llm_attempt, record_llm_cost_micros
from backend.modules.observability.tracing import llm_invoke_span, record_llm_span_result
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


def _provider_base_url(provider: ProviderConfig) -> str:
    if provider.provider_type == "openai":
        return provider.base_url or "https://api.openai.com/v1"
    if provider.provider_type == "qwen":
        return provider.base_url or "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    if provider.provider_type == "anthropic":
        return provider.base_url or "https://api.anthropic.com"
    if provider.provider_type == "ollama":
        return provider.base_url or "http://localhost:11434"
    return provider.base_url or "https://api.openai.com/v1"


def _provider_headers(provider: ProviderConfig) -> dict[str, str]:
    headers: dict[str, str] = {}
    api_key = decrypt_secret(provider.encrypted_api_key)
    if provider.provider_type == "anthropic":
        if api_key:
            headers["x-api-key"] = api_key
        headers["anthropic-version"] = "2023-06-01"
        return external_headers(headers)
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if provider.organization:
        headers["OpenAI-Organization"] = provider.organization
    return external_headers(headers)


def _bool_value(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "supported"}
    return bool(value)


def _int_value(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        digits = "".join(char for char in value if char.isdigit())
        if digits:
            return int(digits)
    return None


def _float_value(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _source_value(
    source: str, value: Any, *, missing: str = "unavailable_from_provider_api"
) -> str:
    return source if value is not None and value != "" else missing


def _provider_health(provider: ProviderConfig) -> tuple[str, int | None]:
    if provider.last_healthcheck_status:
        status = provider.last_healthcheck_status
    elif provider.is_healthy:
        status = "healthy"
    else:
        status = "unknown"
    return status, provider.last_healthcheck_latency_ms


def _request_option(request_options: dict[str, Any] | None, key: str, default: Any = None) -> Any:
    value = (request_options or {}).get(key)
    return default if value is None else value


def _request_int(request_options: dict[str, Any] | None, key: str, default: int) -> int:
    value = _int_value(_request_option(request_options, key))
    return value if value is not None and value > 0 else default


def _request_float(request_options: dict[str, Any] | None, key: str, default: float) -> float:
    value = _float_value(_request_option(request_options, key))
    return value if value is not None else default


def _capability_record(
    provider: ProviderConfig,
    *,
    model_slug: str,
    display_name: str | None,
    supports_tools: bool,
    supports_vision: bool,
    context_window: int | None,
    max_output_tokens: int | None,
    input_cost_per_1k: float | None,
    output_cost_per_1k: float | None,
    latency_p50: int | None,
    health_status: str,
    source_for_each_field: dict[str, str],
    source: str,
    override_reason: str | None = None,
    raw: dict[str, Any] | None = None,
) -> dict[str, Any]:
    verified_at = datetime.now(UTC)
    input_cost_per_1m = input_cost_per_1k * 1000 if input_cost_per_1k is not None else None
    output_cost_per_1m = output_cost_per_1k * 1000 if output_cost_per_1k is not None else None
    return {
        "provider_id": provider.id,
        "provider_type": provider.provider_type,
        "model_slug": model_slug,
        "display_name": display_name or model_slug,
        "supports_tools": supports_tools,
        "supports_tool_calling": supports_tools,
        "supports_structured_output": provider.provider_type
        in {
            "openai",
            "openai_compatible",
            "qwen",
            "ollama",
            "local",
        },
        "supports_reasoning": provider.provider_type
        in {
            "openai",
            "openai_compatible",
            "qwen",
            "anthropic",
        },
        "supports_vision": supports_vision,
        "context_window": context_window,
        "max_output_tokens": max_output_tokens,
        "input_cost_per_1k": input_cost_per_1k,
        "output_cost_per_1k": output_cost_per_1k,
        "input_cost_per_1m": input_cost_per_1m,
        "output_cost_per_1m": output_cost_per_1m,
        "latency_p50": latency_p50,
        "health_status": health_status,
        "source_for_each_field": source_for_each_field,
        "last_verified_at": verified_at,
        "override_reason": override_reason,
        "source": source,
        "raw": raw or {},
    }


async def discover_provider_capabilities(provider: ProviderConfig) -> list[dict[str, Any]]:
    if provider.provider_type == "local":
        return _discover_local_capabilities(provider)
    if provider.provider_type == "ollama":
        return await _discover_ollama_capabilities(provider)
    if provider.provider_type == "anthropic":
        return await _discover_anthropic_capabilities(provider)
    return await _discover_openai_compatible_capabilities(provider)


def _fallback_configured_capabilities(
    provider: ProviderConfig, reason: str
) -> list[dict[str, Any]]:
    status, latency = _provider_health(provider)
    models = [provider.default_model]
    if provider.fallback_model and provider.fallback_model not in models:
        models.append(provider.fallback_model)
    return [
        _capability_record(
            provider,
            model_slug=model_slug,
            display_name=model_slug,
            supports_tools=False,
            supports_vision=False,
            context_window=None,
            max_output_tokens=None,
            input_cost_per_1k=None,
            output_cost_per_1k=None,
            latency_p50=latency,
            health_status=status,
            source_for_each_field={
                "provider_id": "provider_config",
                "model_slug": "provider_config:fallback",
                "display_name": "provider_config:fallback",
                "supports_tools": "default:false:provider_api_missing",
                "supports_vision": "default:false:provider_api_missing",
                "context_window": "unavailable_from_provider_api",
                "max_output_tokens": "unavailable_from_provider_api",
                "input_cost_per_1k": "unavailable_from_provider_api",
                "output_cost_per_1k": "unavailable_from_provider_api",
                "input_cost_per_1m": "unavailable_from_provider_api",
                "output_cost_per_1m": "unavailable_from_provider_api",
                "latency_p50": _source_value("provider_healthcheck", latency),
                "health_status": "provider_healthcheck"
                if provider.last_healthcheck_at
                else "unknown",
                "last_verified_at": "sync_runtime",
                "override_reason": "sync_runtime",
            },
            source="provider_config:fallback",
            override_reason=reason,
            raw={},
        )
        for model_slug in models
        if model_slug
    ]


def _provider_metric_label(provider: ProviderConfig | None) -> str:
    if provider is None:
        return "local-heuristic"
    return str(provider.provider_type or "unknown").strip().lower() or "unknown"


async def execute_prompt(
    provider: ProviderConfig | None,
    *,
    model_name: str | None,
    system_prompt: str,
    user_prompt: str,
    response_format: str = "text",
    request_options: dict[str, Any] | None = None,
    purpose: str = "direct",
    record_metrics: bool = True,
) -> ProviderExecutionResult:
    provider_label = _provider_metric_label(provider)
    model_label = str(model_name or "unknown")
    with llm_invoke_span(purpose=purpose, provider=provider_label, model=model_label) as otel_span:
        try:
            result = await _execute_prompt_impl(
                provider,
                model_name=model_name,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_format=response_format,
                request_options=request_options,
            )
        except Exception:
            if record_metrics:
                record_llm_attempt(purpose=purpose, provider=provider_label, result="error")
            record_llm_span_result(otel_span, input_tokens=0, output_tokens=0, result="error")
            raise
    if record_metrics:
        record_llm_attempt(purpose=purpose, provider=provider_label, result="success")
        record_llm_cost_micros(
            purpose=purpose,
            provider=provider_label,
            micros=estimate_cost_micros(
                provider,
                result.input_tokens,
                result.output_tokens,
                model_name=result.model_name,
            ),
        )
    record_llm_span_result(
        otel_span,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        result="success",
    )
    return result


async def _execute_prompt_impl(
    provider: ProviderConfig | None,
    *,
    model_name: str | None,
    system_prompt: str,
    user_prompt: str,
    response_format: str = "text",
    request_options: dict[str, Any] | None = None,
) -> ProviderExecutionResult:
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

    provider_type = str(provider.provider_type or "").strip().lower()
    if provider_type in {"openai", "openai_compatible", "qwen"}:
        return await _execute_openai_compatible(
            provider,
            model_name=model_name or provider.default_model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_format=response_format,
            request_options=request_options,
        )
    if provider_type == "anthropic":
        return await _execute_anthropic(
            provider,
            model_name=model_name or provider.default_model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_format=response_format,
            request_options=request_options,
        )
    if provider_type == "ollama":
        return await _execute_ollama(
            provider,
            model_name=model_name or provider.default_model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_format=response_format,
            request_options=request_options,
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
    capabilities = await discover_provider_capabilities(provider)
    return [
        {
            "name": item["model_slug"],
            "display_name": item.get("display_name"),
            "context_window": item.get("context_window"),
            "max_output_tokens": item.get("max_output_tokens"),
            "supports_tools": item.get("supports_tools"),
            "supports_vision": item.get("supports_vision"),
            "latency_p50": item.get("latency_p50"),
            "health_status": item.get("health_status"),
            "source": item.get("source"),
            "source_for_each_field": item.get("source_for_each_field"),
        }
        for item in capabilities
    ]


@observe_provider_call("generate")
async def _execute_openai_compatible(
    provider: ProviderConfig,
    *,
    model_name: str,
    system_prompt: str,
    user_prompt: str,
    response_format: str,
    request_options: dict[str, Any] | None = None,
) -> ProviderExecutionResult:
    started = time.perf_counter()
    structured_output = bool(_request_option(request_options, "structured_output", False))
    effective_response_format = "json" if structured_output else response_format
    body: dict[str, Any] = {
        "model": model_name,
        "temperature": _request_float(request_options, "temperature", provider.temperature),
        "max_tokens": _request_int(request_options, "max_tokens", provider.max_tokens),
        "response_format": {"type": "json_object"}
        if effective_response_format == "json"
        else {"type": "text"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    reasoning_effort = str(_request_option(request_options, "reasoning_effort", "") or "").strip()
    if reasoning_effort and provider.provider_type in {"openai", "openai_compatible", "qwen"}:
        body["reasoning_effort"] = reasoning_effort
    if _request_option(request_options, "tool_calling", None) is False:
        body["tools"] = []
    async with managed_http_client(
        "orchestration-provider",
        timeout_seconds=float(provider.timeout_seconds),
        base_url=_provider_base_url(provider),
    ) as client:
        response = await client.post(
            "/chat/completions",
            headers=_provider_headers(provider),
            json=body,
        )
    if response.status_code >= 400:
        raise HTTPException(
            status_code=502, detail=f"Provider request failed: {response.text[:300]}"
        )
    payload = response.json()
    content = payload["choices"][0]["message"]["content"]
    usage = payload.get("usage", {})
    latency_ms = int((time.perf_counter() - started) * 1000)
    parsed_json = None
    if effective_response_format == "json":
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


@observe_provider_call("generate")
async def _execute_anthropic(
    provider: ProviderConfig,
    *,
    model_name: str,
    system_prompt: str,
    user_prompt: str,
    response_format: str,
    request_options: dict[str, Any] | None = None,
) -> ProviderExecutionResult:
    started = time.perf_counter()
    async with managed_http_client(
        "orchestration-provider",
        timeout_seconds=float(provider.timeout_seconds),
        base_url=_provider_base_url(provider),
    ) as client:
        response = await client.post(
            "/v1/messages",
            headers=_provider_headers(provider),
            json={
                "model": model_name,
                "system": system_prompt,
                "max_tokens": _request_int(request_options, "max_tokens", provider.max_tokens),
                "temperature": _request_float(request_options, "temperature", provider.temperature),
                "messages": [{"role": "user", "content": user_prompt}],
            },
        )
    if response.status_code >= 400:
        raise HTTPException(
            status_code=502, detail=f"Anthropic request failed: {response.text[:300]}"
        )
    payload = response.json()
    parts = payload.get("content") or []
    content = "".join(
        str(item.get("text") or "")
        for item in parts
        if isinstance(item, dict) and item.get("type") == "text"
    )
    parsed_json = None
    if (
        bool(_request_option(request_options, "structured_output", False))
        or response_format == "json"
    ):
        try:
            parsed_json = json.loads(content)
        except json.JSONDecodeError:
            parsed_json = {"raw": content}
    usage = payload.get("usage") or {}
    latency_ms = int((time.perf_counter() - started) * 1000)
    return ProviderExecutionResult(
        model_name=model_name,
        output_text=content,
        output_json=parsed_json,
        input_tokens=int(usage.get("input_tokens", estimate_tokens(system_prompt + user_prompt))),
        output_tokens=int(usage.get("output_tokens", estimate_tokens(content))),
        latency_ms=latency_ms,
    )


def _ollama_error_from_payload(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    err = payload.get("error")
    if err is None:
        return None
    return str(err).strip() or None


def _ollama_extract_text_from_payload(payload: dict[str, Any]) -> str:
    """Ollama /api/chat returns assistant text under message.content; /api/generate uses response."""
    msg = payload.get("message")
    if isinstance(msg, dict):
        raw = msg.get("content")
        if raw is not None:
            return str(raw)
    resp = payload.get("response")
    if resp is not None:
        return str(resp)
    return ""


@observe_provider_call("generate")
async def _execute_ollama(
    provider: ProviderConfig,
    *,
    model_name: str,
    system_prompt: str,
    user_prompt: str,
    response_format: str,
    request_options: dict[str, Any] | None = None,
) -> ProviderExecutionResult:
    started = time.perf_counter()
    base = _provider_base_url(provider)
    messages: list[dict[str, str]] = []
    sys_clean = (system_prompt or "").strip()
    if sys_clean:
        messages.append({"role": "system", "content": sys_clean})
    messages.append({"role": "user", "content": user_prompt})
    options = {
        "temperature": _request_float(request_options, "temperature", provider.temperature),
        "num_predict": _request_int(request_options, "max_tokens", provider.max_tokens),
    }
    want_json = (
        bool(_request_option(request_options, "structured_output", False))
        or response_format == "json"
    )

    async def _post_chat(client: httpx.AsyncClient, *, json_format: bool) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "stream": False,
            "options": options,
        }
        if json_format and want_json:
            body["format"] = "json"
        r = await client.post("/api/chat", json=body)
        if r.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"Ollama chat failed: {r.text[:300]}")
        payload = r.json()
        err = _ollama_error_from_payload(payload)
        if err:
            raise HTTPException(status_code=502, detail=f"Ollama chat failed: {err[:500]}")
        return payload

    async def _post_generate(client: httpx.AsyncClient) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": model_name,
            "system": system_prompt,
            "prompt": user_prompt,
            "stream": False,
            "options": options,
        }
        if want_json:
            body["format"] = "json"
        r = await client.post("/api/generate", json=body)
        if r.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"Ollama generate failed: {r.text[:300]}")
        payload = r.json()
        err = _ollama_error_from_payload(payload)
        if err:
            raise HTTPException(status_code=502, detail=f"Ollama generate failed: {err[:500]}")
        return payload

    payload: dict[str, Any]
    async with managed_http_client(
        "orchestration-provider", timeout_seconds=float(provider.timeout_seconds), base_url=base
    ) as client:
        payload = await _post_chat(client, json_format=True)
        content = _ollama_extract_text_from_payload(payload)
        if want_json and not str(content).strip():
            payload = await _post_chat(client, json_format=False)
            content = _ollama_extract_text_from_payload(payload)
        if not str(content).strip():
            payload = await _post_generate(client)
            content = str(payload.get("response") or "")

    if want_json and not str(content).strip():
        err = _ollama_error_from_payload(payload) if isinstance(payload, dict) else None
        hint = f"{err} " if err else ""
        raise HTTPException(
            status_code=502,
            detail=(
                f"Ollama returned no usable text for model {model_name!r} (JSON plan expected). {hint}"
                f"Pull the model if missing (`ollama pull {model_name}`), confirm the backend can reach "
                f"the Ollama base URL ({base!r}), and try a model that supports structured JSON output."
            ),
        )

    parsed_json = None
    if want_json:
        try:
            parsed_json = json.loads(content)
        except json.JSONDecodeError:
            parsed_json = {"raw": content}
    latency_ms = int((time.perf_counter() - started) * 1000)
    return ProviderExecutionResult(
        model_name=model_name,
        output_text=content,
        output_json=parsed_json,
        input_tokens=int(
            payload.get("prompt_eval_count", estimate_tokens(system_prompt + user_prompt))
        ),
        output_tokens=int(payload.get("eval_count", estimate_tokens(content))),
        latency_ms=latency_ms,
    )


async def _discover_openai_compatible_capabilities(
    provider: ProviderConfig,
) -> list[dict[str, Any]]:
    status, latency = _provider_health(provider)
    source = "provider_api:/models"
    async with managed_http_client(
        "orchestration-provider",
        timeout_seconds=float(provider.timeout_seconds),
        base_url=_provider_base_url(provider),
    ) as client:
        response = await client.get("/models", headers=_provider_headers(provider))
    if response.status_code >= 400:
        if provider.provider_type in {"qwen", "openai_compatible"}:
            return _fallback_configured_capabilities(
                provider,
                reason=f"Provider /models endpoint unavailable ({response.status_code}); using configured models until API metadata is available.",
            )
        raise HTTPException(
            status_code=502,
            detail=f"Provider model discovery failed: {response.text[:300]}",
        )
    payload = response.json()
    records = payload.get("data") or payload.get("models") or []
    discovered: list[dict[str, Any]] = []
    for item in records:
        if not isinstance(item, dict):
            continue
        model_slug = str(item.get("id") or item.get("name") or item.get("model") or "").strip()
        if not model_slug:
            continue
        modalities = item.get("input_modalities") or item.get("modalities") or []
        capabilities = item.get("capabilities") or {}
        supports_vision = False
        if isinstance(modalities, list):
            supports_vision = any(str(entry).lower() in {"image", "vision"} for entry in modalities)
        elif isinstance(capabilities, dict):
            supports_vision = _bool_value(capabilities.get("vision"))
        supports_tools = False
        if isinstance(capabilities, dict):
            supports_tools = _bool_value(
                capabilities.get("tools")
                or capabilities.get("tool_use")
                or capabilities.get("function_calling")
            )
        context_window = _int_value(item.get("context_window") or item.get("context_length"))
        max_output_tokens = _int_value(
            item.get("max_output_tokens") or item.get("output_token_limit")
        )
        input_cost_per_1k = _float_value(item.get("input_cost_per_1k"))
        output_cost_per_1k = _float_value(item.get("output_cost_per_1k"))
        override_reason = None
        if not any(
            value is not None
            for value in (context_window, max_output_tokens, input_cost_per_1k, output_cost_per_1k)
        ):
            override_reason = "Provider API omits detailed capability and pricing fields; conservative defaults applied."
        discovered.append(
            _capability_record(
                provider,
                model_slug=model_slug,
                display_name=str(item.get("display_name") or model_slug),
                supports_tools=supports_tools,
                supports_vision=supports_vision,
                context_window=context_window,
                max_output_tokens=max_output_tokens,
                input_cost_per_1k=input_cost_per_1k,
                output_cost_per_1k=output_cost_per_1k,
                latency_p50=latency,
                health_status=status,
                source_for_each_field={
                    "provider_id": "provider_config",
                    "model_slug": source,
                    "display_name": _source_value(source, item.get("display_name") or model_slug),
                    "supports_tools": _source_value(source, capabilities if capabilities else None),
                    "supports_vision": _source_value(source, modalities or capabilities),
                    "context_window": _source_value(source, context_window),
                    "max_output_tokens": _source_value(source, max_output_tokens),
                    "input_cost_per_1k": _source_value(source, input_cost_per_1k),
                    "output_cost_per_1k": _source_value(source, output_cost_per_1k),
                    "input_cost_per_1m": _source_value(source, input_cost_per_1k),
                    "output_cost_per_1m": _source_value(source, output_cost_per_1k),
                    "latency_p50": _source_value("provider_healthcheck", latency),
                    "health_status": "provider_healthcheck"
                    if provider.last_healthcheck_at
                    else "unknown",
                    "last_verified_at": "sync_runtime",
                    "override_reason": "sync_runtime" if override_reason else "none",
                },
                source=source,
                override_reason=override_reason,
                raw=item,
            )
        )
    return discovered


async def _discover_anthropic_capabilities(provider: ProviderConfig) -> list[dict[str, Any]]:
    status, latency = _provider_health(provider)
    source = "provider_api:/v1/models"
    async with managed_http_client(
        "orchestration-provider",
        timeout_seconds=float(provider.timeout_seconds),
        base_url=_provider_base_url(provider),
    ) as client:
        response = await client.get("/v1/models", headers=_provider_headers(provider))
    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"Anthropic model discovery failed: {response.text[:300]}",
        )
    payload = response.json()
    records = payload.get("data") or []
    discovered: list[dict[str, Any]] = []
    for item in records:
        if not isinstance(item, dict):
            continue
        model_slug = str(item.get("id") or "").strip()
        if not model_slug:
            continue
        override_reason = "Anthropic models API currently exposes identity metadata but not tool, vision, context, or pricing fields."
        discovered.append(
            _capability_record(
                provider,
                model_slug=model_slug,
                display_name=str(item.get("display_name") or model_slug),
                supports_tools=False,
                supports_vision=False,
                context_window=None,
                max_output_tokens=None,
                input_cost_per_1k=None,
                output_cost_per_1k=None,
                latency_p50=latency,
                health_status=status,
                source_for_each_field={
                    "provider_id": "provider_config",
                    "model_slug": source,
                    "display_name": _source_value(source, item.get("display_name") or model_slug),
                    "supports_tools": "default:false:provider_api_missing",
                    "supports_vision": "default:false:provider_api_missing",
                    "context_window": "unavailable_from_provider_api",
                    "max_output_tokens": "unavailable_from_provider_api",
                    "input_cost_per_1k": "unavailable_from_provider_api",
                    "output_cost_per_1k": "unavailable_from_provider_api",
                    "input_cost_per_1m": "unavailable_from_provider_api",
                    "output_cost_per_1m": "unavailable_from_provider_api",
                    "latency_p50": _source_value("provider_healthcheck", latency),
                    "health_status": "provider_healthcheck"
                    if provider.last_healthcheck_at
                    else "unknown",
                    "last_verified_at": "sync_runtime",
                    "override_reason": "sync_runtime",
                },
                source=source,
                override_reason=override_reason,
                raw=item,
            )
        )
    return discovered


async def _discover_ollama_capabilities(provider: ProviderConfig) -> list[dict[str, Any]]:
    status, latency = _provider_health(provider)
    async with managed_http_client(
        "orchestration-provider",
        timeout_seconds=float(provider.timeout_seconds),
        base_url=_provider_base_url(provider),
    ) as client:
        response = await client.get("/api/tags")
        if response.status_code >= 400:
            raise HTTPException(
                status_code=502, detail=f"Ollama model discovery failed: {response.text[:300]}"
            )
        payload = response.json()
        models = payload.get("models", [])
        discovered: list[dict[str, Any]] = []
        for item in models:
            if not isinstance(item, dict):
                continue
            model_slug = str(item.get("name") or item.get("model") or "").strip()
            if not model_slug:
                continue
            show_response = await client.post("/api/show", json={"model": model_slug})
            show_payload: dict[str, Any] = {}
            if show_response.status_code < 400:
                show_payload = show_response.json()
            capabilities = show_payload.get("capabilities") or []
            model_info = show_payload.get("model_info") or {}
            parameters = str(show_payload.get("parameters") or "")
            context_window = None
            for key in (
                "context_length",
                "llama.context_length",
                "gemma3.context_length",
                "qwen2.context_length",
            ):
                context_window = _int_value(model_info.get(key))
                if context_window is not None:
                    break
            if context_window is None:
                for line in parameters.splitlines():
                    parts = line.strip().split(maxsplit=1)
                    if len(parts) == 2 and parts[0] == "num_ctx":
                        context_window = _int_value(parts[1])
                        break
            max_output_tokens = None
            for line in parameters.splitlines():
                parts = line.strip().split(maxsplit=1)
                if len(parts) == 2 and parts[0] == "num_predict":
                    max_output_tokens = _int_value(parts[1])
                    break
            discovered.append(
                _capability_record(
                    provider,
                    model_slug=model_slug,
                    display_name=str(item.get("model") or item.get("name") or model_slug),
                    supports_tools=any(str(entry).lower() == "tools" for entry in capabilities),
                    supports_vision=any(str(entry).lower() == "vision" for entry in capabilities),
                    context_window=context_window,
                    max_output_tokens=max_output_tokens,
                    input_cost_per_1k=0.0,
                    output_cost_per_1k=0.0,
                    latency_p50=latency,
                    health_status=status,
                    source_for_each_field={
                        "provider_id": "provider_config",
                        "model_slug": "provider_api:/api/tags",
                        "display_name": "provider_api:/api/tags",
                        "supports_tools": _source_value("provider_api:/api/show", capabilities),
                        "supports_vision": _source_value("provider_api:/api/show", capabilities),
                        "context_window": _source_value("provider_api:/api/show", context_window),
                        "max_output_tokens": _source_value(
                            "provider_api:/api/show", max_output_tokens
                        ),
                        "input_cost_per_1k": "default:0:local_runtime",
                        "output_cost_per_1k": "default:0:local_runtime",
                        "input_cost_per_1m": "default:0:local_runtime",
                        "output_cost_per_1m": "default:0:local_runtime",
                        "latency_p50": _source_value("provider_healthcheck", latency),
                        "health_status": "provider_healthcheck"
                        if provider.last_healthcheck_at
                        else "unknown",
                        "last_verified_at": "sync_runtime",
                        "override_reason": "none",
                    },
                    source="provider_api:/api/tags+/api/show",
                    raw={"tags": item, "show": show_payload},
                )
            )
    return discovered


def _discover_local_capabilities(provider: ProviderConfig) -> list[dict[str, Any]]:
    status, latency = _provider_health(provider)
    models = [provider.default_model or "local-heuristic"]
    if provider.fallback_model and provider.fallback_model not in models:
        models.append(provider.fallback_model)
    discovered = []
    for model_slug in models:
        discovered.append(
            _capability_record(
                provider,
                model_slug=model_slug,
                display_name=model_slug,
                supports_tools=False,
                supports_vision=False,
                context_window=provider.max_tokens,
                max_output_tokens=provider.max_tokens,
                input_cost_per_1k=0.0,
                output_cost_per_1k=0.0,
                latency_p50=latency,
                health_status=status,
                source_for_each_field={
                    "provider_id": "provider_config",
                    "model_slug": "local_runtime",
                    "display_name": "local_runtime",
                    "supports_tools": "default:false:local_runtime",
                    "supports_vision": "default:false:local_runtime",
                    "context_window": "provider_config:max_tokens",
                    "max_output_tokens": "provider_config:max_tokens",
                    "input_cost_per_1k": "default:0:local_runtime",
                    "output_cost_per_1k": "default:0:local_runtime",
                    "input_cost_per_1m": "default:0:local_runtime",
                    "output_cost_per_1m": "default:0:local_runtime",
                    "latency_p50": _source_value("provider_healthcheck", latency),
                    "health_status": "provider_healthcheck"
                    if provider.last_healthcheck_at
                    else "unknown",
                    "last_verified_at": "sync_runtime",
                    "override_reason": "sync_runtime",
                },
                source="local_runtime",
                override_reason="Local heuristic provider does not expose a remote models API; runtime defaults stored instead.",
                raw={},
            )
        )
    return discovered
