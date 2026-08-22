import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Add as AddIcon } from "@mui/icons-material";
import { Alert, Button, MenuItem, Stack, TextField } from "@mui/material";
import { Link as RouterLink } from "react-router-dom";

import {
    activateAgent,
    createAgent,
    createAgentFromTemplate,
    duplicateAgent,
    listAgentTemplates,
    listAgentVersions,
    listAgents,
    listOrchestrationProjects,
    listTools,
    testRunAgent,
    updateAgent,
    validateAgentContract,
    type AgentTemplate,
} from "../../../api/orchestration";
import { DensePageMobileNotice } from "../../../components/ui/DensePageMobileNotice";
import { FilterToolbar } from "../../../components/ui/FilterToolbar";
import { InspectorSplit } from "../../../components/ui/InspectorSplit";
import { PageHeader } from "../../../components/ui/PageHeader";
import { PageShell } from "../../../components/ui/PageShell";
import { QueryState } from "../../../components/ui/QueryState";
import { queryKeys } from "../../../config/queryKeys";
import { extractApiErrorMessage } from "../../../utils/apiErrors";
import {
    agentContractPayload,
    agentProfileForm,
    commaSeparatedList,
    defaultAgentMarkdown,
} from "./agentFormUtils";
import { AgentEditorPanel } from "./AgentEditorPanel";
import { AgentRegistryPanel } from "./AgentRegistryPanel";
import type { AgentEditorTab, AgentProfileForm, AgentValidationState } from "./types";

