import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Box, Button, Chip, Divider, MenuItem, Paper, Stack, Tab, Tabs, TextField, Typography } from "@mui/material";
import { Add as AddIcon, CheckCircleOutline, ContentCopy, PlayArrow, Publish, SmartToy as AgentIcon, UploadFile } from "@mui/icons-material";
import {
    activateAgent, createAgent, createAgentFromTemplate, duplicateAgent, listAgentTemplates,
    listAgentVersions, listAgents, listOrchestrationProjects, listTools, testRunAgent,
    updateAgent, validateAgentContract, type Agent, type AgentTemplate,
} from "../api/orchestration";
import { PageShell } from "../components/ui/PageShell";
import { PageHeader } from "../components/ui/PageHeader";
import { FilterToolbar } from "../components/ui/FilterToolbar";
import { FormFieldStack } from "../components/ui/FormFieldStack";
import { InspectorSplit } from "../components/ui/InspectorSplit";
import { QueryState } from "../components/ui/QueryState";
import { Subsection } from "../components/ui/Subsection";
import { StatusChip } from "../components/ui/StatusChip";
import { EmptyState } from "../components/ui/EmptyState";
import { DensePageMobileNotice } from "../components/ui/DensePageMobileNotice";
import { MEMORIES, OUTPUTS, PERMISSIONS } from "../features/agents/contractOptions";
import { extractApiErrorMessage } from "../utils/apiErrors";
import { queryKeys } from "../config/queryKeys";
import { Link as RouterLink } from "react-router-dom";

const DEFAULT_MARKDOWN = `---
name: New Specialist
role: specialist
capabilities: [planning]
tools_allowed: [fs_read]
permissions: read-only
escalation_path: manager
task_filters: [triage]
model:
  provider: openai
  model: gpt-4.1
memory_policy:
  scope: project-only
budget:
  token_budget: 4000
  time_budget_seconds: 300
  retry_budget: 1
output_schema: checklist
---

# Mission

Describe the work this agent owns.

# Rules

- Stay within the assigned task filters.

# Output Contract

Return a concise checklist with evidence and blockers.`;

const TOOL_ALIASES: Record<string, string> = { file_read_stub: "fs_read", web_search_stub: "web_search", python_analysis_stub: "code_execute", github_issue_stub: "github_comment", geospatial_analysis_stub: "code_execute" };

type Form = {
    name: string; slug: string; role: string; description: string; capabilities: string;
    allowed_tools: string[]; permissions: string; escalation_path: string; task_filters: string;
    provider: string; model: string; fallback_model: string; max_context: string;
    max_tokens: string; temperature: string; reasoning_level: string; reasoning_effort: string;
    tool_calling: boolean; structured_output: boolean; timeout_seconds: string; retry_count: string;
    memory_scope: string; token_budget: string; time_budget_seconds: string; retry_budget: string;
    budget_cap_usd: string; output_format: string;
};

const list = (value: string) => value.split(",").map((x) => x.trim()).filter(Boolean);
const agentForm = (agent: Agent | null): Form => {
    const policy = agent?.model_policy ?? {}, budget = agent?.budget ?? {}, memory = agent?.memory_policy ?? {}, output = agent?.output_schema ?? {};
    return {
        name: agent?.name ?? "New Specialist", slug: agent?.slug ?? "new-specialist", role: agent?.role ?? "specialist",
        description: agent?.description ?? "", capabilities: (agent?.capabilities ?? []).join(", "), allowed_tools: agent?.allowed_tools ?? [],
        permissions: typeof agent?.permissions === "string" ? agent.permissions : "read-only", escalation_path: agent?.escalation_path ?? "manager",
        task_filters: (agent?.task_filters ?? []).join(", "), provider: String(policy.provider ?? ""), model: String(policy.model ?? ""),
        fallback_model: String(policy.fallback_model ?? ""), max_context: String(policy.max_context ?? ""), temperature: String(policy.temperature ?? "0.2"),
        max_tokens: String(policy.max_tokens ?? ""), reasoning_level: String(policy.reasoning_level ?? "medium"),
        reasoning_effort: String(policy.reasoning_effort ?? policy.reasoning_level ?? "medium"),
        tool_calling: policy.tool_calling !== false, structured_output: Boolean(policy.structured_output),
        timeout_seconds: String(policy.timeout_seconds ?? agent?.timeout_seconds ?? "900"),
        retry_count: String(policy.retry_count ?? agent?.retry_limit ?? "1"), memory_scope: String(memory.scope ?? "project-only"),
        token_budget: String(budget.token_budget ?? "4000"), time_budget_seconds: String(budget.time_budget_seconds ?? "300"),
        retry_budget: String(budget.retry_budget ?? "1"), budget_cap_usd: String(budget.cost_cap_usd ?? budget.budget_cap_usd ?? ""),
        output_format: String(output.format ?? "checklist"),
    };
};

