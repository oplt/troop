from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.core.schemas import RequestModel
from backend.modules.github.schemas import GithubSyncEventResponse

from backend.modules.orchestration.schemas.common import *  # noqa: F403

class ProviderConfigCreate(RequestModel):
    project_id: str | None = None
    name: str = Field(min_length=2, max_length=255)
    provider_type: str = Field(min_length=2, max_length=64)
    base_url: str | None = None
    api_key: str | None = None
    organization: str | None = None
    default_model: str = Field(min_length=1, max_length=255)
    fallback_model: str | None = None
    temperature: float = Field(default=0.2, ge=0, le=2)
    max_tokens: int = Field(default=4096, ge=128, le=200000)
    timeout_seconds: int = Field(default=120, ge=5, le=3600)
    is_default: bool = False
    is_enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProviderConfigUpdate(RequestModel):
    name: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    organization: str | None = None
    default_model: str | None = None
    fallback_model: str | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=128, le=200000)
    timeout_seconds: int | None = Field(default=None, ge=5, le=3600)
    is_default: bool | None = None
    is_enabled: bool | None = None
    metadata: dict[str, Any] | None = None


class ProviderConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str | None
    name: str
    provider_type: str
    base_url: str | None
    api_key_hint: str | None
    organization: str | None
    default_model: str
    fallback_model: str | None
    temperature: float
    max_tokens: int
    timeout_seconds: int
    is_default: bool
    is_enabled: bool
    metadata: dict[str, Any]
    last_healthcheck_status: str | None
    last_healthcheck_latency_ms: int | None
    is_healthy: bool
    last_healthcheck_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ModelCapabilityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    provider_id: str | None
    provider_type: str
    model_slug: str
    display_name: str | None
    supports_tools: bool
    supports_tool_calling: bool = False
    supports_structured_output: bool = False
    supports_reasoning: bool = False
    supports_vision: bool
    max_context_tokens: int
    cost_per_1k_input: float
    cost_per_1k_output: float
    context_window: int | None = None
    max_output_tokens: int | None = None
    input_cost_per_1k: float | None = None
    output_cost_per_1k: float | None = None
    input_cost_per_1m: float | None = None
    output_cost_per_1m: float | None = None
    latency_p50: int | None = None
    health_status: str | None = None
    source_for_each_field: dict[str, str] = Field(default_factory=dict)
    last_verified_at: datetime | None = None
    override_reason: str | None = None
    metadata: dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ProviderModelListResponse(BaseModel):
    provider_id: str
    provider_type: str
    models: list[dict[str, Any]] = Field(default_factory=list)


class ProviderCompareRequest(RequestModel):
    provider_a_id: str
    provider_b_id: str
    model_a: str | None = None
    model_b: str | None = None
    task_title: str = Field(min_length=2, max_length=255)
    task_description: str | None = None
    acceptance_criteria: str | None = None
    task_metadata: dict[str, Any] = Field(default_factory=dict)


class ProviderCompareResult(BaseModel):
    provider_id: str
    provider_name: str
    provider_type: str
    model_name: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    token_total: int
    estimated_cost_usd: float
    output_text: str
    is_healthy: bool


class ProviderCompareResponse(BaseModel):
    prompt_preview: str
    result_a: ProviderCompareResult
    result_b: ProviderCompareResult