export function AgentProfilesContent() {
    const client = useQueryClient();
    const [projectId, setProjectId] = useState("");
    const [agentSearch, setAgentSearch] = useState("");
    const [selectedId, setSelectedId] = useState<string | null>(null);
    const [form, setForm] = useState<AgentProfileForm>(agentProfileForm(null));
    const [markdown, setMarkdown] = useState(defaultAgentMarkdown());
    const [activeTab, setActiveTab] = useState<AgentEditorTab>("profile");
    const [message, setMessage] = useState("");
    const [error, setError] = useState("");
    const [validation, setValidation] = useState<AgentValidationState | null>(null);
    const [dryRun, setDryRun] = useState("");

    const { data: projects = [] } = useQuery({
        queryKey: queryKeys.orchestration.projects,
        queryFn: listOrchestrationProjects,
    });
    const {
        data: agents = [],
        isLoading: agentsLoading,
        error: agentsError,
    } = useQuery({
        queryKey: queryKeys.orchestration.agents(projectId || undefined),
        queryFn: () => listAgents(projectId || undefined),
    });
    const { data: tools = [] } = useQuery({
        queryKey: queryKeys.orchestration.tools,
        queryFn: listTools,
    });
    const { data: templates = [] } = useQuery({
        queryKey: queryKeys.orchestration.agentTemplates,
        queryFn: listAgentTemplates,
    });

    const filteredAgents = useMemo(() => {
        const query = agentSearch.trim().toLowerCase();
        if (!query) return agents;
        return agents.filter((item) =>
            [item.name, item.role, item.slug].some((value) => String(value ?? "").toLowerCase().includes(query)),
        );
    }, [agents, agentSearch]);

    const agent = useMemo(
        () =>
            filteredAgents.find((item) => item.id === selectedId) ??
            agents.find((item) => item.id === selectedId) ??
            filteredAgents[0] ??
            agents[0] ??
            null,
        [agents, filteredAgents, selectedId],
    );

    const { data: versions = [] } = useQuery({
        queryKey: queryKeys.orchestration.agentVersions(agent?.id ?? ""),
        queryFn: () => listAgentVersions(agent!.id),
        enabled: Boolean(agent?.id),
    });

    // The selected server profile is the source of truth when switching registry entries.
    useEffect(() => {
        if (agent) {
            // eslint-disable-next-line react-hooks/set-state-in-effect -- reset the draft when registry selection changes
            setForm(agentProfileForm(agent));
            setMarkdown(agent.source_markdown || defaultAgentMarkdown());
        }
    }, [agent]);

    const setFormField = <K extends keyof AgentProfileForm>(key: K, value: AgentProfileForm[K]) =>
        setForm((current) => ({ ...current, [key]: value }));

    const fail = (reason: unknown, fallback: string) => setError(extractApiErrorMessage(reason, fallback));

    const startNewDraft = () => {
        setSelectedId(null);
        setForm(agentProfileForm(null));
        setMarkdown(defaultAgentMarkdown());
    };

    const save = useMutation({
        mutationFn: () => {
            const payload = agentContractPayload(form, projectId, markdown);
            return agent
                ? updateAgent(agent.id, payload)
                : createAgent({
                      ...payload,
                      system_prompt: markdown,
                      mission_markdown: markdown,
                      is_active: false,
                  });
        },
        onSuccess: (saved) => {
            setSelectedId(saved.id);
            setMessage(`Saved ${saved.name} as version ${saved.version}.`);
            void client.invalidateQueries({ queryKey: queryKeys.orchestration.agents() });
            void client.invalidateQueries({ queryKey: queryKeys.orchestration.agentVersions(saved.id) });
        },
        onError: (reason) => fail(reason, "Agent save failed."),
    });

    const validate = useMutation({
        mutationFn: () => validateAgentContract(agentContractPayload(form, projectId, markdown)),
        onSuccess: (result) => {
            setValidation({ errors: result.errors, warnings: result.warnings, ready: result.activation_ready });
            setMessage(
                result.activation_ready
                    ? "Contract is activation-ready."
                    : "Contract needs attention before activation.",
            );
        },
        onError: (reason) => fail(reason, "Validation failed."),
    });

    const template = useMutation({
        mutationFn: (item: AgentTemplate) =>
            createAgentFromTemplate(item.slug, {
                project_id: projectId || null,
                name: `${item.name} ${agents.length + 1}`,
                slug: `${item.slug}-${Date.now()}`,
            }),
        onSuccess: (created) => {
            setSelectedId(created.id);
            setMessage(`Created ${created.name} from template.`);
            void client.invalidateQueries({ queryKey: queryKeys.orchestration.agents() });
        },
        onError: (reason) => fail(reason, "Template creation failed."),
    });

    const action = useMutation({
        mutationFn: (kind: "activate" | "deactivate" | "duplicate") =>
            !agent
                ? Promise.reject(new Error("Select an agent first."))
                : kind === "duplicate"
                  ? duplicateAgent(agent.id)
                  : activateAgent(agent.id, kind === "activate"),
        onSuccess: (result, kind) => {
            setSelectedId(result.id);
            setMessage(
                kind === "duplicate"
                    ? `Duplicated as ${result.name}.`
                    : `${result.name} is now ${result.is_active ? "active" : "inactive"}.`,
            );
            void client.invalidateQueries({ queryKey: queryKeys.orchestration.agents() });
        },
        onError: (reason) => fail(reason, "Agent action failed."),
    });

    const run = useMutation({
        mutationFn: () =>
            !agent
                ? Promise.reject(new Error("Save an agent before running a dry run."))
                : testRunAgent(agent.id, {
                      task_title: "Registry contract dry run",
                      task_description: form.description || "Verify the agent contract.",
                      task_labels: commaSeparatedList(form.task_filters),
                  }),
        onSuccess: (result) => {
            setDryRun(result.output_text);
            setMessage(`Dry run completed in ${result.latency_ms}ms.`);
        },
        onError: (reason) => fail(reason, "Dry run failed."),
    });

    return (
        <PageShell maxWidth="xl">
            <PageHeader
                title="Agents"
                description="Versioned worker contracts. Install packs from Marketplace, attach Skills, or compose teams in Hierarchy."
                actions={
                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                        <Button component={RouterLink} to="/marketplace" size="small" variant="outlined">
                            Marketplace
                        </Button>
                        <Button component={RouterLink} to="/skills" size="small" variant="outlined">
                            Skills
                        </Button>
                        <Button component={RouterLink} to="/hierarchy" size="small" variant="outlined">
                            Hierarchy
                        </Button>
                        <Button variant="outlined" startIcon={<AddIcon />} onClick={startNewDraft}>
                            New draft
                        </Button>
                    </Stack>
                }
            />
            <DensePageMobileNotice surface="Agents catalog" />

            <FilterToolbar>
                <TextField
                    label="Search"
                    size="small"
                    value={agentSearch}
                    onChange={(event) => setAgentSearch(event.target.value)}
                    placeholder="Name, role, or slug"
                    sx={{ minWidth: { sm: 220 }, flex: 1 }}
                />
                <TextField
                    select
                    label="Project scope"
                    size="small"
                    value={projectId}
                    onChange={(event) => {
                        setProjectId(event.target.value);
                        setSelectedId(null);
                    }}
                    sx={{ minWidth: 200 }}
                >
                    <MenuItem value="">Global agents</MenuItem>
                    {projects.map((item) => (
                        <MenuItem key={item.id} value={item.id}>
                            {item.name}
                        </MenuItem>
                    ))}
                </TextField>
            </FilterToolbar>

            {error && (
                <Alert severity="error" onClose={() => setError("")}>
                    {error}
                </Alert>
            )}
            {message && (
                <Alert severity="info" onClose={() => setMessage("")}>
                    {message}
                </Alert>
            )}

            <QueryState
                loading={agentsLoading}
                error={agentsError}
                onRetry={() => {
                    void client.invalidateQueries({ queryKey: queryKeys.orchestration.agents(projectId || undefined) });
                }}
            >
                <InspectorSplit
                    variant="list-detail"
                    secondaryWidth={320}
                    hideSecondaryOnMobile={false}
                    primary={
                        <AgentRegistryPanel
                            agents={agents}
                            filteredAgents={filteredAgents}
                            templates={templates}
                            selectedAgentId={agent?.id ?? selectedId}
                            isCreatingFromTemplate={template.isPending}
                            onSelectAgent={setSelectedId}
                            onNewDraft={startNewDraft}
                            onCreateFromTemplate={(item) => template.mutate(item)}
                        />
                    }
                    secondary={
                        <AgentEditorPanel
                            agent={agent}
                            form={form}
                            markdown={markdown}
                            tools={tools}
                            versions={versions}
                            activeTab={activeTab}
                            validation={validation}
                            dryRun={dryRun}
                            isSaving={save.isPending}
                            isValidating={validate.isPending}
                            isRunningDryRun={run.isPending}
                            isDuplicating={action.isPending && action.variables === "duplicate"}
                            isTogglingActive={
                                action.isPending &&
                                (action.variables === "activate" || action.variables === "deactivate")
                            }
                            onTabChange={setActiveTab}
                            onFormChange={setFormField}
                            onMarkdownChange={setMarkdown}
                            onDuplicate={() => action.mutate("duplicate")}
                            onToggleActive={() => action.mutate(agent?.is_active ? "deactivate" : "activate")}
                            onDryRun={() => run.mutate()}
                            onValidate={() => validate.mutate()}
                            onSave={() => save.mutate()}
                        />
                    }
                />
            </QueryState>
        </PageShell>
    );
}