function contract(form: Form) {
    const model_policy = {
        provider: form.provider.trim() || undefined, model: form.model.trim() || undefined,
        fallback_model: form.fallback_model.trim() || undefined, max_context: form.max_context ? Number(form.max_context) : undefined,
        max_tokens: form.max_tokens ? Number(form.max_tokens) : undefined,
        temperature: form.temperature ? Number(form.temperature) : undefined, reasoning_level: form.reasoning_level || undefined,
        reasoning_effort: form.reasoning_effort || undefined, tool_calling: form.tool_calling,
        structured_output: form.structured_output, timeout_seconds: form.timeout_seconds ? Number(form.timeout_seconds) : undefined,
        retry_count: form.retry_count ? Number(form.retry_count) : undefined,
        permissions: form.permissions, escalation_path: form.escalation_path.trim() || undefined,
    };
    return {
        name: form.name.trim(), slug: form.slug.trim(), role: form.role.trim() || "specialist", description: form.description.trim() || null,
        capabilities: list(form.capabilities), allowed_tools: form.allowed_tools, permissions: form.permissions,
        escalation_path: form.escalation_path.trim() || null, task_filters: list(form.task_filters), model_policy,
        memory_policy: { scope: form.memory_scope },
        budget: {
            token_budget: Number(form.token_budget), time_budget_seconds: Number(form.time_budget_seconds),
            retry_budget: Number(form.retry_budget), cost_cap_usd: form.budget_cap_usd ? Number(form.budget_cap_usd) : undefined,
        },
        timeout_seconds: Number(form.timeout_seconds), retry_limit: Number(form.retry_count),
        output_schema: { format: form.output_format },
    };
}

