import { apiFetch } from "../client";

export type Agent = {
    id: string;
    project_id: string | null;
    parent_agent_id: string | null;
    reviewer_agent_id: string | null;
    provider_config_id: string | null;
    parent_template_slug: string | null;
    name: string;
    slug: string;
    description: string | null;
    role: string;
    system_prompt: string;
    mission_markdown: string;
    rules_markdown: string;
    output_contract_markdown: string;
    source_markdown: string;
    capabilities: string[];
    allowed_tools: string[];
    skills: string[];
    model_policy: Record<string, unknown>;
    permissions: string | Record<string, unknown> | null;
    escalation_path: string | null;
    visibility: string;
    is_active: boolean;
    tags: string[];
    budget: Record<string, unknown>;
    timeout_seconds: number;
    retry_limit: number;
    memory_policy: Record<string, unknown>;
    output_schema: Record<string, unknown>;
    task_filters: string[];
    inheritance: AgentInheritancePreview | null;
    lint: AgentLintSummary | null;
    metadata: Record<string, unknown>;
    version: number;
    created_at: string;
    updated_at: string;
};

export type AgentLintSummary = {
    errors: string[];
    warnings: string[];
    activation_ready: boolean;
};

export type AgentResolvedProfile = {
    capabilities: string[];
    allowed_tools: string[];
    skills: string[];
    tags: string[];
    rules_markdown: string;
    memory_policy: Record<string, unknown>;
    output_schema: Record<string, unknown>;
    budget: Record<string, unknown>;
    model_policy: Record<string, unknown>;
    permissions?: string | Record<string, unknown> | null;
    escalation_path?: string | null;
    task_filters?: string[];
};

export type AgentInheritancePreview = {
    parent_template_slug: string | null;
    inherited_fields: Record<string, unknown>;
    overridden_fields: Record<string, unknown>;
    effective: AgentResolvedProfile;
};

export type ToolSpec = {
    name: string;
    description: string;
    input_schema: Record<string, unknown>;
    output_schema: Record<string, unknown>;
    enabled: boolean;
    risk_level: "low" | "medium" | "high";
    requires_approval: boolean;
};

export type TeamTemplate = {
    id: string;
    slug: string;
    name: string;
    description: string;
    outcome: string;
    roles: string[];
    tools: string[];
    autonomy: string;
    visibility: string;
    agent_template_slugs: string[];
    canvas_layout: Record<string, unknown>;
};

export type TeamProfile = {
    id: string;
    source_team_template_slug: string;
    slug: string;
    name: string;
    description: string;
    outcome: string;
    roles: string[];
    tools: string[];
    autonomy: string;
    visibility: string;
    agent_template_slugs: string[];
    canvas_layout: Record<string, unknown>;
};

export async function listAgents(projectId?: string): Promise<Agent[]> {
    const suffix = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
    return apiFetch(`/orchestration/agents${suffix}`);
}

export async function listTools(): Promise<ToolSpec[]> {
    const response = await apiFetch<{ tools: ToolSpec[] }>("/tools");
    return response.tools;
}

export async function createAgent(payload: Record<string, unknown>): Promise<Agent> {
    return apiFetch("/orchestration/agents", { method: "POST", body: JSON.stringify(payload) });
}

export async function deleteAgent(agentId: string): Promise<void> {
    return apiFetch(`/orchestration/agents/${agentId}`, { method: "DELETE" });
}

export async function importAgentMarkdown(file: File, projectId?: string, existingAgentId?: string): Promise<Agent> {
    const formData = new FormData();
    formData.append("file", file);
    if (projectId) formData.append("project_id", projectId);
    if (existingAgentId) formData.append("existing_agent_id", existingAgentId);
    return apiFetch("/orchestration/agents/import", { method: "POST", body: formData });
}

export async function validateAgentMarkdown(file: File): Promise<{ valid: boolean; normalized: Record<string, unknown> | null; errors: string[]; warnings: string[]; activation_ready: boolean }> {
    const formData = new FormData();
    formData.append("file", file);
    return apiFetch("/orchestration/agents/validate-markdown", { method: "POST", body: formData });
}

export async function validateAgentContract(payload: Record<string, unknown>): Promise<{ valid: boolean; normalized: Record<string, unknown> | null; errors: string[]; warnings: string[]; activation_ready: boolean }> {
    return apiFetch("/orchestration/agents/validate-contract", { method: "POST", body: JSON.stringify(payload) });
}

