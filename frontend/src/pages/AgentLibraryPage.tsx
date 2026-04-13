import { useEffect, useMemo, useState, type DragEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocation } from "react-router-dom";
import {
    Alert,
    Box,
    Button,
    Chip,
    CircularProgress,
    Dialog,
    DialogActions,
    DialogContent,
    DialogTitle,
    Divider,
    MenuItem,
    Paper,
    Stack,
    Switch,
    Tab,
    Tabs,
    TextField,
    Typography,
} from "@mui/material";
import {
    CloudUpload as UploadIcon,
    ContentCopy as DuplicateIcon,
    PlayArrow as TestRunIcon,
    SmartToy as AgentIcon,
    AutoFixHigh as InheritanceIcon,
} from "@mui/icons-material";
import {
    activateAgent,
    createAgent,
    createAgentFromTemplate,
    duplicateAgent,
    importAgentMarkdown,
    listAgents,
    listAgentTemplates,
    listAgentVersions,
    listSkillCatalog,
    testRunAgent,
    updateAgent,
    validateAgentMarkdown,
} from "../api/orchestration";
import type {
    Agent,
    AgentInheritancePreview,
    AgentTemplate,
    SkillPack,
} from "../api/orchestration";
import { useSnackbar } from "../app/snackbarContext";
import { EmptyState } from "../components/ui/EmptyState";
import { PageHeader } from "../components/ui/PageHeader";
import { PageShell } from "../components/ui/PageShell";
import { SectionCard } from "../components/ui/SectionCard";
import { formatDateTime } from "../utils/formatters";

const MEMORY_SCOPE_OPTIONS = ["none", "project-only", "long-term"] as const;
const OUTPUT_FORMAT_OPTIONS = ["checklist", "json", "patch_proposal", "issue_reply", "adr"] as const;
const PERMISSION_OPTIONS = ["read-only", "comment-only", "code-write", "merge-blocked"] as const;

const EMPTY_FORM = {
    name: "",
    slug: "",
    description: "",
    role: "specialist",
    system_prompt: "",
    parent_template_slug: "",
    capabilities: "",
    allowed_tools: "",
    skills: [] as string[],
    tags: "",
    task_filters: "",
    model: "",
    fallback_model: "",
    escalation_path: "",
    permission: "read-only",
    memory_scope: "project-only",
    output_format: "json",
    token_budget: "8000",
    time_budget_seconds: "300",
    retry_budget: "1",
};

function parseCsv(value: string) {
    return value
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
}

function skillDisplayName(slug: string, catalog: SkillPack[]) {
    return catalog.find((item) => item.slug === slug)?.name ?? slug;
}

function mergeUnique(...items: string[][]) {
    const merged: string[] = [];
    items.flat().forEach((item) => {
        if (item && !merged.includes(item)) merged.push(item);
    });
    return merged;
}

function getTemplateBySlug(templates: AgentTemplate[], slug: string) {
    return templates.find((item) => item.slug === slug) ?? null;
}

function buildInheritancePreview(
    form: typeof EMPTY_FORM,
    templates: AgentTemplate[],
    skills: SkillPack[],
): AgentInheritancePreview | null {
    const template = form.parent_template_slug ? getTemplateBySlug(templates, form.parent_template_slug) : null;
    if (!template) {
        return null;
    }
    const selectedSkills = skills.filter((item) => form.skills.includes(item.slug));
    const inheritedCapabilities = mergeUnique(
        template.capabilities,
        selectedSkills.flatMap((item) => item.capabilities),
    );
    const inheritedTools = mergeUnique(
        template.allowed_tools,
        selectedSkills.flatMap((item) => item.allowed_tools),
    );
    const inheritedTags = mergeUnique(template.tags, selectedSkills.flatMap((item) => item.tags));
    const overriddenFields: Record<string, unknown> = {};
    const explicitCapabilities = parseCsv(form.capabilities);
    const explicitTools = parseCsv(form.allowed_tools);
    const explicitTags = parseCsv(form.tags);
    if (explicitCapabilities.length > 0) overriddenFields.capabilities = explicitCapabilities;
    if (explicitTools.length > 0) overriddenFields.allowed_tools = explicitTools;
    if (explicitTags.length > 0) overriddenFields.tags = explicitTags;
    if (form.system_prompt.trim()) overriddenFields.system_prompt = form.system_prompt.trim();

    return {
        parent_template_slug: template.slug,
        inherited_fields: {
            capabilities: inheritedCapabilities,
            allowed_tools: inheritedTools,
            skills: template.skills,
            tags: inheritedTags,
            rules_markdown: template.rules_markdown,
            budget: template.budget,
            memory_policy: template.memory_policy,
            output_schema: template.output_schema,
            model_policy: template.model_policy,
        },
        overridden_fields: overriddenFields,
        effective: {
            capabilities: mergeUnique(inheritedCapabilities, explicitCapabilities),
            allowed_tools: mergeUnique(inheritedTools, explicitTools),
            skills: mergeUnique(template.skills, form.skills),
            tags: mergeUnique(inheritedTags, explicitTags),
            rules_markdown: template.rules_markdown,
            budget: {
                ...template.budget,
                token_budget: Number(form.token_budget || 0),
                time_budget_seconds: Number(form.time_budget_seconds || 0),
                retry_budget: Number(form.retry_budget || 0),
            },
            memory_policy: { scope: form.memory_scope },
            output_schema: { format: form.output_format },
            model_policy: {
                ...template.model_policy,
                model: form.model || null,
                fallback_model: form.fallback_model || null,
                escalation_path: form.escalation_path || null,
                permissions: form.permission,
            },
        },
    };
}