export default function AgentProfilesPage() {
    const client = useQueryClient();
    const [projectId, setProjectId] = useState("");
    const [agentSearch, setAgentSearch] = useState("");
    const [selectedId, setSelectedId] = useState<string | null>(null);
    const [form, setForm] = useState<Form>(agentForm(null));
    const [markdown, setMarkdown] = useState(DEFAULT_MARKDOWN);
    const [tab, setTab] = useState(0);
    const [message, setMessage] = useState("");
    const [error, setError] = useState("");
    const [validation, setValidation] = useState<{ errors: string[]; warnings: string[]; ready: boolean } | null>(null);
    const [dryRun, setDryRun] = useState("");
    const { data: projects = [] } = useQuery({ queryKey: queryKeys.orchestration.projects, queryFn: listOrchestrationProjects });
    const { data: agents = [], isLoading: agentsLoading, error: agentsError } = useQuery({ queryKey: queryKeys.orchestration.agents(projectId || undefined), queryFn: () => listAgents(projectId || undefined) });
    const { data: tools = [] } = useQuery({ queryKey: queryKeys.orchestration.tools, queryFn: listTools });
    const { data: templates = [] } = useQuery({ queryKey: queryKeys.orchestration.agentTemplates, queryFn: listAgentTemplates });
    const filteredAgents = useMemo(() => {
        const q = agentSearch.trim().toLowerCase();
        if (!q) return agents;
        return agents.filter((item) =>
            [item.name, item.role, item.slug].some((value) => String(value ?? "").toLowerCase().includes(q)),
        );
    }, [agents, agentSearch]);
    const agent = useMemo(() => filteredAgents.find((item) => item.id === selectedId) ?? agents.find((item) => item.id === selectedId) ?? filteredAgents[0] ?? agents[0] ?? null, [agents, filteredAgents, selectedId]);
    const { data: versions = [] } = useQuery({ queryKey: queryKeys.orchestration.agentVersions(agent?.id ?? ""), queryFn: () => listAgentVersions(agent!.id), enabled: Boolean(agent?.id) });

    // The selected server profile is the source of truth when switching registry entries.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    useEffect(() => { if (agent) { setForm(agentForm(agent)); setMarkdown(agent.source_markdown || DEFAULT_MARKDOWN); } }, [agent]);
    const set = <K extends keyof Form>(key: K, value: Form[K]) => setForm((current) => ({ ...current, [key]: value }));
    const fail = (reason: unknown, fallback: string) => setError(extractApiErrorMessage(reason, fallback));

    const save = useMutation({
        mutationFn: () => {
            const payload = { ...contract(form), project_id: projectId || null, source_markdown: markdown };
            return agent ? updateAgent(agent.id, payload) : createAgent({ ...payload, system_prompt: markdown, mission_markdown: markdown, is_active: false });
        },
        onSuccess: (saved) => { setSelectedId(saved.id); setMessage(`Saved ${saved.name} as version ${saved.version}.`); void client.invalidateQueries({ queryKey: queryKeys.orchestration.agents() }); void client.invalidateQueries({ queryKey: queryKeys.orchestration.agentVersions(saved.id) }); },
        onError: (reason) => fail(reason, "Agent save failed."),
    });
    const validate = useMutation({
        mutationFn: () => validateAgentContract({ ...contract(form), project_id: projectId || null, source_markdown: markdown }),
        onSuccess: (result) => { setValidation({ errors: result.errors, warnings: result.warnings, ready: result.activation_ready }); setMessage(result.activation_ready ? "Contract is activation-ready." : "Contract needs attention before activation."); },
        onError: (reason) => fail(reason, "Validation failed."),
    });
    const template = useMutation({
        mutationFn: (item: AgentTemplate) => createAgentFromTemplate(item.slug, { project_id: projectId || null, name: `${item.name} ${agents.length + 1}`, slug: `${item.slug}-${Date.now()}` }),
        onSuccess: (created) => { setSelectedId(created.id); setMessage(`Created ${created.name} from template.`); void client.invalidateQueries({ queryKey: queryKeys.orchestration.agents() }); },
        onError: (reason) => fail(reason, "Template creation failed."),
    });
    const action = useMutation({
        mutationFn: (kind: "activate" | "deactivate" | "duplicate") => !agent ? Promise.reject(new Error("Select an agent first.")) : kind === "duplicate" ? duplicateAgent(agent.id) : activateAgent(agent.id, kind === "activate"),
        onSuccess: (result, kind) => { setSelectedId(result.id); setMessage(kind === "duplicate" ? `Duplicated as ${result.name}.` : `${result.name} is now ${result.is_active ? "active" : "inactive"}.`); void client.invalidateQueries({ queryKey: queryKeys.orchestration.agents() }); },
        onError: (reason) => fail(reason, "Agent action failed."),
    });
    const run = useMutation({
        mutationFn: () => !agent ? Promise.reject(new Error("Save an agent before running a dry run.")) : testRunAgent(agent.id, { task_title: "Registry contract dry run", task_description: form.description || "Verify the agent contract.", task_labels: list(form.task_filters) }),
        onSuccess: (result) => { setDryRun(result.output_text); setMessage(`Dry run completed in ${result.latency_ms}ms.`); },
        onError: (reason) => fail(reason, "Dry run failed."),
    });

    return <PageShell maxWidth="xl">
        <PageHeader
            title="Agents"
            description="Versioned worker contracts. Install packs from Marketplace, attach Skills, or compose teams in Hierarchy."
            actions={
                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                    <Button component={RouterLink} to="/marketplace" size="small" variant="outlined">Marketplace</Button>
                    <Button component={RouterLink} to="/skills" size="small" variant="outlined">Skills</Button>
                    <Button component={RouterLink} to="/hierarchy" size="small" variant="outlined">Hierarchy</Button>
                    <Button variant="outlined" startIcon={<AddIcon />} onClick={() => { setSelectedId(null); setForm(agentForm(null)); setMarkdown(DEFAULT_MARKDOWN); }}>New draft</Button>
                </Stack>
            }
        />
        <DensePageMobileNotice surface="Agents catalog" />
        <FilterToolbar>
            <TextField
                label="Search"
                size="small"
                value={agentSearch}
                onChange={(e) => setAgentSearch(e.target.value)}
                placeholder="Name, role, or slug"
                sx={{ minWidth: { sm: 220 }, flex: 1 }}
            />
            <TextField select label="Project scope" size="small" value={projectId} onChange={(e) => { setProjectId(e.target.value); setSelectedId(null); }} sx={{ minWidth: 200 }}>
                <MenuItem value="">Global agents</MenuItem>
                {projects.map((item) => <MenuItem key={item.id} value={item.id}>{item.name}</MenuItem>)}
            </TextField>
        </FilterToolbar>
        {error && <Alert severity="error" onClose={() => setError("")}>{error}</Alert>}{message && <Alert severity="info" onClose={() => setMessage("")}>{message}</Alert>}
        <QueryState
            loading={agentsLoading}
            error={agentsError}
            onRetry={() => { void client.invalidateQueries({ queryKey: queryKeys.orchestration.agents(projectId || undefined) }); }}
        >
        <InspectorSplit
            variant="list-detail"
            secondaryWidth={320}
            hideSecondaryOnMobile={false}
            primary={
                <Stack spacing={2}>
                    <Paper sx={{ p: 2, borderRadius: 1 }}>
                        <Typography variant="subtitle1">Registry</Typography>
                        <Typography variant="caption" color="text.secondary">{filteredAgents.length} profiles in this scope</Typography>
                        <Stack spacing={1} sx={{ mt: 1.5 }}>
                            {filteredAgents.map((item) => (
                                <Button key={item.id} variant={agent?.id === item.id ? "contained" : "outlined"} onClick={() => setSelectedId(item.id)} sx={{ justifyContent: "flex-start", textAlign: "left" }}>
                                    <Box>
                                        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                                            <Typography variant="body2">{item.name}</Typography>
                                            <StatusChip status={item.is_active ? "active" : "draft"} kind="project" size="small" showIcon={false} />
                                        </Stack>
                                        <Typography variant="caption">{item.role} · v{item.version}</Typography>
                                    </Box>
                                </Button>
                            ))}
                            {filteredAgents.length === 0 && (
                                agents.length === 0 ? (
                                    <EmptyState
                                        icon={<AgentIcon />}
                                        title="No agents in this scope"
                                        description="Create a draft contract or install a validated template to start the registry."
                                        action={
                                            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                                                <Button
                                                    size="small"
                                                    variant="contained"
                                                    startIcon={<AddIcon />}
                                                    onClick={() => {
                                                        setSelectedId(null);
                                                        setForm(agentForm(null));
                                                        setMarkdown(DEFAULT_MARKDOWN);
                                                    }}
                                                >
                                                    New draft
                                                </Button>
                                                {templates[0] ? (
                                                    <Button
                                                        size="small"
                                                        variant="outlined"
                                                        disabled={template.isPending}
                                                        onClick={() => template.mutate(templates[0])}
                                                    >
                                                        Use template
                                                    </Button>
                                                ) : (
                                                    <Button size="small" variant="outlined" component={RouterLink} to="/marketplace">
                                                        Browse Marketplace
                                                    </Button>
                                                )}
                                            </Stack>
                                        }
                                    />
                                ) : (
                                    <Typography color="text.secondary">No agents match the current filters.</Typography>
                                )
                            )}
                        </Stack>
                    </Paper>
                    <Paper sx={{ p: 2, borderRadius: 1 }}>
                        <Typography variant="subtitle1">Templates</Typography>
                        <Typography variant="caption" color="text.secondary">Validated starting points with inheritance and skill composition.</Typography>
                        <Stack spacing={1} sx={{ mt: 1.5 }}>
                            {templates.map((item) => (
                                <Button key={item.slug} size="small" variant="outlined" disabled={template.isPending} onClick={() => template.mutate(item)} sx={{ justifyContent: "space-between", textTransform: "none" }}>
                                    <span>{item.name}</span>
                                    <Typography variant="caption">{item.role}</Typography>
                                </Button>
                            ))}
                        </Stack>
                    </Paper>
                </Stack>
            }
            secondary={
            <Paper sx={{ p: { xs: 2, md: 3 }, borderRadius: 1 }}><Stack spacing={2}><Stack direction={{ xs: "column", md: "row" }} justifyContent="space-between" spacing={1}><Box><Typography variant="h5">{agent?.name ?? "New agent contract"}</Typography>{agent && <Typography color="text.secondary">{agent.role} · {String(agent.model_policy.provider ?? "provider")} / {String(agent.model_policy.model ?? "model not set")} · v{agent.version}</Typography>}</Box>{agent && <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap><Button size="small" variant="outlined" startIcon={<ContentCopy />} onClick={() => action.mutate("duplicate")}>Duplicate</Button><Button size="small" variant={agent.is_active ? "outlined" : "contained"} startIcon={agent.is_active ? <CheckCircleOutline /> : <Publish />} onClick={() => action.mutate(agent.is_active ? "deactivate" : "activate")}>{agent.is_active ? "Deactivate" : "Activate"}</Button><Button size="small" variant="outlined" startIcon={<PlayArrow />} onClick={() => run.mutate()}>Dry run</Button></Stack>}</Stack>
                <Tabs value={tab} onChange={(_, value) => setTab(value)} variant="scrollable"><Tab label="Contract" /><Tab label="Instructions" /><Tab label={`Versions (${versions.length})`} /><Tab label="Validation" /></Tabs>
                {tab === 0 && <FormFieldStack>
                    <Subsection title="Identity">
                    <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" }, gap: 2 }}>
                        <TextField label="Name" size="small" value={form.name} onChange={(e) => set("name", e.target.value)} />
                        <TextField label="Slug" size="small" value={form.slug} onChange={(e) => set("slug", e.target.value)} />
                        <TextField label="Role" size="small" value={form.role} onChange={(e) => set("role", e.target.value)} />
                        <TextField select label="Permission level" size="small" value={form.permissions} onChange={(e) => set("permissions", e.target.value)}>{PERMISSIONS.map((value) => <MenuItem key={value} value={value}>{value}</MenuItem>)}</TextField>
                    </Box>
                    </Subsection>
                    <TextField label="Description" size="small" value={form.description} onChange={(e) => set("description", e.target.value)} multiline minRows={2} />
                    <TextField label="Capabilities" size="small" value={form.capabilities} onChange={(e) => set("capabilities", e.target.value)} helperText="Comma-separated capabilities" />
                    <TextField label="Escalation path" size="small" value={form.escalation_path} onChange={(e) => set("escalation_path", e.target.value)} />
                    <TextField label="Task filters" size="small" value={form.task_filters} onChange={(e) => set("task_filters", e.target.value)} helperText="Comma-separated tags or regular expressions" />
                    <Typography variant="subtitle2">Allowed tools</Typography>
                    <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">{tools.map((tool) => { const name = TOOL_ALIASES[tool.name] ?? tool.name; return <Chip key={tool.name} label={name} color={form.allowed_tools.includes(name) ? "primary" : "default"} variant={form.allowed_tools.includes(name) ? "filled" : "outlined"} onClick={() => set("allowed_tools", form.allowed_tools.includes(name) ? form.allowed_tools.filter((item) => item !== name) : [...form.allowed_tools, name])} />; })}</Stack>
                    <Divider />
                    <Subsection title="Model policy" info="These settings are passed to the provider router for every run of this agent.">
                    <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "repeat(2, minmax(0, 1fr))" }, gap: 2 }}>
                        <TextField label="Provider" size="small" value={form.provider} onChange={(e) => set("provider", e.target.value)} />
                        <TextField label="Primary model" size="small" value={form.model} onChange={(e) => set("model", e.target.value)} />
                        <TextField label="Fallback model" size="small" value={form.fallback_model} onChange={(e) => set("fallback_model", e.target.value)} />
                        <TextField label="Max context tokens" size="small" type="number" value={form.max_context} onChange={(e) => set("max_context", e.target.value)} />
                        <TextField label="Max output tokens" size="small" type="number" value={form.max_tokens} onChange={(e) => set("max_tokens", e.target.value)} inputProps={{ min: 128 }} />
                        <TextField label="Temperature" size="small" type="number" value={form.temperature} onChange={(e) => set("temperature", e.target.value)} inputProps={{ min: 0, max: 2, step: 0.1 }} />
                        <TextField label="Reasoning effort" size="small" value={form.reasoning_effort} onChange={(e) => { set("reasoning_effort", e.target.value); set("reasoning_level", e.target.value); }} helperText="Provider-specific effort such as low, medium, or high." />
                        <TextField label="Timeout (seconds)" size="small" type="number" value={form.timeout_seconds} onChange={(e) => set("timeout_seconds", e.target.value)} inputProps={{ min: 10, max: 14400 }} />
                        <TextField label="Retry count" size="small" type="number" value={form.retry_count} onChange={(e) => set("retry_count", e.target.value)} inputProps={{ min: 0, max: 10 }} />
                        <TextField select label="Tool calling" size="small" value={String(form.tool_calling)} onChange={(e) => set("tool_calling", e.target.value === "true")}><MenuItem value="true">Enabled</MenuItem><MenuItem value="false">Disabled</MenuItem></TextField>
                        <TextField select label="Structured output" size="small" value={String(form.structured_output)} onChange={(e) => set("structured_output", e.target.value === "true")}><MenuItem value="true">Enabled (JSON)</MenuItem><MenuItem value="false">Disabled (text)</MenuItem></TextField>
                    </Box>
                    </Subsection>
                    <Subsection title="Memory, budget, and output">
                    <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "repeat(2, 1fr)" }, gap: 2 }}>
                        <TextField select label="Memory scope" size="small" value={form.memory_scope} onChange={(e) => set("memory_scope", e.target.value)}>{MEMORIES.map((value) => <MenuItem key={value} value={value}>{value}</MenuItem>)}</TextField>
                        <TextField select label="Output schema" size="small" value={form.output_format} onChange={(e) => set("output_format", e.target.value)}>{OUTPUTS.map((value) => <MenuItem key={value} value={value}>{value}</MenuItem>)}</TextField>
                        <TextField label="Token budget" size="small" type="number" value={form.token_budget} onChange={(e) => set("token_budget", e.target.value)} />
                        <TextField label="Budget cap (USD)" size="small" type="number" value={form.budget_cap_usd} onChange={(e) => set("budget_cap_usd", e.target.value)} inputProps={{ min: 0, step: 0.01 }} />
                        <TextField label="Time budget (seconds)" size="small" type="number" value={form.time_budget_seconds} onChange={(e) => set("time_budget_seconds", e.target.value)} />
                        <TextField label="Retry budget" size="small" type="number" value={form.retry_budget} onChange={(e) => set("retry_budget", e.target.value)} />
                    </Box>
                    </Subsection>
                </FormFieldStack>}
                {tab === 1 && <Stack spacing={2}><Typography color="text.secondary">Markdown is the portable instruction source. Structured fields above are stored alongside it and override matching frontmatter.</Typography><TextField label="Agent markdown" value={markdown} onChange={(e) => setMarkdown(e.target.value)} multiline minRows={24} fullWidth sx={{ "& textarea": { fontFamily: "monospace", fontSize: 13 } }} /></Stack>}
                {tab === 2 && <Stack spacing={1.5}>{versions.map((version) => <Paper key={version.id} variant="outlined" sx={{ p: 1.5 }}><Stack direction="row" justifyContent="space-between"><Typography variant="subtitle2">Version {version.version_number}</Typography><Typography variant="caption" color="text.secondary">{new Date(version.created_at).toLocaleString()}</Typography></Stack><Typography variant="caption" color="text.secondary">{version.source_markdown ? `${version.source_markdown.slice(0, 180)}${version.source_markdown.length > 180 ? "…" : ""}` : "Structured contract snapshot"}</Typography></Paper>)}{versions.length === 0 && <Typography color="text.secondary">Save the first contract version to begin history.</Typography>}</Stack>}
                {tab === 3 && <Stack spacing={1.5}><Typography color="text.secondary">Lint checks markdown, tools, models, budgets, filters, output format, memory scope, permissions, and escalation before activation.</Typography>{validation && <><Alert severity={validation.ready ? "success" : "warning"}>{validation.ready ? "Activation-ready" : "Needs attention"}</Alert>{validation.errors.map((item) => <Alert key={item} severity="error">{item}</Alert>)}{validation.warnings.map((item) => <Alert key={item} severity="warning">{item}</Alert>)}</>}{dryRun && <><Divider /><Typography variant="subtitle2">Dry-run output</Typography><Paper variant="outlined" sx={{ p: 2, whiteSpace: "pre-wrap", fontFamily: "monospace", fontSize: 13 }}>{dryRun}</Paper></>}</Stack>}
                <Divider /><Stack direction={{ xs: "column", sm: "row" }} spacing={1} justifyContent="flex-end"><Button variant="outlined" onClick={() => validate.mutate()} disabled={validate.isPending}>{validate.isPending ? "Validating…" : "Validate contract"}</Button><Button variant="contained" startIcon={<UploadFile />} onClick={() => save.mutate()} disabled={save.isPending}>{save.isPending ? "Saving…" : agent ? "Save new version" : "Register agent"}</Button></Stack>
            </Stack></Paper>
            }
        />
        </QueryState>
    </PageShell>;
}
