import { Alert, Divider, MenuItem, Stack, TextField } from "@mui/material";

import type { AgentTemplate, SkillPack } from "../../api/orchestration";
import { SkillPackPicker } from "./SkillPackPicker";
import { TemplateSection } from "./TemplateSection";
import { TemplateValidationPanel } from "./TemplateValidationPanel";
import type { TemplateBuilderFormState } from "./types";
import { AgentRegistryPanel } from "./AgentRegistryPanel";

type TemplateBuilderViewProps = {
    form: TemplateBuilderFormState;
    setForm: React.Dispatch<React.SetStateAction<TemplateBuilderFormState>>;
    templates: AgentTemplate[];
    skills: SkillPack[];
    templatePreview: import("../../api/orchestration").AgentInheritancePreview | null;
    validationError: string | null;
    validationWarnings: string[];
    memoryScopeOptions: readonly string[];
    outputFormatOptions: readonly string[];
    permissionOptions: readonly string[];
    onCreateAgent: () => void;
    onImportMarkdown: (file: File) => Promise<void> | void;
    createAgentError: string | null;
    isCreatingAgent: boolean;
    agents: import("../../api/orchestration").Agent[];
    isLoadingAgents: boolean;
    agentLiveStatus: Map<string, "running" | "blocked" | "queued" | "idle">;
    simulationAgentId: string | null;
    isSimulatingAgent: boolean;
    getSkillDisplayName: (slug: string) => string;
    onDuplicateAgent: (agentId: string) => void;
    onToggleAgent: (payload: { agentId: string; active: boolean }) => void;
    onOpenVersions: (agent: import("../../api/orchestration").Agent) => void;
    onOpenTestRun: (agent: import("../../api/orchestration").Agent) => void;
    onSimulateAgent: (agentId: string) => void;
    showRegistryPanel?: boolean;
};

const ROLE_OPTIONS = ["manager", "specialist", "reviewer"] as const;

