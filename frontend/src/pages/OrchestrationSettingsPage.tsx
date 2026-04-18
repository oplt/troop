import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
    Alert,
    Box,
    Button,
    Chip,
    Divider,
    MenuItem,
    Paper,
    Stack,
    TextField,
    Typography,
} from "@mui/material";
import {
    compareProviders,
    createProvider,
    listModelCapabilities,
    listProviderModels,
    listProviders,
    testProvider,
    type ProviderConfig,
} from "../api/orchestration";
import { useSnackbar } from "../app/snackbarContext";
import { PageHeader } from "../components/ui/PageHeader";
import { PageShell } from "../components/ui/PageShell";
import { SectionCard } from "../components/ui/SectionCard";
import { formatDateTime } from "../utils/formatters";

const PROVIDER_TYPE_OPTIONS = [
    { value: "openai", label: "OpenAI", baseUrl: "https://api.openai.com/v1" },
    { value: "openai_compatible", label: "OpenAI-compatible", baseUrl: "https://api.openai.com/v1" },
    { value: "ollama", label: "Ollama", baseUrl: "http://localhost:11434" },
] as const;

const HEALTH_COLORS: Record<string, "success" | "warning" | "error" | "default"> = {
    healthy: "success",
    unhealthy: "error",
    never: "default",
};

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

export function ProviderSettingsPanel() {
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();
    const [form, setForm] = useState({
        name: "",
        provider_type: "openai_compatible",
        base_url: "https://api.openai.com/v1",
        api_key: "",
        default_model: "gpt-4.1-mini",
        fallback_model: "",
    });
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
            accumulator[item.provider_type].push(item.model_slug);
            return accumulator;
        }, {});
    }, [modelCapabilities]);
    const capabilityMatrix = useMemo(() => {
        const rows = modelCapabilities.map((item) => ({
            providerType: item.provider_type,
            modelSlug: item.model_slug,
            supportsTools: item.supports_tools,
            supportsVision: item.supports_vision,
            contextTokens: item.max_context_tokens,
            inputCost: item.cost_per_1k_input,
            outputCost: item.cost_per_1k_output,
        }));
        rows.sort((a, b) =>
            a.providerType === b.providerType
                ? a.modelSlug.localeCompare(b.modelSlug)
                : a.providerType.localeCompare(b.providerType)
        );
        return rows;
    }, [modelCapabilities]);

    const createMutation = useMutation({
        mutationFn: createProvider,
        onSuccess: async () => {
            setForm({
                name: "",
                provider_type: "openai_compatible",
                base_url: "https://api.openai.com/v1",
                api_key: "",
                default_model: "gpt-4.1-mini",
                fallback_model: "",
            });
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "providers"] });
            showToast({ message: "Provider saved.", severity: "success" });
        },
    });
    const testMutation = useMutation({
        mutationFn: testProvider,
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "providers"] });
            showToast({ message: "Provider health check completed.", severity: "success" });
        },
    });
    const discoverMutation = useMutation({
        mutationFn: listProviderModels,
        onSuccess: async (_, providerId) => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "providers"] });
            showToast({ message: "Provider models refreshed.", severity: "success" });
            setCompareForm((current) => ({
                ...current,
                provider_a_id: current.provider_a_id || providerId,
            }));
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
                    description="Register hosted or local model endpoints. Ollama providers auto-discover running local models."
                >
                    <Stack spacing={2}>
                        <TextField
                            label="Name"
                            value={form.name}
                            onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
                        />
                        <TextField
                            select
                            label="Type"
                            value={form.provider_type}
                            onChange={(event) => {
                                const nextType = event.target.value;
                                const nextOption = PROVIDER_TYPE_OPTIONS.find((option) => option.value === nextType);
                                const suggestedModels = providerCapabilityMap[nextType] ?? [];
                                setForm((current) => ({
                                    ...current,
                                    provider_type: nextType,
                                    base_url: nextOption?.baseUrl ?? current.base_url,
                                    default_model: suggestedModels[0] ?? current.default_model,
                                    fallback_model: suggestedModels[1] ?? current.fallback_model,
                                }));
                            }}
                        >
                            {PROVIDER_TYPE_OPTIONS.map((option) => (
                                <MenuItem key={option.value} value={option.value}>
                                    {option.label}
                                </MenuItem>
                            ))}
                        </TextField>
                        <TextField
                            label="Base URL"
                            value={form.base_url}
                            onChange={(event) => setForm((current) => ({ ...current, base_url: event.target.value }))}
                        />
                        <TextField
                            label="API key"
                            type="password"
                            value={form.api_key}
                            onChange={(event) => setForm((current) => ({ ...current, api_key: event.target.value }))}
                            helperText={form.provider_type === "ollama" ? "Leave blank for local Ollama." : undefined}
                        />
                        <TextField
                            select
                            label="Default model"
                            value={form.default_model}
                            onChange={(event) => setForm((current) => ({ ...current, default_model: event.target.value }))}
                        >
                            {(providerCapabilityMap[form.provider_type] ?? [form.default_model]).map((model) => (
                                <MenuItem key={model} value={model}>
                                    {model}
                                </MenuItem>
                            ))}
                        </TextField>
                        <TextField
                            select
                            label="Fallback model"
                            value={form.fallback_model}
                            onChange={(event) => setForm((current) => ({ ...current, fallback_model: event.target.value }))}
                        >
                            <MenuItem value="">None</MenuItem>
                            {(providerCapabilityMap[form.provider_type] ?? []).map((model) => (
                                <MenuItem key={model} value={model}>
                                    {model}
                                </MenuItem>
                            ))}
                        </TextField>
                        <Button
                            variant="contained"
                            onClick={() =>
                                createMutation.mutate({
                                    ...form,
                                    fallback_model: form.fallback_model || null,
                                })
                            }
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
                                                <Button size="small" onClick={() => testMutation.mutate(provider.id)}>
                                                    Test connection
                                                </Button>
                                                {provider.provider_type === "ollama" && (
                                                    <Button size="small" onClick={() => discoverMutation.mutate(provider.id)}>
                                                        Refresh models
                                                    </Button>
                                                )}
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
                                        </Stack>
                                        <Typography variant="caption" color="text.secondary">
                                            {provider.api_key_hint || "No key stored"}
                                            {provider.metadata?.last_healthcheck_error ? ` • ${String(provider.metadata.last_healthcheck_error)}` : ""}
                                        </Typography>
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
                        <Paper key={`${item.providerType}-${item.modelSlug}`} sx={{ p: 1.5, borderRadius: 3 }}>
                            <Stack direction={{ xs: "column", md: "row" }} spacing={1.25} justifyContent="space-between">
                                <Typography variant="body2">
                                    <strong>{item.providerType}</strong> · {item.modelSlug}
                                </Typography>
                                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                                    <Chip size="small" label={item.supportsTools ? "tools" : "no-tools"} />
                                    <Chip size="small" label={item.supportsVision ? "vision" : "text-only"} />
                                    <Chip size="small" label={`${item.contextTokens.toLocaleString()} ctx`} />
                                    <Chip size="small" label={`in $${item.inputCost.toFixed(4)}/1k`} />
                                    <Chip size="small" label={`out $${item.outputCost.toFixed(4)}/1k`} />
                                </Stack>
                            </Stack>
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
            <PageHeader
                eyebrow="Settings"
                title="Provider Settings"
                description="Manage hosted and local model providers, health status, routing, and side-by-side model comparisons."
            />
            <ProviderSettingsPanel />
        </PageShell>
    );
}