export async function updateAgent(agentId: string, payload: Record<string, unknown>): Promise<Agent> {
    return apiFetch(`/orchestration/agents/${agentId}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export async function duplicateAgent(agentId: string): Promise<Agent> {
    return apiFetch(`/orchestration/agents/${agentId}/duplicate`, { method: "POST" });
}

export async function activateAgent(agentId: string, active: boolean): Promise<Agent> {
    return apiFetch(`/orchestration/agents/${agentId}/${active ? "activate" : "deactivate"}`, { method: "POST" });
}

export type SkillPack = {
    id?: string;
    slug: string;
    name: string;
    description: string;
    capabilities: string[];
    allowed_tools: string[];
    rules_markdown: string;
    tags: string[];
};

export type AgentTemplate = {
    id?: string;
    slug: string;
    name: string;
    description: string;
    role: string;
    parent_template_slug: string | null;
    system_prompt: string;
    mission_markdown: string;
    rules_markdown: string;
    output_contract_markdown: string;
    capabilities: string[];
    allowed_tools: string[];
    tags: string[];
    skills: string[];
    model_policy: Record<string, unknown>;
    permissions?: string | Record<string, unknown> | null;
    escalation_path?: string | null;
    budget: Record<string, unknown>;
    memory_policy: Record<string, unknown>;
    output_schema: Record<string, unknown>;
    task_filters?: string[];
    metadata: Record<string, unknown>;
};

export type AgentTestRunResult = {
    agent_id: string;
    agent_name: string;
    model_used: string | null;
    token_input: number;
    token_output: number;
    token_total: number;
    latency_ms: number;
    estimated_cost_usd: number;
    output_text: string;
    trace: Array<{ step: string; level: string; message: string; payload: Record<string, unknown> }>;
    simulated_tool_results: Array<Record<string, unknown>>;
    inheritance: AgentInheritancePreview | null;
};

export async function listAgentTemplates(): Promise<AgentTemplate[]> {
    return apiFetch("/orchestration/agents/templates");
}

export async function createAgentTemplate(payload: Omit<AgentTemplate, "id">): Promise<AgentTemplate> {
    return apiFetch("/orchestration/agents/templates", {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

export async function updateAgentTemplate(
    templateId: string,
    payload: Partial<Omit<AgentTemplate, "id">>,
): Promise<AgentTemplate> {
    return apiFetch(`/orchestration/agents/templates/${encodeURIComponent(templateId)}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
    });
}

export async function deleteAgentTemplate(templateId: string): Promise<void> {
    return apiFetch(`/orchestration/agents/templates/${encodeURIComponent(templateId)}`, {
        method: "DELETE",
    });
}

export async function updateAgentTemplateBySlug(
    slug: string,
    payload: Partial<Omit<AgentTemplate, "id">>,
): Promise<AgentTemplate> {
    return apiFetch(`/orchestration/agents/templates/slug/${encodeURIComponent(slug)}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
    });
}

export async function deleteAgentTemplateBySlug(slug: string): Promise<void> {
    return apiFetch(`/orchestration/agents/templates/slug/${encodeURIComponent(slug)}`, {
        method: "DELETE",
    });
}

export async function listSkillCatalog(): Promise<SkillPack[]> {
    return apiFetch("/orchestration/agents/skills");
}

export async function createSkillPack(payload: Omit<SkillPack, "id">): Promise<SkillPack> {
    return apiFetch("/orchestration/agents/skills", {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

export async function updateSkillPack(
    slug: string,
    payload: Partial<Omit<SkillPack, "id" | "slug">>,
): Promise<SkillPack> {
    return apiFetch(`/orchestration/agents/skills/${encodeURIComponent(slug)}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
    });
}

export async function deleteSkillPack(slug: string): Promise<void> {
    return apiFetch(`/orchestration/agents/skills/${encodeURIComponent(slug)}`, {
        method: "DELETE",
    });
}

export async function listTeamTemplates(): Promise<TeamTemplate[]> {
    return apiFetch("/orchestration/teams/templates");
}

export async function createTeamTemplate(payload: Omit<TeamTemplate, "id">): Promise<TeamTemplate> {
    return apiFetch("/orchestration/teams/templates", {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

export async function updateTeamTemplate(
    templateId: string,
    payload: Partial<Omit<TeamTemplate, "id" | "slug">>,
): Promise<TeamTemplate> {
    return apiFetch(`/orchestration/teams/templates/${encodeURIComponent(templateId)}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
    });
}

export async function deleteTeamTemplate(templateId: string): Promise<void> {
    return apiFetch(`/orchestration/teams/templates/${encodeURIComponent(templateId)}`, {
        method: "DELETE",
    });
}

export async function listTeamProfiles(): Promise<TeamProfile[]> {
    return apiFetch("/orchestration/teams/profiles");
}

export async function createTeamProfileFromTemplate(payload: {
    template_id: string;
    slug?: string;
    name?: string;
}): Promise<TeamProfile> {
    return apiFetch("/orchestration/teams/profiles/from-template", {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

export async function simulateAgent(
    agentId: string,
    payload: { scenarios?: Array<Record<string, unknown>> } = {},
): Promise<Record<string, unknown>> {
    return apiFetch(`/orchestration/agents/${agentId}/simulate`, {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

export async function createAgentFromTemplate(slug: string, overrides: Record<string, unknown>): Promise<Agent> {
    return apiFetch(`/orchestration/agents/from-template/${encodeURIComponent(slug)}`, {
        method: "POST",
        body: JSON.stringify(overrides),
    });
}

export async function testRunAgent(agentId: string, payload: Record<string, unknown>): Promise<AgentTestRunResult> {
    return apiFetch(`/orchestration/agents/${agentId}/test-run`, {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

export type AgentVersion = {
    id: string;
    agent_profile_id: string;
    version_number: number;
    source_markdown: string;
    snapshot_json: Record<string, unknown>;
    created_by_user_id: string | null;
    created_at: string;
};

export async function listAgentVersions(agentId: string): Promise<AgentVersion[]> {
    return apiFetch(`/orchestration/agents/${agentId}/versions`);
}

// ── Milestones ──────────────────────────────────────────────
