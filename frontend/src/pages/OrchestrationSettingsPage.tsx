import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
    Alert,
    Box,
    Button,
    Chip,
    Divider,
    FormControlLabel,
    MenuItem,
    Paper,
    Radio,
    RadioGroup,
    Stack,
    TextField,
    Typography,
} from "@mui/material";
import {
    compareProviders,
    createProvider,
    deleteProvider,
    listModelCapabilities,
    listProviderModels,
    listProviders,
    startProviderRuntime,
    testProvider,
    updateProvider,
    type ProviderConfig,
} from "../api/orchestration";
import { useSnackbar } from "../app/snackbarContext";
import { PageShell } from "../components/ui/PageShell";
import { SectionCard } from "../components/ui/SectionCard";
import { formatDateTime } from "../utils/formatters";

const CLOUD_PROVIDER_OPTIONS = [
    { value: "openai", label: "OpenAI", baseUrl: "https://api.openai.com/v1" },
    { value: "anthropic", label: "Anthropic / Claude", baseUrl: "https://api.anthropic.com" },
    { value: "qwen", label: "Qwen", baseUrl: "https://dashscope-intl.aliyuncs.com/compatible-mode/v1" },
    { value: "openai_compatible", label: "OpenAI-compatible API", baseUrl: "https://api.openai.com/v1" },
] as const;

const LOCAL_PROVIDER_OPTIONS = [
    { value: "ollama", label: "Ollama", baseUrl: "http://localhost:11434" },
    { value: "openai_compatible", label: "llama.cpp", baseUrl: "http://localhost:8080/v1" },
] as const;

const HEALTH_COLORS: Record<string, "success" | "warning" | "error" | "default"> = {
    healthy: "success",
    unhealthy: "error",
    never: "default",
};

type ProviderForm = {
    provider_category: "cloud" | "local";
    name: string;
    provider_type: string;
    base_url: string;
    api_key: string;
    default_model: string;
    fallback_model: string;
    timeout_seconds: number;
    local_runtime_command: string;
    local_runtime_working_dir: string;
    local_runtime_health_url: string;
};

const INITIAL_PROVIDER_FORM: ProviderForm = {
    provider_category: "cloud",
    name: "",
    provider_type: "openai",
    base_url: "https://api.openai.com/v1",
    api_key: "",
    default_model: "gpt-4.1-mini",
    fallback_model: "",
    timeout_seconds: 600,
    local_runtime_command: "",
    local_runtime_working_dir: "",
    local_runtime_health_url: "",
};

function buildProviderCreatePayload(form: ProviderForm) {
    const timeout = Math.min(3600, Math.max(5, Math.floor(form.timeout_seconds) || INITIAL_PROVIDER_FORM.timeout_seconds));
    const localRuntime = {
        mode: form.provider_category === "local" ? "managed" : "external",
        auto_start: false,
        command: form.local_runtime_command.trim(),
        working_dir: form.local_runtime_working_dir.trim() || null,
        health_url: form.local_runtime_health_url.trim() || null,
    };
    return {
        name: form.name.trim(),
        provider_type: form.provider_type,
        base_url: form.base_url.trim() || null,
        api_key: form.api_key.trim() || null,
        default_model: form.default_model.trim(),
        fallback_model: form.fallback_model.trim() || null,
        timeout_seconds: timeout,
        metadata: { local_runtime: localRuntime },
    };
}

function defaultLocalRuntimeCommand(providerType: string) {
    if (providerType === "ollama") return "ollama serve";
    if (providerType === "openai_compatible") {
        return [
            "/home/polat/Desktop/Projects/llama.cpp/build/bin/llama-server",
            "  -m /home/polat/Desktop/Projects/llama.cpp/models/qwen2.5-14b-instruct-q4_k_m.gguf",
            "  --host 127.0.0.1",
            "  --port 8081",
            "  -c 8192",
            "  -ngl 999",
        ].join("\n");
    }
    return "";
}

function defaultLocalRuntimeHealthUrl(providerType: string, baseUrl: string) {
    const normalizedBaseUrl = baseUrl.trim().replace(/\/$/, "");
    if (providerType === "ollama") return `${normalizedBaseUrl || "http://localhost:11434"}/api/tags`;
    if (providerType === "openai_compatible" && normalizedBaseUrl) return `${normalizedBaseUrl}/models`;
    return "";
}

