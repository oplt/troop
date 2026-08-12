import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Box, Button, Chip, Divider, MenuItem, Paper, Stack, Tab, Tabs, TextField, Typography } from "@mui/material";
import { Add as AddIcon, CheckCircleOutline, ContentCopy, PlayArrow, Publish, UploadFile } from "@mui/icons-material";
import {
    activateAgent, createAgent, createAgentFromTemplate, duplicateAgent, listAgentTemplates,
    listAgentVersions, listAgents, listOrchestrationProjects, listTools, testRunAgent,
    updateAgent, validateAgentContract, type Agent, type AgentTemplate,
} from "../api/orchestration";
import { PageShell } from "../components/ui/PageShell";
import { extractApiErrorMessage } from "../utils/apiErrors";
import { queryKeys } from "../config/queryKeys";

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

const PERMISSIONS = ["read-only", "comment-only", "code-write", "merge-blocked"];
const MEMORIES = ["none", "project-only", "long-term"];
const OUTPUTS = ["checklist", "json", "patch_proposal", "issue_reply", "adr"];
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
    const [selectedId, setSelectedId] = useState<string | null>(null);
    const [form, setForm] = useState<Form>(agentForm(null));
    const [markdown, setMarkdown] = useState(DEFAULT_MARKDOWN);
    const [tab, setTab] = useState(0);
    const [message, setMessage] = useState("");
    const [error, setError] = useState("");
    const [validation, setValidation] = useState<{ errors: string[]; warnings: string[]; ready: boolean } | null>(null);
    const [dryRun, setDryRun] = useState("");
    const { data: projects = [] } = useQuery({ queryKey: queryKeys.orchestration.projects, queryFn: listOrchestrationProjects });
    const { data: agents = [] } = useQuery({ queryKey: queryKeys.orchestration.agents(projectId || undefined), queryFn: () => listAgents(projectId || undefined) });
    const { data: tools = [] } = useQuery({ queryKey: queryKeys.orchestration.tools, queryFn: listTools });
    const { data: templates = [] } = useQuery({ queryKey: queryKeys.orchestration.agentTemplates, queryFn: listAgentTemplates });
    const agent = useMemo(() => agents.find((item) => item.id === selectedId) ?? agents[0] ?? null, [agents, selectedId]);
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
        <Paper sx={{ p: { xs: 2.5, md: 3 }, borderRadius: 1 }}><Stack direction={{ xs: "column", md: "row" }} justifyContent="space-between" spacing={2}>
            <Box><Typography variant="overline" color="text.secondary">Agent registry</Typography><Typography variant="h3">Versioned workers with explicit contracts</Typography><Typography color="text.secondary" sx={{ mt: 1, maxWidth: 760 }}>Define identity, capabilities, tools, model policy, memory, permissions, escalation, budgets, filters, and output shape before an agent can run.</Typography></Box>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={1}><TextField select label="Project scope" value={projectId} onChange={(e) => { setProjectId(e.target.value); setSelectedId(null); }} sx={{ minWidth: 220 }}><MenuItem value="">Global agents</MenuItem>{projects.map((item) => <MenuItem key={item.id} value={item.id}>{item.name}</MenuItem>)}</TextField><Button variant="outlined" startIcon={<AddIcon />} onClick={() => { setSelectedId(null); setForm(agentForm(null)); setMarkdown(DEFAULT_MARKDOWN); }}>New draft</Button></Stack>
        </Stack></Paper>
        {error && <Alert severity="error" onClose={() => setError("")}>{error}</Alert>}{message && <Alert severity="info" onClose={() => setMessage("")}>{message}</Alert>}
        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", lg: "320px minmax(0, 1fr)" }, gap: 3 }}>
            <Stack spacing={2}><Paper sx={{ p: 2, borderRadius: 1 }}><Typography variant="subtitle1">Registry</Typography><Typography variant="caption" color="text.secondary">{agents.length} profiles in this scope</Typography><Stack spacing={1} sx={{ mt: 1.5 }}>{agents.map((item) => <Button key={item.id} variant={agent?.id === item.id ? "contained" : "outlined"} onClick={() => setSelectedId(item.id)} sx={{ justifyContent: "flex-start", textAlign: "left" }}><Box><Typography variant="body2">{item.name}</Typography><Typography variant="caption">{item.role} · v{item.version} · {item.is_active ? "active" : "inactive"}</Typography></Box></Button>)}{agents.length === 0 && <Typography color="text.secondary">No agents in this scope yet.</Typography>}</Stack></Paper><Paper sx={{ p: 2, borderRadius: 1 }}><Typography variant="subtitle1">Templates</Typography><Typography variant="caption" color="text.secondary">Validated starting points with inheritance and skill composition.</Typography><Stack spacing={1} sx={{ mt: 1.5 }}>{templates.map((item) => <Button key={item.slug} size="small" variant="outlined" disabled={template.isPending} onClick={() => template.mutate(item)} sx={{ justifyContent: "space-between", textTransform: "none" }}><span>{item.name}</span><Typography variant="caption">{item.role}</Typography></Button>)}</Stack></Paper></Stack>
            <Paper sx={{ p: { xs: 2, md: 3 }, borderRadius: 1 }}><Stack spacing={2}><Stack direction={{ xs: "column", md: "row" }} justifyContent="space-between" spacing={1}><Box><Typography variant="h5">{agent?.name ?? "New agent contract"}</Typography>{agent && <Typography color="text.secondary">{agent.role} · {String(agent.model_policy.provider ?? "provider")} / {String(agent.model_policy.model ?? "model not set")} · v{agent.version}</Typography>}</Box>{agent && <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap><Button size="small" variant="outlined" startIcon={<ContentCopy />} onClick={() => action.mutate("duplicate")}>Duplicate</Button><Button size="small" variant={agent.is_active ? "outlined" : "contained"} startIcon={agent.is_active ? <CheckCircleOutline /> : <Publish />} onClick={() => action.mutate(agent.is_active ? "deactivate" : "activate")}>{agent.is_active ? "Deactivate" : "Activate"}</Button><Button size="small" variant="outlined" startIcon={<PlayArrow />} onClick={() => run.mutate()}>Dry run</Button></Stack>}</Stack>
                <Tabs value={tab} onChange={(_, value) => setTab(value)} variant="scrollable"><Tab label="Contract" /><Tab label="Instructions" /><Tab label={`Versions (${versions.length})`} /><Tab label="Validation" /></Tabs>
                {tab === 0 && <Stack spacing={2}>
                    <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" }, gap: 2 }}>
                        <TextField label="Name" value={form.name} onChange={(e) => set("name", e.target.value)} />
                        <TextField label="Slug" value={form.slug} onChange={(e) => set("slug", e.target.value)} />
                        <TextField label="Role" value={form.role} onChange={(e) => set("role", e.target.value)} />
                        <TextField select label="Permission level" value={form.permissions} onChange={(e) => set("permissions", e.target.value)}>{PERMISSIONS.map((value) => <MenuItem key={value} value={value}>{value}</MenuItem>)}</TextField>
                    </Box>
                    <TextField label="Description" value={form.description} onChange={(e) => set("description", e.target.value)} multiline minRows={2} />
                    <TextField label="Capabilities" value={form.capabilities} onChange={(e) => set("capabilities", e.target.value)} helperText="Comma-separated capabilities" />
                    <TextField label="Escalation path" value={form.escalation_path} onChange={(e) => set("escalation_path", e.target.value)} />
                    <TextField label="Task filters" value={form.task_filters} onChange={(e) => set("task_filters", e.target.value)} helperText="Comma-separated tags or regular expressions" />
                    <Typography variant="subtitle2">Allowed tools</Typography>
                    <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">{tools.map((tool) => { const name = TOOL_ALIASES[tool.name] ?? tool.name; return <Chip key={tool.name} label={name} color={form.allowed_tools.includes(name) ? "primary" : "default"} variant={form.allowed_tools.includes(name) ? "filled" : "outlined"} onClick={() => set("allowed_tools", form.allowed_tools.includes(name) ? form.allowed_tools.filter((item) => item !== name) : [...form.allowed_tools, name])} />; })}</Stack>
                    <Divider />
                    <Typography variant="subtitle2">Model policy</Typography>
                    <Typography variant="caption" color="text.secondary">These settings are passed to the provider router for every run of this agent.</Typography>
                    <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "repeat(2, minmax(0, 1fr))" }, gap: 2 }}>
                        <TextField label="Provider" value={form.provider} onChange={(e) => set("provider", e.target.value)} />
                        <TextField label="Primary model" value={form.model} onChange={(e) => set("model", e.target.value)} />
                        <TextField label="Fallback model" value={form.fallback_model} onChange={(e) => set("fallback_model", e.target.value)} />
                        <TextField label="Max context tokens" type="number" value={form.max_context} onChange={(e) => set("max_context", e.target.value)} />
                        <TextField label="Max output tokens" type="number" value={form.max_tokens} onChange={(e) => set("max_tokens", e.target.value)} inputProps={{ min: 128 }} />
                        <TextField label="Temperature" type="number" value={form.temperature} onChange={(e) => set("temperature", e.target.value)} inputProps={{ min: 0, max: 2, step: 0.1 }} />
                        <TextField label="Reasoning effort" value={form.reasoning_effort} onChange={(e) => { set("reasoning_effort", e.target.value); set("reasoning_level", e.target.value); }} helperText="Provider-specific effort such as low, medium, or high." />
                        <TextField label="Timeout (seconds)" type="number" value={form.timeout_seconds} onChange={(e) => set("timeout_seconds", e.target.value)} inputProps={{ min: 10, max: 14400 }} />
                        <TextField label="Retry count" type="number" value={form.retry_count} onChange={(e) => set("retry_count", e.target.value)} inputProps={{ min: 0, max: 10 }} />
                        <TextField select label="Tool calling" value={String(form.tool_calling)} onChange={(e) => set("tool_calling", e.target.value === "true")}><MenuItem value="true">Enabled</MenuItem><MenuItem value="false">Disabled</MenuItem></TextField>
                        <TextField select label="Structured output" value={String(form.structured_output)} onChange={(e) => set("structured_output", e.target.value === "true")}><MenuItem value="true">Enabled (JSON)</MenuItem><MenuItem value="false">Disabled (text)</MenuItem></TextField>
                    </Box>
                    <Typography variant="subtitle2">Memory, budget, and output</Typography>
                    <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "repeat(2, 1fr)" }, gap: 2 }}>
                        <TextField select label="Memory scope" value={form.memory_scope} onChange={(e) => set("memory_scope", e.target.value)}>{MEMORIES.map((value) => <MenuItem key={value} value={value}>{value}</MenuItem>)}</TextField>
                        <TextField select label="Output schema" value={form.output_format} onChange={(e) => set("output_format", e.target.value)}>{OUTPUTS.map((value) => <MenuItem key={value} value={value}>{value}</MenuItem>)}</TextField>
                        <TextField label="Token budget" type="number" value={form.token_budget} onChange={(e) => set("token_budget", e.target.value)} />
                        <TextField label="Budget cap (USD)" type="number" value={form.budget_cap_usd} onChange={(e) => set("budget_cap_usd", e.target.value)} inputProps={{ min: 0, step: 0.01 }} />
                        <TextField label="Time budget (seconds)" type="number" value={form.time_budget_seconds} onChange={(e) => set("time_budget_seconds", e.target.value)} />
                        <TextField label="Retry budget" type="number" value={form.retry_budget} onChange={(e) => set("retry_budget", e.target.value)} />
                    </Box>
                </Stack>}
                {tab === 1 && <Stack spacing={2}><Typography color="text.secondary">Markdown is the portable instruction source. Structured fields above are stored alongside it and override matching frontmatter.</Typography><TextField label="Agent markdown" value={markdown} onChange={(e) => setMarkdown(e.target.value)} multiline minRows={24} fullWidth sx={{ "& textarea": { fontFamily: "monospace", fontSize: 13 } }} /></Stack>}
                {tab === 2 && <Stack spacing={1.5}>{versions.map((version) => <Paper key={version.id} variant="outlined" sx={{ p: 1.5 }}><Stack direction="row" justifyContent="space-between"><Typography variant="subtitle2">Version {version.version_number}</Typography><Typography variant="caption" color="text.secondary">{new Date(version.created_at).toLocaleString()}</Typography></Stack><Typography variant="caption" color="text.secondary">{version.source_markdown ? `${version.source_markdown.slice(0, 180)}${version.source_markdown.length > 180 ? "…" : ""}` : "Structured contract snapshot"}</Typography></Paper>)}{versions.length === 0 && <Typography color="text.secondary">Save the first contract version to begin history.</Typography>}</Stack>}
                {tab === 3 && <Stack spacing={1.5}><Typography color="text.secondary">Lint checks markdown, tools, models, budgets, filters, output format, memory scope, permissions, and escalation before activation.</Typography>{validation && <><Alert severity={validation.ready ? "success" : "warning"}>{validation.ready ? "Activation-ready" : "Needs attention"}</Alert>{validation.errors.map((item) => <Alert key={item} severity="error">{item}</Alert>)}{validation.warnings.map((item) => <Alert key={item} severity="warning">{item}</Alert>)}</>}{dryRun && <><Divider /><Typography variant="subtitle2">Dry-run output</Typography><Paper variant="outlined" sx={{ p: 2, whiteSpace: "pre-wrap", fontFamily: "monospace", fontSize: 13 }}>{dryRun}</Paper></>}</Stack>}
                <Divider /><Stack direction={{ xs: "column", sm: "row" }} spacing={1} justifyContent="flex-end"><Button variant="outlined" onClick={() => validate.mutate()} disabled={validate.isPending}>{validate.isPending ? "Validating…" : "Validate contract"}</Button><Button variant="contained" startIcon={<UploadFile />} onClick={() => save.mutate()} disabled={save.isPending}>{save.isPending ? "Saving…" : agent ? "Save new version" : "Register agent"}</Button></Stack>
            </Stack></Paper>
        </Box>
    </PageShell>;
}