export function TemplateBuilderView({
    form,
    setForm,
    templates,
    skills,
    templatePreview,
    validationError,
    validationWarnings,
    memoryScopeOptions,
    outputFormatOptions,
    permissionOptions,
    onCreateAgent,
    onImportMarkdown,
    createAgentError,
    isCreatingAgent,
    agents,
    isLoadingAgents,
    agentLiveStatus,
    simulationAgentId,
    isSimulatingAgent,
    getSkillDisplayName,
    onDuplicateAgent,
    onToggleAgent,
    onOpenVersions,
    onOpenTestRun,
    onSimulateAgent,
    showRegistryPanel = true,
}: TemplateBuilderViewProps) {
    return (
        <Stack spacing={2}>
            <Stack
                direction={showRegistryPanel ? { xs: "column", xl: "row" } : "column"}
                spacing={2}
                alignItems="flex-start"
            >
                <Stack spacing={2} sx={{ flex: 1, minWidth: 0 }}>
                    <TemplateSection title="Base template" description="Choose parent template for inherited rules and runtime defaults.">
                        <TextField
                            select
                            label="Parent template"
                            value={form.parent_template_slug}
                            onChange={(event) =>
                                setForm((current) => ({ ...current, parent_template_slug: event.target.value }))
                            }
                            fullWidth
                        >
                            <MenuItem value="">None</MenuItem>
                            {templates.map((template) => (
                                <MenuItem key={template.slug} value={template.slug}>
                                    {template.name}
                                </MenuItem>
                            ))}
                        </TextField>
                    </TemplateSection>

                    <TemplateSection title="Identity" description="Core agent identity fields.">
                        <Stack spacing={2}>
                            <TextField label="Name" value={form.name} onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} />
                            <TextField label="Slug" value={form.slug} onChange={(event) => setForm((current) => ({ ...current, slug: event.target.value }))} />
                            <TextField select label="Role" value={form.role} onChange={(event) => setForm((current) => ({ ...current, role: event.target.value }))}>
                                {ROLE_OPTIONS.map((role) => (
                                    <MenuItem key={role} value={role}>
                                        {role}
                                    </MenuItem>
                                ))}
                            </TextField>
                            <TextField label="Description" multiline minRows={3} value={form.description} onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))} />
                        </Stack>
                    </TemplateSection>

                    <TemplateSection title="Skills" description="Skill packs, capabilities, tags, task filters.">
                        <Stack spacing={2}>
                            <SkillPackPicker form={form} setForm={setForm} skills={skills} />
                            <TextField label="Capabilities" helperText="Comma-separated" value={form.capabilities} onChange={(event) => setForm((current) => ({ ...current, capabilities: event.target.value }))} />
                            <TextField label="Tags" helperText="Comma-separated" value={form.tags} onChange={(event) => setForm((current) => ({ ...current, tags: event.target.value }))} />
                            <TextField label="Task filters" helperText="Comma-separated tags or regex patterns" value={form.task_filters} onChange={(event) => setForm((current) => ({ ...current, task_filters: event.target.value }))} />
                        </Stack>
                    </TemplateSection>

                    <TemplateSection title="Tools + runtime" description="Tool access, models, budgets, memory, permissions.">
                        <Stack spacing={2}>
                            <TextField label="Allowed tools" helperText="Comma-separated" value={form.allowed_tools} onChange={(event) => setForm((current) => ({ ...current, allowed_tools: event.target.value }))} />
                            <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                                <TextField fullWidth label="Primary model" value={form.model} onChange={(event) => setForm((current) => ({ ...current, model: event.target.value }))} />
                                <TextField fullWidth label="Fallback model" value={form.fallback_model} onChange={(event) => setForm((current) => ({ ...current, fallback_model: event.target.value }))} />
                            </Stack>
                            <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                                <TextField fullWidth label="Escalation path" value={form.escalation_path} onChange={(event) => setForm((current) => ({ ...current, escalation_path: event.target.value }))} />
                                <TextField select fullWidth label="Permission" value={form.permission} onChange={(event) => setForm((current) => ({ ...current, permission: event.target.value }))}>
                                    {permissionOptions.map((item) => (
                                        <MenuItem key={item} value={item}>
                                            {item}
                                        </MenuItem>
                                    ))}
                                </TextField>
                            </Stack>
                            <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                                <TextField select fullWidth label="Memory scope" value={form.memory_scope} onChange={(event) => setForm((current) => ({ ...current, memory_scope: event.target.value }))}>
                                    {memoryScopeOptions.map((item) => (
                                        <MenuItem key={item} value={item}>
                                            {item}
                                        </MenuItem>
                                    ))}
                                </TextField>
                                <TextField select fullWidth label="Output format" value={form.output_format} onChange={(event) => setForm((current) => ({ ...current, output_format: event.target.value }))}>
                                    {outputFormatOptions.map((item) => (
                                        <MenuItem key={item} value={item}>
                                            {item}
                                        </MenuItem>
                                    ))}
                                </TextField>
                            </Stack>
                            <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                                <TextField fullWidth label="Token budget" value={form.token_budget} onChange={(event) => setForm((current) => ({ ...current, token_budget: event.target.value }))} />
                                <TextField fullWidth label="Time budget (s)" value={form.time_budget_seconds} onChange={(event) => setForm((current) => ({ ...current, time_budget_seconds: event.target.value }))} />
                                <TextField fullWidth label="Retry budget" value={form.retry_budget} onChange={(event) => setForm((current) => ({ ...current, retry_budget: event.target.value }))} />
                            </Stack>
                        </Stack>
                    </TemplateSection>

                    <TemplateSection title="Prompting" description="Raw prompt override and system-level instructions.">
                        <TextField
                            label="System prompt override"
                            multiline
                            minRows={6}
                            value={form.system_prompt}
                            onChange={(event) => setForm((current) => ({ ...current, system_prompt: event.target.value }))}
                            fullWidth
                        />
                    </TemplateSection>

                    <TemplateSection title="Review + save" description="Final validation and save actions.">
                        <TemplateValidationPanel
                            validationError={validationError}
                            validationWarnings={validationWarnings}
                            createAgentError={createAgentError}
                            isCreatingAgent={isCreatingAgent}
                            onCreateAgent={onCreateAgent}
                            onImportMarkdown={onImportMarkdown}
                        />
                    </TemplateSection>
                </Stack>

                {showRegistryPanel ? (
                    <Stack spacing={2} sx={{ width: { xs: "100%", xl: 420 }, flexShrink: 0 }}>
                        <AgentRegistryPanel
                            agents={agents}
                            isLoadingAgents={isLoadingAgents}
                            agentLiveStatus={agentLiveStatus}
                            simulationAgentId={simulationAgentId}
                            isSimulatingAgent={isSimulatingAgent}
                            getSkillDisplayName={getSkillDisplayName}
                            onDuplicateAgent={onDuplicateAgent}
                            onToggleAgent={onToggleAgent}
                            onOpenVersions={onOpenVersions}
                            onOpenTestRun={onOpenTestRun}
                            onSimulateAgent={onSimulateAgent}
                        />
                        {templatePreview == null && !validationError && validationWarnings.length === 0 ? null : (
                            <>
                                <Divider />
                                <Alert severity="info">Preview, validation, registry live here while builder stays focused.</Alert>
                            </>
                        )}
                    </Stack>
                ) : null}
            </Stack>
        </Stack>
    );
}
