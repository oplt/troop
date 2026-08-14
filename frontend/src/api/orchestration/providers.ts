import { apiFetch } from "../client";

export type ProviderConfig = {
    id: string;
    project_id: string | null;
    name: string;
    provider_type: string;
    base_url: string | null;
    api_key_hint: string | null;
    organization: string | null;
    default_model: string;
    fallback_model: string | null;
    temperature: number;
    max_tokens: number;
    timeout_seconds: number;
    is_default: boolean;
    is_enabled: boolean;
    metadata: Record<string, unknown>;
    last_healthcheck_status: string | null;
    last_healthcheck_latency_ms: number | null;
    is_healthy: boolean;
    last_healthcheck_at: string | null;
    created_at: string;
    updated_at: string;
};

export type ProviderModelList = {
    provider_id: string;
    provider_type: string;
    models: Array<Record<string, unknown>>;
};

export type ModelCapability = {
    id: string;
    provider_id: string | null;
    provider_type: string;
    model_slug: string;
    display_name: string | null;
    supports_tools: boolean;
    supports_tool_calling: boolean;
    supports_structured_output: boolean;
    supports_reasoning: boolean;
    supports_vision: boolean;
    max_context_tokens: number;
    cost_per_1k_input: number;
    cost_per_1k_output: number;
    context_window: number | null;
    max_output_tokens: number | null;
    input_cost_per_1k: number | null;
    output_cost_per_1k: number | null;
    input_cost_per_1m: number | null;
    output_cost_per_1m: number | null;
    latency_p50: number | null;
    health_status: string | null;
    source_for_each_field: Record<string, string>;
    last_verified_at: string | null;
    override_reason: string | null;
    metadata: Record<string, unknown>;
    is_active: boolean;
    created_at: string;
    updated_at: string;
};

export type ProviderCompareResult = {
    provider_id: string;
    provider_name: string;
    provider_type: string;
    model_name: string;
    latency_ms: number;
    input_tokens: number;
    output_tokens: number;
    token_total: number;
    estimated_cost_usd: number;
    output_text: string;
    is_healthy: boolean;
};

export type ProviderCompareResponse = {
    prompt_preview: string;
    result_a: ProviderCompareResult;
    result_b: ProviderCompareResult;
};

export type ProviderHealthSummary = {
    provider_id: string;
    project_id: string | null;
    name: string;
    provider_type: string;
    default_model: string;
    enabled: boolean;
    status: string;
    healthy: boolean | null;
    latency_ms: number | null;
    last_checked_at: string | null;
    error: string | null;
};

export async function listProviders(projectId?: string): Promise<ProviderConfig[]> {
    const suffix = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
    return apiFetch(`/orchestration/providers${suffix}`);
}

export async function createProvider(payload: Record<string, unknown>): Promise<ProviderConfig> {
    return apiFetch("/orchestration/providers", { method: "POST", body: JSON.stringify(payload) });
}

export async function updateProvider(providerId: string, payload: Record<string, unknown>): Promise<ProviderConfig> {
    return apiFetch(`/orchestration/providers/${providerId}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export async function deleteProvider(providerId: string): Promise<void> {
    await apiFetch(`/orchestration/providers/${providerId}`, { method: "DELETE" });
}

export async function testProvider(providerId: string): Promise<Record<string, unknown>> {
    return apiFetch(`/orchestration/providers/${providerId}/test`, { method: "POST" });
}

export async function runProviderHealthChecks(): Promise<Array<Record<string, unknown>>> {
    return apiFetch("/orchestration/providers/health-check", { method: "POST" });
}

export async function getProviderHealthSummary(): Promise<ProviderHealthSummary[]> {
    return apiFetch("/orchestration/providers/health-summary");
}

export async function startProviderRuntime(providerId: string): Promise<Record<string, unknown>> {
    return apiFetch(`/orchestration/providers/${providerId}/runtime/start`, { method: "POST" });
}

export async function listProviderModels(providerId: string): Promise<ProviderModelList> {
    return apiFetch(`/orchestration/providers/${providerId}/models`);
}

export async function listModelCapabilities(): Promise<ModelCapability[]> {
    return apiFetch("/orchestration/providers/model-capabilities");
}

export async function compareProviders(payload: Record<string, unknown>): Promise<ProviderCompareResponse> {
    return apiFetch("/orchestration/providers/compare", {
        method: "POST",
        body: JSON.stringify(payload),
    });
}
