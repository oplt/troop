import type { Dispatch, SetStateAction } from "react";

import type {
    Agent,
    AgentTemplate,
    SkillPack,
    TeamTemplate,
    TaskRun,
} from "../../api/orchestration";

export type TemplateBuilderFormState = {
    name: string;
    slug: string;
    description: string;
    role: string;
    system_prompt: string;
    parent_template_slug: string;
    capabilities: string;
    allowed_tools: string;
    skills: string[];
    tags: string;
    task_filters: string;
    model: string;
    fallback_model: string;
    escalation_path: string;
    permission: string;
    memory_scope: string;
    output_format: string;
    token_budget: string;
    time_budget_seconds: string;
    retry_budget: string;
};

export type SkillBuilderFormState = {
    name: string;
    description: string;
    capabilities: string;
};

export type TemplateFilterState = {
    type: "all" | "agent" | "team" | "skill";
    roles: string[];
    domains: string[];
    outcomes: string[];
    tools: string[];
    autonomy: string[];
    visibility: string[];
    sortBy: string;
};

export type StaticTeamTemplate = TeamTemplate;

export type TemplateActionProps = {
    onCopyTemplateContract: (template: AgentTemplate) => Promise<void> | void;
    onCreateFromTemplate: (templateSlug: string) => void;
    onCreateAgent: () => void;
    onResetBuilder: () => void;
    onDuplicateAgent: (agentId: string) => void;
    onToggleAgent: (payload: { agentId: string; active: boolean }) => void;
    onOpenVersions: (agent: Agent) => void;
    onOpenTestRun: (agent: Agent) => void;
    onSimulateAgent: (agentId: string) => void;
    onImportMarkdown: (file: File) => Promise<void> | void;
};

export type TemplateTabProps = TemplateActionProps & {
    agents: Agent[];
    templates: AgentTemplate[];
    skills: SkillPack[];
    runs: TaskRun[];
    isLoadingAgents: boolean;
    form: TemplateBuilderFormState;
    setForm: Dispatch<SetStateAction<TemplateBuilderFormState>>;
    validationError: string | null;
    validationWarnings: string[];
    agentLiveStatus: Map<string, "running" | "blocked" | "queued" | "idle">;
    memoryScopeOptions: readonly string[];
    outputFormatOptions: readonly string[];
    permissionOptions: readonly string[];
    isCreatingAgent: boolean;
    createAgentError: string | null;
    isCreatingFromTemplate: boolean;
    isSimulatingAgent: boolean;
    simulationAgentId: string | null;
    getSkillDisplayName: (slug: string) => string;
};