function parseLlamaCppCommand(command: string) {
    const normalized = command.replace(/\\\s*\n/g, " ");
    const host = normalized.match(/(?:^|\s)--host\s+(\S+)/)?.[1] ?? "127.0.0.1";
    const port = normalized.match(/(?:^|\s)--port\s+(\S+)/)?.[1] ?? "8080";
    const modelPath = normalized.match(/(?:^|\s)-m\s+(\S+)/)?.[1] ?? "";
    const modelSlug = modelPath.split("/").pop()?.replace(/\.gguf$/i, "") || "local";
    const baseUrl = `http://${host}:${port}/v1`;
    return { baseUrl, healthUrl: `${baseUrl}/models`, modelSlug };
}

function providerOptionsFor(category: ProviderForm["provider_category"]) {
    return category === "local" ? LOCAL_PROVIDER_OPTIONS : CLOUD_PROVIDER_OPTIONS;
}

function localRuntimeMetadata(provider: ProviderConfig) {
    const value = provider.metadata?.local_runtime;
    return value && typeof value === "object" ? (value as Record<string, unknown>) : null;
}

function isLocalRuntimeProvider(provider: ProviderConfig, runtime: Record<string, unknown> | null) {
    return provider.provider_type === "ollama" || runtime?.mode === "managed";
}

function ProviderRequestTimeoutEditor({ provider }: { provider: ProviderConfig }) {
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();
    const [draft, setDraft] = useState(String(provider.timeout_seconds));
    const saveMutation = useMutation({
        mutationFn: (next: number) => updateProvider(provider.id, { timeout_seconds: next }),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "providers"] });
            showToast({ message: "Request timeout updated.", severity: "success" });
        },
        onError: () => {
            showToast({ message: "Could not update timeout.", severity: "error" });
        },
    });
    const parsed = parseInt(draft, 10);
    const clamped = Number.isFinite(parsed) ? Math.min(3600, Math.max(5, parsed)) : null;
    const unchanged = clamped !== null && clamped === provider.timeout_seconds;
    return (
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1} alignItems={{ sm: "flex-start" }}>
            <TextField
                size="small"
                type="number"
                label="HTTP request timeout (s)"
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                inputProps={{ min: 5, max: 3600 }}
                sx={{ maxWidth: 220 }}
                helperText="Each LLM call to this provider (5–3600s). Raise for slow CPU / Ollama."
            />
            <Button
                size="small"
                variant="outlined"
                sx={{ mt: { sm: 0.5 } }}
                disabled={saveMutation.isPending || clamped === null || unchanged}
                onClick={() => clamped !== null && saveMutation.mutate(clamped)}
            >
                Save timeout
            </Button>
        </Stack>
    );
}

function providerModels(provider: ProviderConfig) {
    const discovered = Array.isArray(provider.metadata?.discovered_models)
        ? (provider.metadata.discovered_models as Array<Record<string, unknown>>)
        : [];
    const names = new Set<string>();
    [provider.default_model, provider.fallback_model, ...discovered.map((item) => String(item.name ?? ""))]
        .filter(Boolean)
        .forEach((name) => names.add(String(name)));
    return Array.from(names);
}

function defaultModelForProviderType(providerType: string, capabilityMap: Record<string, string[]>) {
    if (providerType === "local") return "local-heuristic";
    if (providerType === "anthropic") return "claude-sonnet-4-20250514";
    if (providerType === "qwen") return "qwen-plus";
    return capabilityMap[providerType]?.[0] ?? "";
}