function TestRunDialog({ agent, onClose }: { agent: Agent; onClose: () => void }) {
    const [form, setForm] = useState({
        task_title: "Dry-run task",
        task_description: "",
        acceptance_criteria: "",
        task_labels: "backend,api",
        task_metadata: '{\n  "tool_calls": []\n}',
    });
    const [error, setError] = useState<string | null>(null);
    const [result, setResult] = useState<Awaited<ReturnType<typeof testRunAgent>> | null>(null);

    const runMutation = useMutation({
        mutationFn: async () =>
            testRunAgent(agent.id, {
                task_title: form.task_title,
                task_description: form.task_description || undefined,
                acceptance_criteria: form.acceptance_criteria || undefined,
                task_labels: parseCsv(form.task_labels),
                task_metadata: JSON.parse(form.task_metadata || "{}"),
            }),
        onSuccess: (data) => {
            setError(null);
            setResult(data);
        },
        onError: (err) => {
            setResult(null);
            setError(err instanceof Error ? err.message : "Test run failed.");
        },
    });

    return (
        <Dialog open onClose={onClose} maxWidth="md" fullWidth>
            <DialogTitle>Test run — {agent.name}</DialogTitle>
            <DialogContent>
                <Stack spacing={2} sx={{ mt: 1 }}>
                    <TextField label="Task title" value={form.task_title} onChange={(event) => setForm((current) => ({ ...current, task_title: event.target.value }))} />
                    <TextField label="Task description" multiline minRows={3} value={form.task_description} onChange={(event) => setForm((current) => ({ ...current, task_description: event.target.value }))} />
                    <TextField label="Acceptance criteria" multiline minRows={2} value={form.acceptance_criteria} onChange={(event) => setForm((current) => ({ ...current, acceptance_criteria: event.target.value }))} />
                    <TextField label="Task labels" helperText="Comma-separated" value={form.task_labels} onChange={(event) => setForm((current) => ({ ...current, task_labels: event.target.value }))} />
                    <TextField label="Task metadata JSON" multiline minRows={6} value={form.task_metadata} onChange={(event) => setForm((current) => ({ ...current, task_metadata: event.target.value }))} />
                    {error && <Alert severity="error">{error}</Alert>}
                    {result && (
                        <Stack spacing={2}>
                            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                                <Chip label={`${result.token_total} tokens`} size="small" variant="outlined" />
                                <Chip label={`${result.latency_ms} ms`} size="small" variant="outlined" />
                                <Chip label={`$${result.estimated_cost_usd.toFixed(4)}`} size="small" variant="outlined" />
                            </Stack>
                            <SectionCard title="Trace" description="Dry-run execution trace without GitHub side effects or task completion.">
                                <Stack spacing={1}>
                                    {result.trace.map((item, index) => (
                                        <Box key={`${item.step}-${index}`}>
                                            <Typography variant="body2">{item.step} • {item.message}</Typography>
                                            {Object.keys(item.payload).length > 0 && (
                                                <Typography variant="caption" color="text.secondary" component="pre" sx={{ whiteSpace: "pre-wrap" }}>
                                                    {JSON.stringify(item.payload, null, 2)}
                                                </Typography>
                                            )}
                                        </Box>
                                    ))}
                                </Stack>
                            </SectionCard>
                            <SectionCard title="Output" description="Model response from the dry run.">
                                <Typography variant="caption" component="pre" sx={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                                    {result.output_text}
                                </Typography>
                            </SectionCard>
                        </Stack>
                    )}
                </Stack>
            </DialogContent>
            <DialogActions>
                <Button onClick={onClose}>Close</Button>
                <Button
                    variant="contained"
                    startIcon={runMutation.isPending ? <CircularProgress size={14} /> : <TestRunIcon />}
                    disabled={runMutation.isPending}
                    onClick={() => runMutation.mutate()}
                >
                    Run test
                </Button>
            </DialogActions>
        </Dialog>
    );
}

function VersionHistoryDialog({ agent, onClose }: { agent: Agent; onClose: () => void }) {
    const [selected, setSelected] = useState<number | null>(null);
    const [compareTo, setCompareTo] = useState<number | null>(null);
    const { data: versions = [], isLoading } = useQuery({
        queryKey: ["orchestration", "agent", agent.id, "versions"],
        queryFn: () => listAgentVersions(agent.id),
    });

    const sorted = useMemo(() => [...versions].sort((a, b) => b.version_number - a.version_number), [versions]);

    useEffect(() => {
        if (!sorted.length) return;
        setSelected((current) => current ?? sorted[0].version_number);
    }, [sorted]);
    const primary = sorted.find((item) => item.version_number === selected);
    const secondary = sorted.find((item) => item.version_number === compareTo);

    const diffText = useMemo(() => {
        if (!primary || !secondary) return "";
        const a = JSON.stringify(primary.snapshot_json, null, 2);
        const b = JSON.stringify(secondary.snapshot_json, null, 2);
        if (a === b) return "Snapshots are identical for JSON comparison.";
        const la = a.split("\n");
        const lb = b.split("\n");
        const max = Math.max(la.length, lb.length);
        const lines: string[] = [];
        for (let i = 0; i < max; i++) {
            const left = la[i] ?? "";
            const right = lb[i] ?? "";
            if (left === right) {
                lines.push(`  ${left}`);
            } else {
                if (left) lines.push(`- ${left}`);
                if (right) lines.push(`+ ${right}`);
            }
        }
        return lines.join("\n");
    }, [primary, secondary]);

    return (
        <Dialog key={agent.id} open onClose={onClose} maxWidth="md" fullWidth>
            <DialogTitle>Version history — {agent.name}</DialogTitle>
            <DialogContent>
                {isLoading && <CircularProgress size={22} sx={{ mt: 2 }} />}
                {!isLoading && sorted.length === 0 && (
                    <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>No stored versions yet. Versions are recorded when the agent profile changes.</Typography>
                )}
                {!isLoading && sorted.length > 0 && (
                    <Stack spacing={2} sx={{ mt: 1 }}>
                        <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
                            <TextField
                                select
                                label="Snapshot A"
                                size="small"
                                fullWidth
                                value={selected != null ? String(selected) : ""}
                                onChange={(event) => setSelected(event.target.value ? Number(event.target.value) : null)}
                            >
                                {sorted.map((item) => (
                                    <MenuItem key={item.id} value={String(item.version_number)}>
                                        v{item.version_number} — {formatDateTime(item.created_at)}
                                    </MenuItem>
                                ))}
                            </TextField>
                            <TextField
                                select
                                label="Compare to (B)"
                                size="small"
                                fullWidth
                                value={compareTo != null ? String(compareTo) : ""}
                                onChange={(event) => setCompareTo(event.target.value ? Number(event.target.value) : null)}
                            >
                                <MenuItem value="">None</MenuItem>
                                {sorted.map((item) => (
                                    <MenuItem key={`${item.id}-b`} value={String(item.version_number)}>
                                        v{item.version_number}
                                    </MenuItem>
                                ))}
                            </TextField>
                        </Stack>
                        {primary && (
                            <SectionCard title={`Snapshot v${primary.version_number}`} description="Stored JSON profile at this revision.">
                                <Typography variant="caption" component="pre" sx={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                                    {JSON.stringify(primary.snapshot_json, null, 2)}
                                </Typography>
                            </SectionCard>
                        )}
                        {primary && secondary && primary.id !== secondary.id && (
                            <SectionCard title={`Diff (v${secondary.version_number} → v${primary.version_number})`} description="Line-oriented comparison of snapshot_json.">
                                <Typography variant="caption" component="pre" sx={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                                    {diffText}
                                </Typography>
                            </SectionCard>
                        )}
                    </Stack>
                )}
            </DialogContent>
            <DialogActions>
                <Button onClick={onClose}>Close</Button>
            </DialogActions>
        </Dialog>
    );
}

export default function AgentLibraryPage() {
    const location = useLocation();
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();
    const [form, setForm] = useState(EMPTY_FORM);
    const [validationError, setValidationError] = useState<string | null>(null);
    const [testRunAgent_, setTestRunAgent] = useState<Agent | null>(null);
    const [versionAgent, setVersionAgent] = useState<Agent | null>(null);
    const [activeTab, setActiveTab] = useState<"library" | "hierarchy">("library");
    const [assignmentMode, setAssignmentMode] = useState<"parent" | "reviewer">("parent");
    const [selectedHierarchyAgentId, setSelectedHierarchyAgentId] = useState<string | null>(null);
    const [draggedAgentId, setDraggedAgentId] = useState<string | null>(null);
    const [delegationDraft, setDelegationDraft] = useState("");
    const [brainstormDraft, setBrainstormDraft] = useState("");

    const { data: agents = [], isLoading } = useQuery({
        queryKey: ["orchestration", "agents"],
        queryFn: () => listAgents(),
    });
    const { data: templates = [] } = useQuery({
        queryKey: ["orchestration", "agent-templates"],
        queryFn: listAgentTemplates,
    });
    const { data: skills = [] } = useQuery({
        queryKey: ["orchestration", "skill-catalog"],
        queryFn: listSkillCatalog,
    });

    useEffect(() => {
        if (location.pathname === "/agent-hierarchy" || location.pathname === "/hierarchy-builder") {
            setActiveTab("hierarchy");
        }
    }, [location.pathname]);

    const templatePreview = useMemo(() => buildInheritancePreview(form, templates, skills), [form, templates, skills]);

    const createMutation = useMutation({
        mutationFn: createAgent,
        onSuccess: async () => {
            setForm(EMPTY_FORM);
            setValidationError(null);
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "agents"] });
            showToast({ message: "Agent created.", severity: "success" });
        },
    });

    const duplicateMutation = useMutation({
        mutationFn: duplicateAgent,
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "agents"] });
            showToast({ message: "Agent duplicated.", severity: "success" });
        },
    });

    const toggleMutation = useMutation({
        mutationFn: ({ agentId, active }: { agentId: string; active: boolean }) => activateAgent(agentId, active),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "agents"] });
        },
    });
    const updateAgentMutation = useMutation({
        mutationFn: ({ agentId, payload }: { agentId: string; payload: Record<string, unknown> }) => updateAgent(agentId, payload),
        onSuccess: async (_, variables) => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "agents"] });
            showToast({ message: "Agent hierarchy updated.", severity: "success" });
            setSelectedHierarchyAgentId(variables.agentId);
        },
    });

    const templateMutation = useMutation({
        mutationFn: (slug: string) => createAgentFromTemplate(slug, {}),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "agents"] });
            showToast({ message: "Agent created from template.", severity: "success" });
        },
    });

    async function handleMarkdownUpload(file: File) {
        const validation = await validateAgentMarkdown(file);
        if (!validation.valid) {
            setValidationError(validation.errors.join(" "));
            return;
        }
        setValidationError(null);
        await importAgentMarkdown(file);
        await queryClient.invalidateQueries({ queryKey: ["orchestration", "agents"] });
        showToast({ message: "Agent imported from markdown.", severity: "success" });
    }

    function resetFromTemplate(templateSlug: string) {
        const template = getTemplateBySlug(templates, templateSlug);
        if (!template) return;
        setForm((current) => ({
            ...current,
            parent_template_slug: template.slug,
            role: template.role,
            description: template.description,
            system_prompt: template.system_prompt,
            skills: template.skills,
            capabilities: template.capabilities.join(", "),
            allowed_tools: template.allowed_tools.join(", "),
            tags: template.tags.join(", "),
            memory_scope: String((template.memory_policy?.scope as string | undefined) || "project-only"),
            output_format: String((template.output_schema?.format as string | undefined) || "json"),
            model: String((template.model_policy?.model as string | undefined) || ""),
            fallback_model: String((template.model_policy?.fallback_model as string | undefined) || ""),
            escalation_path: String((template.model_policy?.escalation_path as string | undefined) || ""),
            permission: String((template.model_policy?.permissions as string | undefined) || "read-only"),
            token_budget: String((template.budget?.token_budget as number | undefined) || 8000),
            time_budget_seconds: String((template.budget?.time_budget_seconds as number | undefined) || 300),
            retry_budget: String((template.budget?.retry_budget as number | undefined) || 1),
        }));
    }

    const selectedHierarchyAgent = agents.find((agent) => agent.id === selectedHierarchyAgentId) ?? null;
    const delegationRules = (selectedHierarchyAgent?.model_policy?.delegation_rules as Record<string, unknown> | undefined) ?? {};
    const hierarchyColumns = [
        { role: "manager", title: "Managers" },
        { role: "team_lead", title: "Team leads" },
        { role: "specialist", title: "Specialists" },
        { role: "reviewer", title: "Reviewers" },
    ];

    const agentById = useMemo(() => new Map(agents.map((a) => [a.id, a])), [agents]);
    const orgChartRoots = useMemo(
        () => agents.filter((a) => !a.parent_agent_id || !agentById.has(a.parent_agent_id)),
        [agents, agentById],
    );

    function renderOrgChartNode(agent: Agent, depth: number) {
        const children = agents.filter((x) => x.parent_agent_id === agent.id);
        const selected = selectedHierarchyAgentId === agent.id;
        return (
            <Box
                key={agent.id}
                sx={{
                    pl: depth === 0 ? 0 : 2,
                    borderLeft: depth ? "2px solid" : "none",
                    borderColor: "divider",
                    ml: depth ? 1.5 : 0,
                    mt: depth ? 1.25 : 0,
                }}
            >
                <Paper
                    elevation={0}
                    onClick={() => {
                        setSelectedHierarchyAgentId(agent.id);
                        const rules = (agent.model_policy?.delegation_rules as Record<string, unknown> | undefined) ?? {};
                        setDelegationDraft(
                            Array.isArray(rules.allowed_delegate_to)
                                ? (rules.allowed_delegate_to as string[]).join(", ")
                                : "",
                        );
                        setBrainstormDraft(
                            Array.isArray(rules.allowed_brainstorm_with)
                                ? (rules.allowed_brainstorm_with as string[]).join(", ")
                                : "",
                        );
                    }}
                    sx={{
                        p: 1.25,
                        borderRadius: 2,
                        cursor: "pointer",
                        border: "1px solid",
                        borderColor: selected ? "primary.main" : "divider",
                        bgcolor: selected ? "action.selected" : "background.paper",
                    }}
                >
                    <Typography variant="subtitle2">{agent.name}</Typography>
                    <Typography variant="caption" color="text.secondary">{agent.slug} · {agent.role}</Typography>
                </Paper>
                <Box sx={{ mt: 0.5 }}>
                    {children.map((child) => renderOrgChartNode(child, depth + 1))}
                </Box>
            </Box>
        );
    }

    function parseDelegationTargets(value: string) {
        return value
            .split(",")
            .map((item) => item.trim())
            .filter(Boolean);
    }

    function beginDrag(agentId: string) {
        setDraggedAgentId(agentId);
    }

    function endDrag() {
        setDraggedAgentId(null);
    }

    function allowDrop(event: DragEvent) {
        event.preventDefault();
    }

    function handleRoleDrop(role: string) {
        if (!draggedAgentId) return;
        updateAgentMutation.mutate({ agentId: draggedAgentId, payload: { role } });
        setDraggedAgentId(null);
    }

    function handleRelationshipDrop(targetAgentId: string) {
        if (!draggedAgentId || draggedAgentId === targetAgentId) return;
        updateAgentMutation.mutate({
            agentId: draggedAgentId,
            payload: assignmentMode === "parent"
                ? { parent_agent_id: targetAgentId }
                : { reviewer_agent_id: targetAgentId },
        });
        setDraggedAgentId(null);
    }

    function saveHierarchyPolicyRules() {
        if (!selectedHierarchyAgent) return;
        updateAgentMutation.mutate({
            agentId: selectedHierarchyAgent.id,
            payload: {
                model_policy: {
                    ...selectedHierarchyAgent.model_policy,
                    delegation_rules: {
                        ...delegationRules,
                        allowed_delegate_to: parseDelegationTargets(delegationDraft),
                        allowed_brainstorm_with: parseDelegationTargets(brainstormDraft),
                    },
                },
            },
        });
    }


    return (
        <PageShell maxWidth="xl">
            <PageHeader
                eyebrow="Registry"
                title="Agent Library"
                description="Manage templates, inheritance, skill packs, markdown imports, and dry-run execution tests for your orchestration agents."
                meta={<Typography variant="body2" color="text.secondary">{agents.length} agents • {skills.length} skills • {templates.length} templates</Typography>}
            />

            <Paper sx={{ mb: 2, borderRadius: 4, p: 1 }}>
                <Tabs value={activeTab} onChange={(_, value) => setActiveTab(value)} variant="scrollable" scrollButtons="auto">
                    <Tab value="library" label="Library" />
                    <Tab value="hierarchy" label="Hierarchy builder" />
                </Tabs>
            </Paper>

            {activeTab === "library" && templates.length > 0 && (
                <SectionCard title="Quick-start templates" description="Create a seeded template directly or load it into the editor first.">
                    <Box sx={{ display: "grid", gap: 1.5, gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr", lg: "repeat(3, 1fr)" } }}>
                        {templates.map((tpl) => (
                            <Paper key={tpl.slug} sx={{ p: 2, borderRadius: 3, display: "flex", flexDirection: "column", gap: 1 }}>
                                <Typography variant="subtitle2">{tpl.name}</Typography>
                                <Typography variant="body2" color="text.secondary" sx={{ flex: 1 }}>{tpl.description}</Typography>
                                <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                                    <Chip label={tpl.role} size="small" variant="outlined" />
                                    {tpl.skills.slice(0, 3).map((s) => <Chip key={s} label={s} size="small" color="secondary" variant="outlined" />)}
                                </Stack>
                                <Stack direction="row" spacing={1}>
                                    <Button size="small" variant="outlined" onClick={() => resetFromTemplate(tpl.slug)}>Load into editor</Button>
                                    <Button size="small" variant="contained" disabled={templateMutation.isPending} onClick={() => templateMutation.mutate(tpl.slug)}>Create</Button>
                                </Stack>
                            </Paper>
                        ))}
                    </Box>
                </SectionCard>
            )}

            {activeTab === "library" && (
            <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", xl: "440px minmax(0, 1fr)" }, alignItems: "start" }}>
                <Stack spacing={2}>
                    <SectionCard title="Agent editor" description="Compose an agent from a parent template and reusable skills.">
                        <Stack spacing={2}>
                            <TextField label="Name" value={form.name} onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} />
                            <TextField label="Slug" value={form.slug} onChange={(event) => setForm((current) => ({ ...current, slug: event.target.value }))} />
                            <TextField select label="Role" value={form.role} onChange={(event) => setForm((current) => ({ ...current, role: event.target.value }))}>
                                <MenuItem value="manager">Manager</MenuItem>
                                <MenuItem value="specialist">Specialist</MenuItem>
                                <MenuItem value="reviewer">Reviewer</MenuItem>
                            </TextField>
                            <TextField select label="Parent template" value={form.parent_template_slug} onChange={(event) => setForm((current) => ({ ...current, parent_template_slug: event.target.value }))}>
                                <MenuItem value="">None</MenuItem>
                                {templates.map((template) => <MenuItem key={template.slug} value={template.slug}>{template.name}</MenuItem>)}
                            </TextField>
                            <TextField
                                select
                                SelectProps={{ multiple: true }}
                                label="Skill packs"
                                value={form.skills}
                                onChange={(event) => setForm((current) => ({ ...current, skills: typeof event.target.value === "string" ? [event.target.value] : event.target.value }))}
                                helperText="Agents keep identity fields, while skill packs contribute reusable capabilities, tools, rules, and tags."
                            >
                                {skills.map((skill) => (
                                    <MenuItem key={skill.slug} value={skill.slug}>{skill.name}</MenuItem>
                                ))}
                            </TextField>
                            <TextField label="Description" multiline minRows={3} value={form.description} onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))} />
                            <TextField label="System prompt override" multiline minRows={4} value={form.system_prompt} onChange={(event) => setForm((current) => ({ ...current, system_prompt: event.target.value }))} />
                            <TextField label="Capabilities override" helperText="Comma-separated" value={form.capabilities} onChange={(event) => setForm((current) => ({ ...current, capabilities: event.target.value }))} />
                            <TextField label="Allowed tools override" helperText="Comma-separated" value={form.allowed_tools} onChange={(event) => setForm((current) => ({ ...current, allowed_tools: event.target.value }))} />
                            <TextField label="Tags" helperText="Comma-separated" value={form.tags} onChange={(event) => setForm((current) => ({ ...current, tags: event.target.value }))} />
                            <TextField label="Task filters" helperText="Comma-separated tags or regex patterns" value={form.task_filters} onChange={(event) => setForm((current) => ({ ...current, task_filters: event.target.value }))} />
                            <Divider />
                            <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                                <TextField label="Primary model" value={form.model} onChange={(event) => setForm((current) => ({ ...current, model: event.target.value }))} fullWidth />
                                <TextField label="Fallback model" value={form.fallback_model} onChange={(event) => setForm((current) => ({ ...current, fallback_model: event.target.value }))} fullWidth />
                            </Stack>
                            <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                                <TextField label="Escalation path" helperText="Agent slug to escalate to" value={form.escalation_path} onChange={(event) => setForm((current) => ({ ...current, escalation_path: event.target.value }))} fullWidth />
                                <TextField select label="Permission" value={form.permission} onChange={(event) => setForm((current) => ({ ...current, permission: event.target.value }))} fullWidth>
                                    {PERMISSION_OPTIONS.map((item) => <MenuItem key={item} value={item}>{item}</MenuItem>)}
                                </TextField>
                            </Stack>
                            <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                                <TextField select label="Memory policy" value={form.memory_scope} onChange={(event) => setForm((current) => ({ ...current, memory_scope: event.target.value }))} fullWidth>
                                    {MEMORY_SCOPE_OPTIONS.map((item) => <MenuItem key={item} value={item}>{item}</MenuItem>)}
                                </TextField>
                                <TextField select label="Output schema" value={form.output_format} onChange={(event) => setForm((current) => ({ ...current, output_format: event.target.value }))} fullWidth>
                                    {OUTPUT_FORMAT_OPTIONS.map((item) => <MenuItem key={item} value={item}>{item}</MenuItem>)}
                                </TextField>
                            </Stack>
                            <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                                <TextField label="Token budget" value={form.token_budget} onChange={(event) => setForm((current) => ({ ...current, token_budget: event.target.value }))} fullWidth />
                                <TextField label="Time budget (s)" value={form.time_budget_seconds} onChange={(event) => setForm((current) => ({ ...current, time_budget_seconds: event.target.value }))} fullWidth />
                                <TextField label="Retry budget" value={form.retry_budget} onChange={(event) => setForm((current) => ({ ...current, retry_budget: event.target.value }))} fullWidth />
                            </Stack>
                            {createMutation.isError && <Alert severity="error">{createMutation.error instanceof Error ? createMutation.error.message : "Failed to add agent."}</Alert>}
                            {validationError && <Alert severity="error">{validationError}</Alert>}
                            <Button
                                variant="contained"
                                onClick={() =>
                                    createMutation.mutate({
                                        name: form.name,
                                        slug: form.slug,
                                        description: form.description,
                                        role: form.role,
                                        system_prompt: form.system_prompt,
                                        parent_template_slug: form.parent_template_slug || undefined,
                                        skills: form.skills,
                                        capabilities: parseCsv(form.capabilities),
                                        allowed_tools: parseCsv(form.allowed_tools),
                                        tags: parseCsv(form.tags),
                                        task_filters: parseCsv(form.task_filters),
                                        model_policy: {
                                            model: form.model || null,
                                            fallback_model: form.fallback_model || null,
                                            escalation_path: form.escalation_path || null,
                                            permissions: form.permission,
                                        },
                                        budget: {
                                            token_budget: Number(form.token_budget || 0),
                                            time_budget_seconds: Number(form.time_budget_seconds || 0),
                                            retry_budget: Number(form.retry_budget || 0),
                                        },
                                        memory_policy: { scope: form.memory_scope },
                                        output_schema: { format: form.output_format },
                                    })
                                }
                            >
                                Save agent
                            </Button>
                            <Button variant="outlined" component="label" startIcon={<UploadIcon />}>
                                Import markdown
                                <input hidden type="file" accept=".md,text/markdown" onChange={(event) => {
                                    const file = event.target.files?.[0];
                                    if (file) void handleMarkdownUpload(file);
                                }} />
                            </Button>
                        </Stack>
                    </SectionCard>

                    <SectionCard title="Skill catalog" description="Skill packs are reusable capabilities that can be combined with different agent identities.">
                        <Stack spacing={1}>
                            {skills.map((skill) => (
                                <Paper key={skill.slug} sx={{ p: 1.5, borderRadius: 3 }}>
                                    <Typography variant="subtitle2">{skill.name}</Typography>
                                    <Typography variant="body2" color="text.secondary">{skill.description}</Typography>
                                    <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap sx={{ mt: 1 }}>
                                        {skill.capabilities.map((item) => <Chip key={item} label={item} size="small" variant="outlined" />)}
                                        {skill.tags.map((item) => <Chip key={item} label={item} size="small" color="secondary" variant="outlined" />)}
                                    </Stack>
                                </Paper>
                            ))}
                        </Stack>
                    </SectionCard>
                </Stack>

                <Stack spacing={2}>
                    <SectionCard title="Inheritance preview" description="See what comes from the parent template and what this editor is overriding.">
                        {templatePreview ? (
                            <Stack spacing={2}>
                                <Stack direction="row" spacing={1} alignItems="center">
                                    <InheritanceIcon fontSize="small" />
                                    <Typography variant="subtitle2">Parent template: {templatePreview.parent_template_slug}</Typography>
                                </Stack>
                                <Box>
                                    <Typography variant="overline" color="text.secondary">Inherited</Typography>
                                    <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                                        {templatePreview.effective.capabilities.map((item) => <Chip key={`cap-${item}`} label={item} size="small" variant="outlined" />)}
                                    </Stack>
                                </Box>
                                <Box>
                                    <Typography variant="overline" color="text.secondary">Overridden</Typography>
                                    {Object.keys(templatePreview.overridden_fields).length > 0 ? (
                                        <Typography variant="caption" component="pre" sx={{ whiteSpace: "pre-wrap" }}>
                                            {JSON.stringify(templatePreview.overridden_fields, null, 2)}
                                        </Typography>
                                    ) : (
                                        <Typography variant="body2" color="text.secondary">No overrides yet.</Typography>
                                    )}
                                </Box>
                            </Stack>
                        ) : (
                            <Typography color="text.secondary">Select a parent template to preview inherited values.</Typography>
                        )}
                    </SectionCard>

                    <SectionCard title="Agents" description="Managers, specialists, and reviewers with inheritance, skill packs, budgets, and dry-run support.">
                        {isLoading ? (
                            <Typography color="text.secondary">Loading agents...</Typography>
                        ) : agents.length === 0 ? (
                            <EmptyState icon={<AgentIcon />} title="No agents yet" description="Start with a built-in template or compose a custom agent from skills." />
                        ) : (
                            <Stack spacing={1.5}>
                                {agents.map((agent) => (
                                    <Paper key={agent.id} sx={{ p: 2, borderRadius: 4 }}>
                                        <Stack spacing={1.25}>
                                            <Stack direction={{ xs: "column", md: "row" }} justifyContent="space-between" spacing={1}>
                                                <Box>
                                                    <Typography variant="subtitle1">{agent.name}</Typography>
                                                    <Typography variant="body2" color="text.secondary">
                                                        {agent.role} • {agent.slug} {agent.parent_template_slug ? `• template ${agent.parent_template_slug}` : ""}
                                                    </Typography>
                                                </Box>
                                                <Stack direction="row" spacing={1} alignItems="center">
                                                    <Typography variant="caption" color="text.secondary">Active</Typography>
                                                    <Switch checked={agent.is_active} onChange={(_, checked) => toggleMutation.mutate({ agentId: agent.id, active: checked })} />
                                                    <Button size="small" variant="text" startIcon={<DuplicateIcon />} onClick={() => duplicateMutation.mutate(agent.id)}>Duplicate</Button>
                                                    <Button size="small" variant="outlined" onClick={() => setVersionAgent(agent)}>Versions</Button>
                                                    <Button size="small" variant="contained" startIcon={<TestRunIcon />} onClick={() => setTestRunAgent(agent)}>Test run</Button>
                                                </Stack>
                                            </Stack>
                                            <Typography variant="body2" color="text.secondary">{agent.description || "No description provided."}</Typography>
                                            <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                                                {agent.skills.map((item) => (
                                                    <Chip
                                                        key={`skill-${item}`}
                                                        label={skillDisplayName(item, skills)}
                                                        size="small"
                                                        color="info"
                                                        variant="outlined"
                                                    />
                                                ))}
                                                {(agent.inheritance?.effective.capabilities || agent.capabilities).map((item) => <Chip key={`cap-${agent.id}-${item}`} label={item} size="small" variant="outlined" />)}
                                                {agent.tags.map((item) => <Chip key={`tag-${agent.id}-${item}`} label={item} size="small" color="secondary" variant="outlined" />)}
                                            </Stack>
                                            {agent.inheritance && (
                                                <Typography variant="caption" color="text.secondary">
                                                    Inherited: {Object.keys(agent.inheritance.inherited_fields).length} fields • overrides: {Object.keys(agent.inheritance.overridden_fields).length}
                                                </Typography>
                                            )}
                                            <Typography variant="caption" color="text.secondary">
                                                Updated {formatDateTime(agent.updated_at)} • version {agent.version}
                                            </Typography>
                                        </Stack>
                                    </Paper>
                                ))}
                            </Stack>
                        )}
                    </SectionCard>
                </Stack>
            </Box>
            )}

            {activeTab === "hierarchy" && (
                <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", xl: "minmax(0, 1.6fr) 360px" }, alignItems: "start" }}>
                    <Stack spacing={2}>
                    <SectionCard
                        title="Org chart"
                        description="Reporting lines from parent_agent_id. Click a node to edit delegation and brainstorm collaboration rules. Use the role columns below to drag-drop role and manager assignments."
                    >
                        {agents.length === 0 ? (
                            <Typography color="text.secondary">No agents to display.</Typography>
                        ) : (
                            <Stack spacing={1}>
                                {orgChartRoots.map((root) => renderOrgChartNode(root, 0))}
                            </Stack>
                        )}
                    </SectionCard>
                    <SectionCard
                        title="Hierarchy builder"
                        description="Drag agents into roles, then drag one agent card onto another to assign a parent or reviewer relationship."
                    >
                        <Stack spacing={2}>
                            <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                                <TextField
                                    select
                                    label="Drag assignment mode"
                                    value={assignmentMode}
                                    onChange={(event) => setAssignmentMode(event.target.value as "parent" | "reviewer")}
                                    fullWidth
                                >
                                    <MenuItem value="parent">Parent assignment</MenuItem>
                                    <MenuItem value="reviewer">Reviewer assignment</MenuItem>
                                </TextField>
                                <Alert severity="info" sx={{ flex: 1 }}>
                                    Drag to a column to change role. Drag onto another card to set the {assignmentMode === "parent" ? "manager" : "reviewer"} chain.
                                </Alert>
                            </Stack>
                            <Box sx={{ display: "grid", gap: 1.5, gridTemplateColumns: { xs: "1fr", md: "repeat(2, 1fr)", xl: "repeat(4, 1fr)" } }}>
                                {hierarchyColumns.map((column) => (
                                    <Paper
                                        key={column.role}
                                        onDragOver={allowDrop}
                                        onDrop={() => handleRoleDrop(column.role)}
                                        sx={{ p: 1.5, borderRadius: 3, minHeight: 320, border: "1px dashed", borderColor: "divider" }}
                                    >
                                        <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1.5 }}>
                                            <Typography variant="subtitle2">{column.title}</Typography>
                                            <Chip label={agents.filter((agent) => agent.role === column.role).length} size="small" variant="outlined" />
                                        </Stack>
                                        <Stack spacing={1}>
                                            {agents.filter((agent) => agent.role === column.role).map((agent) => {
                                                const parentAgent = agents.find((item) => item.id === agent.parent_agent_id);
                                                const reviewerAgent = agents.find((item) => item.id === agent.reviewer_agent_id);
                                                return (
                                                    <Paper
                                                        key={agent.id}
                                                        draggable
                                                        onDragStart={() => beginDrag(agent.id)}
                                                        onDragEnd={endDrag}
                                                        onDragOver={allowDrop}
                                                        onDrop={() => handleRelationshipDrop(agent.id)}
                                                        onClick={() => {
                                                            setSelectedHierarchyAgentId(agent.id);
                                                            const rules = (agent.model_policy?.delegation_rules as Record<string, unknown> | undefined) ?? {};
                                                            setDelegationDraft(
                                                                Array.isArray(rules.allowed_delegate_to)
                                                                    ? (rules.allowed_delegate_to as string[]).join(", ")
                                                                    : "",
                                                            );
                                                            setBrainstormDraft(
                                                                Array.isArray(rules.allowed_brainstorm_with)
                                                                    ? (rules.allowed_brainstorm_with as string[]).join(", ")
                                                                    : "",
                                                            );
                                                        }}
                                                        sx={{
                                                            p: 1.5,
                                                            borderRadius: 3,
                                                            cursor: "grab",
                                                            border: selectedHierarchyAgentId === agent.id ? "1px solid" : "1px solid",
                                                            borderColor: selectedHierarchyAgentId === agent.id ? "primary.main" : "divider",
                                                            opacity: draggedAgentId === agent.id ? 0.55 : 1,
                                                        }}
                                                    >
                                                        <Typography variant="subtitle2">{agent.name}</Typography>
                                                        <Typography variant="caption" color="text.secondary">{agent.slug}</Typography>
                                                        <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap sx={{ mt: 1 }}>
                                                            {agent.capabilities.slice(0, 3).map((capability) => (
                                                                <Chip key={`${agent.id}-${capability}`} label={capability} size="small" variant="outlined" />
                                                            ))}
                                                        </Stack>
                                                        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
                                                            Reports to: {parentAgent?.name || "none"}
                                                        </Typography>
                                                        <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
                                                            Reviewer: {reviewerAgent?.name || "none"}
                                                        </Typography>
                                                    </Paper>
                                                );
                                            })}
                                        </Stack>
                                    </Paper>
                                ))}
                            </Box>
                        </Stack>
                    </SectionCard>
                    </Stack>

                    <Stack spacing={2}>
                        <SectionCard
                            title="Delegation and brainstorm rules"
                            description="Delegation is enforced for manager/worker runs. Brainstorm pairing is enforced when participants are added to a brainstorm. Use agent slugs or ids."
                        >
                            {selectedHierarchyAgent ? (
                                <Stack spacing={2}>
                                    <Typography variant="subtitle2">{selectedHierarchyAgent.name}</Typography>
                                    <TextField
                                        label="Allowed delegate targets"
                                        helperText="Empty = any direct report in the hierarchy. When set, manager/worker delegation only targets this allowlist (plus hierarchy)."
                                        value={delegationDraft}
                                        onChange={(event) => setDelegationDraft(event.target.value)}
                                        multiline
                                        minRows={3}
                                    />
                                    <TextField
                                        label="Allowed brainstorm partners"
                                        helperText="Empty = no extra restriction. When set, both agents must list each other to be in the same brainstorm."
                                        value={brainstormDraft}
                                        onChange={(event) => setBrainstormDraft(event.target.value)}
                                        multiline
                                        minRows={3}
                                    />
                                    <Button variant="contained" onClick={saveHierarchyPolicyRules} disabled={updateAgentMutation.isPending}>
                                        Save hierarchy rules
                                    </Button>
                                </Stack>
                            ) : (
                                <Typography color="text.secondary">Select an agent from the org chart or a card in the columns.</Typography>
                            )}
                        </SectionCard>

                        <SectionCard title="Relationship legend" description="Quick reference for the hierarchy controls.">
                            <Stack spacing={1}>
                                <Typography variant="body2">Manager: top-level routing and escalation.</Typography>
                                <Typography variant="body2">Team lead: intermediate coordinator for specialists.</Typography>
                                <Typography variant="body2">Specialist: execution-focused worker agent.</Typography>
                                <Typography variant="body2">Reviewer: validates outputs and can reopen work.</Typography>
                            </Stack>
                        </SectionCard>
                    </Stack>
                </Box>
            )}

            {testRunAgent_ && <TestRunDialog agent={testRunAgent_} onClose={() => setTestRunAgent(null)} />}
            {versionAgent && <VersionHistoryDialog agent={versionAgent} onClose={() => setVersionAgent(null)} />}
        </PageShell>
    );
}