export function ProviderSettingsPanel() {
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();
    const [form, setForm] = useState<ProviderForm>(INITIAL_PROVIDER_FORM);
    const [createAttempted, setCreateAttempted] = useState(false);
    const [compareForm, setCompareForm] = useState({
        provider_a_id: "",
        provider_b_id: "",
        model_a: "",
        model_b: "",
        task_title: "Compare model output for task orchestration",
        task_description: "Design the execution plan, identify risks, and outline next steps.",
        acceptance_criteria: "Readable plan, concrete risks, clear next actions.",
    });

    const { data: providers = [] } = useQuery({
        queryKey: ["orchestration", "providers"],
        queryFn: () => listProviders(),
        refetchInterval: 10_000,
    });
    const { data: modelCapabilities = [] } = useQuery({
        queryKey: ["orchestration", "provider-model-capabilities"],
        queryFn: listModelCapabilities,
    });

    const providerCapabilityMap = useMemo(() => {
        return modelCapabilities.reduce<Record<string, string[]>>((accumulator, item) => {
            accumulator[item.provider_type] = accumulator[item.provider_type] ?? [];
            if (!accumulator[item.provider_type].includes(item.model_slug)) {
                accumulator[item.provider_type].push(item.model_slug);
            }
            return accumulator;
        }, {});
    }, [modelCapabilities]);
    const capabilityMatrix = useMemo(() => {
        const providerNameById = new Map(providers.map((provider) => [provider.id, provider.name]));
        const rows = modelCapabilities.map((item) => ({
            providerId: item.provider_id,
            providerLabel: item.provider_id ? providerNameById.get(item.provider_id) ?? item.provider_type : item.provider_type,
            providerType: item.provider_type,
            modelSlug: item.model_slug,
            supportsTools: item.supports_tools,
            supportsVision: item.supports_vision,
            contextTokens: item.context_window ?? item.max_context_tokens,
            maxOutputTokens: item.max_output_tokens,
            inputCost: item.input_cost_per_1k ?? item.cost_per_1k_input,
            outputCost: item.output_cost_per_1k ?? item.cost_per_1k_output,
            latencyP50: item.latency_p50,
            healthStatus: item.health_status ?? "unknown",
            source: String(item.metadata?.source ?? "provider"),
            lastVerifiedAt: item.last_verified_at,
            overrideReason: item.override_reason,
        }));
        for (const provider of providers) {
            for (const model of providerModels(provider)) {
                if (rows.some((item) => item.providerId === provider.id && item.modelSlug === model)) {
                    continue;
                }
                rows.push({
                    providerId: provider.id,
                    providerLabel: provider.name,
                    providerType: provider.provider_type,
                    modelSlug: model,
                    supportsTools: false,
                    supportsVision: false,
                    contextTokens: 8192,
                    maxOutputTokens: null,
                    inputCost: 0,
                    outputCost: 0,
                    latencyP50: provider.last_healthcheck_latency_ms,
                    healthStatus: provider.last_healthcheck_status ?? "unknown",
                    source: "provider",
                    lastVerifiedAt: null,
                    overrideReason: null,
                });
            }
        }
        rows.sort((a, b) =>
            a.providerType === b.providerType
                ? a.modelSlug.localeCompare(b.modelSlug)
                : `${a.providerLabel}`.localeCompare(`${b.providerLabel}`)
        );
        return rows;
    }, [modelCapabilities, providers]);
    const providerPayload = useMemo(() => buildProviderCreatePayload(form), [form]);
    const nameError = createAttempted && providerPayload.name.length < 2;
    const defaultModelError = createAttempted && providerPayload.default_model.length === 0;
    const canCreateProvider = providerPayload.name.length >= 2 && providerPayload.default_model.length > 0;

    const createMutation = useMutation({
        mutationFn: createProvider,
        onSuccess: async () => {
            setForm(INITIAL_PROVIDER_FORM);
            setCreateAttempted(false);
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "providers"] });
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "provider-model-capabilities"] });
            showToast({ message: "Provider saved.", severity: "success" });
        },
    });
    const testMutation = useMutation({
        mutationFn: testProvider,
        onSuccess: async (result) => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "providers"] });
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "provider-model-capabilities"] });
            const status = String(result.status ?? "unknown");
            const error = typeof result.error === "string" ? result.error : "";
            showToast({
                message: status === "healthy" ? "Provider health check completed." : `Provider unhealthy${error ? `: ${error}` : "."}`,
                severity: status === "healthy" ? "success" : "warning",
            });
        },
    });
    const discoverMutation = useMutation({
        mutationFn: listProviderModels,
        onSuccess: async (_, providerId) => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "providers"] });
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "provider-model-capabilities"] });
            showToast({ message: "Provider models refreshed.", severity: "success" });
            setCompareForm((current) => ({
                ...current,
                provider_a_id: current.provider_a_id || providerId,
            }));
        },
    });
    const startRuntimeMutation = useMutation({
        mutationFn: startProviderRuntime,
        onSuccess: async (result) => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "providers"] });
            const status = String(result.status ?? "unknown");
            const detail = typeof result.detail === "string" ? result.detail : "";
            showToast({
                message: `Local server ${status}${detail ? `: ${detail}` : "."}`,
                severity: status === "running" || status === "already_running" ? "success" : "warning",
            });
        },
        onError: () => {
            showToast({ message: "Could not start local server.", severity: "error" });
        },
    });
    const deleteMutation = useMutation({
        mutationFn: deleteProvider,
        onSuccess: async (_, providerId) => {
            setCompareForm((current) => ({
                ...current,
                provider_a_id: current.provider_a_id === providerId ? "" : current.provider_a_id,
                provider_b_id: current.provider_b_id === providerId ? "" : current.provider_b_id,
                model_a: current.provider_a_id === providerId ? "" : current.model_a,
                model_b: current.provider_b_id === providerId ? "" : current.model_b,
            }));
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "providers"] });
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "provider-model-capabilities"] });
            showToast({ message: "Provider deleted.", severity: "success" });
        },
        onError: () => {
            showToast({ message: "Could not delete provider.", severity: "error" });
        },
    });
    const compareMutation = useMutation({
        mutationFn: compareProviders,
    });

    const selectedCompareProviderA = providers.find((provider) => provider.id === compareForm.provider_a_id) ?? null;
    const selectedCompareProviderB = providers.find((provider) => provider.id === compareForm.provider_b_id) ?? null;

    return (
        <Stack spacing={2.5}>
            <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", xl: "380px minmax(0, 1fr)" } }}>
                <SectionCard
                    title="Add provider"
                    description="Register OpenAI, Qwen, Claude, Ollama, compatible, or local endpoints and sync model metadata into the capability matrix."
                >
                    <Stack spacing={2}>
                        <TextField
                            label="Name"
                            value={form.name}
                            onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
                            error={nameError}
                            helperText={nameError ? "Use at least 2 characters." : undefined}
                        />
                        <Box>
                            <Typography variant="caption" color="text.secondary">
                                Type
                            </Typography>
                            <RadioGroup
                                row
                                value={form.provider_category}
                                onChange={(event) => {
                                    const nextCategory = event.target.value as ProviderForm["provider_category"];
                                    const nextOption = providerOptionsFor(nextCategory)[0];
                                    const nextType = nextOption.value;
                                    const suggestedModels = providerCapabilityMap[nextType] ?? [];
                                    const runtimeCommand = defaultLocalRuntimeCommand(nextType);
                                    const parsedLlamaCpp = nextCategory === "local" && nextType === "openai_compatible" ? parseLlamaCppCommand(runtimeCommand) : null;
                                    const nextBaseUrl = parsedLlamaCpp?.baseUrl ?? nextOption.baseUrl;
                                    setForm((current) => ({
                                        ...current,
                                        provider_category: nextCategory,
                                        provider_type: nextType,
                                        base_url: nextBaseUrl,
                                        api_key: nextCategory === "local" ? "" : current.api_key,
                                        default_model:
                                            nextCategory === "local" && nextType === "openai_compatible"
                                                ? parsedLlamaCpp?.modelSlug ?? "local"
                                                : suggestedModels[0] ?? defaultModelForProviderType(nextType, providerCapabilityMap) ?? current.default_model,
                                        fallback_model: nextCategory === "local" ? "" : suggestedModels[1] ?? current.fallback_model,
                                        local_runtime_command: runtimeCommand,
                                        local_runtime_health_url: parsedLlamaCpp?.healthUrl ?? defaultLocalRuntimeHealthUrl(nextType, nextBaseUrl),
                                    }));
                                }}
                            >
                                <FormControlLabel value="cloud" control={<Radio size="small" />} label="Cloud" />
                                <FormControlLabel value="local" control={<Radio size="small" />} label="Local server" />
                            </RadioGroup>
                        </Box>
                        <TextField
                            select
                            label={form.provider_category === "local" ? "Local server" : "Cloud provider"}
                            value={form.provider_type}
                            onChange={(event) => {
                                const nextType = event.target.value;
                                const nextOption = providerOptionsFor(form.provider_category).find((option) => option.value === nextType);
                                const suggestedModels = providerCapabilityMap[nextType] ?? [];
                                const runtimeCommand = defaultLocalRuntimeCommand(nextType);
                                const parsedLlamaCpp = form.provider_category === "local" && nextType === "openai_compatible" ? parseLlamaCppCommand(runtimeCommand) : null;
                                setForm((current) => ({
                                    ...current,
                                    provider_type: nextType,
                                    base_url: parsedLlamaCpp?.baseUrl ?? nextOption?.baseUrl ?? current.base_url,
                                    api_key: form.provider_category === "local" ? "" : current.api_key,
                                    default_model:
                                        form.provider_category === "local" && nextType === "openai_compatible"
                                            ? parsedLlamaCpp?.modelSlug ?? "local"
                                            : suggestedModels[0] ?? defaultModelForProviderType(nextType, providerCapabilityMap) ?? current.default_model,
                                    fallback_model: form.provider_category === "local" ? "" : suggestedModels[1] ?? current.fallback_model,
                                    local_runtime_command: runtimeCommand,
                                    local_runtime_health_url: parsedLlamaCpp?.healthUrl ?? defaultLocalRuntimeHealthUrl(nextType, nextOption?.baseUrl ?? current.base_url),
                                }));
                            }}
                        >
                            {providerOptionsFor(form.provider_category).map((option) => (
                                <MenuItem key={option.value} value={option.value}>
                                    {option.label}
                                </MenuItem>
                            ))}
                        </TextField>
                        <TextField
                            label="Base URL"
                            value={form.base_url}
                            onChange={(event) => setForm((current) => ({ ...current, base_url: event.target.value }))}
                            helperText={form.provider_category === "local" ? "Backend must be able to reach this URL." : undefined}
                        />
                        <TextField
                            label="API key"
                            type="password"
                            value={form.api_key}
                            onChange={(event) => setForm((current) => ({ ...current, api_key: event.target.value }))}
                            helperText={form.provider_category === "local" ? "Usually blank for local servers." : undefined}
                        />
                        <TextField
                            label="Default model"
                            value={form.default_model}
                            onChange={(event) => setForm((current) => ({ ...current, default_model: event.target.value }))}
                            error={defaultModelError}
                            helperText={
                                defaultModelError
                                    ? "Default model is required."
                                    : (providerCapabilityMap[form.provider_type]?.length ?? 0) > 0
                                    ? `Known: ${providerCapabilityMap[form.provider_type].join(", ")}`
                                    : "Type the model slug exactly as the provider expects (e.g. llama3.1:8b)."
                            }
                        />
                        <TextField
                            label="Fallback model"
                            value={form.fallback_model}
                            onChange={(event) => setForm((current) => ({ ...current, fallback_model: event.target.value }))}
                            helperText="Optional. Leave blank for none."
                        />
                        <TextField
                            type="number"
                            label="HTTP request timeout (seconds)"
                            value={form.timeout_seconds}
                            onChange={(event) => {
                                const next = Number(event.target.value);
                                setForm((current) => ({
                                    ...current,
                                    timeout_seconds: Number.isFinite(next) ? next : current.timeout_seconds,
                                }));
                            }}
                            inputProps={{ min: 5, max: 3600 }}
                            helperText="Per LLM request to this provider (backend default was 120s). Use 600–1800+ for slow CPU / Ollama."
                        />
                        {form.provider_category === "local" && (
                            <Stack spacing={1.5}>
                                <TextField
                                    label="Start command"
                                    value={form.local_runtime_command}
                                    onChange={(event) => {
                                        const command = event.target.value;
                                        const parsed = form.provider_type === "openai_compatible" ? parseLlamaCppCommand(command) : null;
                                        setForm((current) => ({
                                            ...current,
                                            local_runtime_command: command,
                                            base_url: parsed?.baseUrl ?? current.base_url,
                                            default_model: parsed?.modelSlug ?? current.default_model,
                                            local_runtime_health_url: parsed?.healthUrl ?? current.local_runtime_health_url,
                                        }));
                                    }}
                                    helperText={
                                        form.provider_type === "ollama"
                                            ? "Default: ollama serve"
                                            : "Paste the full llama-server command."
                                    }
                                    multiline
                                    minRows={form.provider_type === "openai_compatible" ? 6 : 1}
                                />
                                <TextField
                                    label="Health URL"
                                    value={form.local_runtime_health_url}
                                    onChange={(event) => setForm((current) => ({ ...current, local_runtime_health_url: event.target.value }))}
                                    helperText="Used before starting to avoid duplicate servers."
                                />
                            </Stack>
                        )}

                        <Button
                            variant="contained"
                            disabled={createMutation.isPending}
                            onClick={() => {
                                setCreateAttempted(true);
                                if (!canCreateProvider) return;
                                createMutation.mutate(providerPayload);
                            }}
                        >
                            Save provider
                        </Button>
                        {createMutation.isError && (
                            <Alert severity="error">
                                {createMutation.error instanceof Error ? createMutation.error.message : "Couldn't save provider. Check credentials and retry."}
                            </Alert>
                        )}
                    </Stack>
                </SectionCard>

                <SectionCard
                    title="Provider health"
                    description="Status is backed by explicit test requests and periodic Celery beat health checks."
                >
                    <Stack spacing={1.5}>
                        {providers.map((provider) => {
                            const discoveredCount = Array.isArray(provider.metadata?.discovered_models)
                                ? provider.metadata.discovered_models.length
                                : 0;
                            const statusLabel = provider.last_healthcheck_status ?? "never";
                            const runtime = localRuntimeMetadata(provider);
                            const isLocalRuntime = isLocalRuntimeProvider(provider, runtime);
                            const runtimeMode = String(runtime?.mode ?? "external");
                            const runtimeStatus = runtime?.status ? String(runtime.status) : null;
                            return (
                                <Paper key={provider.id} sx={{ p: 2, borderRadius: 4 }}>
                                    <Stack spacing={1.5}>
                                        <Stack direction={{ xs: "column", md: "row" }} justifyContent="space-between" spacing={1.5}>
                                            <Box>
                                                <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                                                    <Typography variant="subtitle2">{provider.name}</Typography>
                                                    <Chip
                                                        label={statusLabel}
                                                        size="small"
                                                        color={HEALTH_COLORS[statusLabel] ?? "default"}
                                                        variant={provider.is_healthy ? "filled" : "outlined"}
                                                    />
                                                </Stack>
                                                <Typography variant="body2" color="text.secondary">
                                                    {provider.provider_type} • {provider.default_model}
                                                    {provider.fallback_model ? ` → ${provider.fallback_model}` : ""}
                                                </Typography>
                                            </Box>
                                            <Stack direction="row" spacing={1}>
                                                {isLocalRuntime && (
                                                    <Button
                                                        size="small"
                                                        variant="contained"
                                                        disabled={startRuntimeMutation.isPending}
                                                        onClick={() => startRuntimeMutation.mutate(provider.id)}
                                                    >
                                                        Start server
                                                    </Button>
                                                )}
                                                <Button size="small" onClick={() => testMutation.mutate(provider.id)}>
                                                    Test connection
                                                </Button>
                                                <Button size="small" onClick={() => discoverMutation.mutate(provider.id)}>
                                                    Refresh models
                                                </Button>
                                                <Button
                                                    size="small"
                                                    color="error"
                                                    variant="outlined"
                                                    disabled={deleteMutation.isPending}
                                                    onClick={() => {
                                                        if (window.confirm(`Delete provider "${provider.name}"?`)) {
                                                            deleteMutation.mutate(provider.id);
                                                        }
                                                    }}
                                                >
                                                    Delete
                                                </Button>
                                            </Stack>
                                        </Stack>
                                        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                                            <Chip
                                                size="small"
                                                variant="outlined"
                                                label={`Latency: ${provider.last_healthcheck_latency_ms ?? "—"} ms`}
                                            />
                                            <Chip
                                                size="small"
                                                variant="outlined"
                                                label={`Last checked: ${provider.last_healthcheck_at ? formatDateTime(provider.last_healthcheck_at) : "Never"}`}
                                            />
                                            <Chip
                                                size="small"
                                                variant="outlined"
                                                label={`Discovered models: ${discoveredCount}`}
                                            />
                                            {isLocalRuntime && (
                                                <Chip
                                                    size="small"
                                                    variant="outlined"
                                                    label={`Runtime: ${runtimeMode}${runtimeStatus ? ` (${runtimeStatus})` : ""}`}
                                                />
                                            )}
                                        </Stack>
                                        <Typography variant="caption" color="text.secondary">
                                            {provider.api_key_hint || "No key stored"}
                                            {provider.metadata?.last_healthcheck_error ? ` • ${String(provider.metadata.last_healthcheck_error)}` : ""}
                                        </Typography>
                                        <ProviderRequestTimeoutEditor key={`${provider.id}-${provider.timeout_seconds}`} provider={provider} />
                                    </Stack>
                                </Paper>
                            );
                        })}
                    </Stack>
                </SectionCard>
            </Box>

            <SectionCard
                title="Provider A/B compare"
                description="Run the same task prompt against two providers or models and compare output, latency, and estimated cost side by side."
            >
                <Stack spacing={2}>
                    <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", md: "repeat(2, minmax(0, 1fr))" } }}>
                        <TextField
                            select
                            label="Provider A"
                            value={compareForm.provider_a_id}
                            onChange={(event) => {
                                const nextProvider = providers.find((provider) => provider.id === event.target.value);
                                setCompareForm((current) => ({
                                    ...current,
                                    provider_a_id: event.target.value,
                                    model_a: nextProvider?.default_model ?? "",
                                }));
                            }}
                        >
                            {providers.map((provider) => (
                                <MenuItem key={provider.id} value={provider.id}>
                                    {provider.name}
                                </MenuItem>
                            ))}
                        </TextField>
                        <TextField
                            select
                            label="Model A"
                            value={compareForm.model_a}
                            onChange={(event) => setCompareForm((current) => ({ ...current, model_a: event.target.value }))}
                        >
                            {providerModels(selectedCompareProviderA ?? ({
                                default_model: compareForm.model_a,
                                fallback_model: null,
                                metadata: {},
                            } as ProviderConfig)).map((model) => (
                                <MenuItem key={model} value={model}>
                                    {model}
                                </MenuItem>
                            ))}
                        </TextField>
                        <TextField
                            select
                            label="Provider B"
                            value={compareForm.provider_b_id}
                            onChange={(event) => {
                                const nextProvider = providers.find((provider) => provider.id === event.target.value);
                                setCompareForm((current) => ({
                                    ...current,
                                    provider_b_id: event.target.value,
                                    model_b: nextProvider?.default_model ?? "",
                                }));
                            }}
                        >
                            {providers.map((provider) => (
                                <MenuItem key={provider.id} value={provider.id}>
                                    {provider.name}
                                </MenuItem>
                            ))}
                        </TextField>
                        <TextField
                            select
                            label="Model B"
                            value={compareForm.model_b}
                            onChange={(event) => setCompareForm((current) => ({ ...current, model_b: event.target.value }))}
                        >
                            {providerModels(selectedCompareProviderB ?? ({
                                default_model: compareForm.model_b,
                                fallback_model: null,
                                metadata: {},
                            } as ProviderConfig)).map((model) => (
                                <MenuItem key={model} value={model}>
                                    {model}
                                </MenuItem>
                            ))}
                        </TextField>
                    </Box>
                    <TextField
                        label="Task title"
                        value={compareForm.task_title}
                        onChange={(event) => setCompareForm((current) => ({ ...current, task_title: event.target.value }))}
                    />
                    <TextField
                        label="Task description"
                        minRows={3}
                        multiline
                        value={compareForm.task_description}
                        onChange={(event) => setCompareForm((current) => ({ ...current, task_description: event.target.value }))}
                    />
                    <TextField
                        label="Acceptance criteria"
                        minRows={2}
                        multiline
                        value={compareForm.acceptance_criteria}
                        onChange={(event) => setCompareForm((current) => ({ ...current, acceptance_criteria: event.target.value }))}
                    />
                    <Stack direction="row" justifyContent="space-between" spacing={2}>
                        <Typography variant="caption" color="text.secondary">
                            Compare uses the same task prompt against both selections and reports real latency plus estimated cost.
                        </Typography>
                        <Button
                            variant="contained"
                            onClick={() => compareMutation.mutate(compareForm)}
                            disabled={!compareForm.provider_a_id || !compareForm.provider_b_id}
                        >
                            Run compare
                        </Button>
                    </Stack>
                    {compareMutation.isError && (
                        <Alert severity="error">
                            {compareMutation.error instanceof Error ? compareMutation.error.message : "Provider compare failed."}
                        </Alert>
                    )}
                    {compareMutation.data && (
                        <>
                            <Divider />
                            <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", xl: "repeat(2, minmax(0, 1fr))" } }}>
                                {[compareMutation.data.result_a, compareMutation.data.result_b].map((result) => (
                                    <Paper key={`${result.provider_id}-${result.model_name}`} sx={{ p: 2.5, borderRadius: 4 }}>
                                        <Stack spacing={1.5}>
                                            <Stack direction="row" justifyContent="space-between" spacing={1.5}>
                                                <Box>
                                                    <Typography variant="subtitle2">{result.provider_name}</Typography>
                                                    <Typography variant="body2" color="text.secondary">
                                                        {result.provider_type} • {result.model_name}
                                                    </Typography>
                                                </Box>
                                                <Chip
                                                    label={result.is_healthy ? "healthy" : "unhealthy"}
                                                    color={result.is_healthy ? "success" : "warning"}
                                                    size="small"
                                                    variant={result.is_healthy ? "filled" : "outlined"}
                                                />
                                            </Stack>
                                            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                                                <Chip size="small" variant="outlined" label={`${result.latency_ms} ms`} />
                                                <Chip size="small" variant="outlined" label={`${result.token_total} tokens`} />
                                                <Chip size="small" variant="outlined" label={`$${result.estimated_cost_usd.toFixed(4)}`} />
                                            </Stack>
                                            <Typography
                                                variant="body2"
                                                sx={{ whiteSpace: "pre-wrap", fontFamily: "IBM Plex Mono, monospace" }}
                                            >
                                                {result.output_text}
                                            </Typography>
                                        </Stack>
                                    </Paper>
                                ))}
                            </Box>
                        </>
                    )}
                </Stack>
            </SectionCard>
            <SectionCard
                title="Model capability matrix"
                description="Provider × model × capabilities view used for policy routing and execution planning."
            >
                <Stack spacing={1.25}>
                    {capabilityMatrix.map((item) => (
                        <Paper key={`${item.providerId ?? item.providerType}-${item.modelSlug}`} sx={{ p: 1.5, borderRadius: 3 }}>
                            <Stack direction={{ xs: "column", md: "row" }} spacing={1.25} justifyContent="space-between">
                                <Typography variant="body2">
                                    <strong>{item.providerLabel}</strong> · {item.modelSlug}
                                </Typography>
                                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                                    <Chip size="small" label={item.supportsTools ? "tools" : "no-tools"} />
                                    <Chip size="small" label={item.supportsVision ? "vision" : "text-only"} />
                                    <Chip size="small" label={item.contextTokens ? `${item.contextTokens.toLocaleString()} ctx` : "ctx —"} />
                                    <Chip size="small" label={item.maxOutputTokens ? `${item.maxOutputTokens.toLocaleString()} out` : "out —"} />
                                    <Chip size="small" label={`in $${item.inputCost.toFixed(4)}/1k`} />
                                    <Chip size="small" label={`out $${item.outputCost.toFixed(4)}/1k`} />
                                    <Chip size="small" label={item.latencyP50 ? `${item.latencyP50} ms p50` : "p50 —"} />
                                    <Chip size="small" label={item.healthStatus} variant="outlined" />
                                    <Chip size="small" variant="outlined" label={item.source} />
                                    <Chip
                                        size="small"
                                        variant="outlined"
                                        label={item.lastVerifiedAt ? formatDateTime(item.lastVerifiedAt) : "unverified"}
                                    />
                                </Stack>
                            </Stack>
                            {item.overrideReason && (
                                <Typography variant="caption" color="text.secondary">
                                    {item.overrideReason}
                                </Typography>
                            )}
                        </Paper>
                    ))}
                </Stack>
            </SectionCard>
        </Stack>
    );
}

export default function OrchestrationSettingsPage() {
    return (
        <PageShell maxWidth="xl">
            <ProviderSettingsPanel />
        </PageShell>
    );
}
