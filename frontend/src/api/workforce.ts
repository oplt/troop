import { apiFetch } from "./client";

// ─── Department Types ────────────────────────────────────────

export type Department = {
    id: string;
    company_id: string;
    name: string;
    slug: string;
    description: string | null;
    parent_department_id: string | null;
    is_archived: boolean;
    created_at: string;
    updated_at: string;
};

export type DepartmentCreatePayload = {
    company_id: string;
    name: string;
    slug: string;
    description?: string | null;
    parent_department_id?: string | null;
};

export type DepartmentUpdatePayload = {
    name?: string;
    description?: string | null;
    parent_department_id?: string | null;
};

// ─── Skill Types ─────────────────────────────────────────────

export type SkillScope = "task" | "project" | "organization" | "template" | "global";
export type SkillStatus = "draft" | "testing" | "active" | "deprecated" | "archived";

export type Skill = {
    id: string;
    owner_id: string;
    company_id: string | null;
    project_id: string | null;
    name: string;
    slug: string;
    scope: SkillScope;
    status: SkillStatus;
    purpose: string;
    when_to_use: string;
    capabilities: string[];
    inputs: Record<string, unknown>;
    outputs: Record<string, unknown>;
    instructions: string;
    tools: string[];
    knowledge: string[];
    constraints: string[];
    risk_level: string;
    examples: string[];
    evaluation_criteria: string[];
    version: number;
    parent_skill_id: string | null;
    created_at: string;
    updated_at: string;
};

export type SkillVersion = {
    id: string;
    skill_id: string;
    version_number: number;
    snapshot_json: Record<string, unknown>;
    created_by_user_id: string | null;
    created_at: string;
};

export type SkillUsage = {
    skill_id: string;
    agent_count: number;
    task_count: number;
    last_used_at: string | null;
};

export type SkillDraft = {
    id: string;
    owner_id: string;
    company_id: string | null;
    project_id: string | null;
    name: string;
    slug: string;
    scope: SkillScope;
    purpose: string;
    when_to_use: string;
    capabilities: string[];
    inputs: Record<string, unknown>;
    outputs: Record<string, unknown>;
    instructions: string;
    tools: string[];
    knowledge: string[];
    constraints: string[];
    risk_level: string;
    examples: string[];
    evaluation_criteria: string[];
    validation_errors: string[];
    validation_warnings: string[];
    duplicate_matches: Array<{
        skill_id: string;
        skill_name: string;
        similarity: number;
    }>;
    is_valid: boolean;
    created_at: string;
    updated_at: string;
    /** @deprecated Use scope instead */
    target_scope?: SkillScope;
};

export type SkillDraftCreatePayload = {
    company_id?: string | null;
    project_id?: string | null;
    name: string;
    slug: string;
    scope: SkillScope;
    purpose: string;
    when_to_use: string;
    capabilities?: string[];
    inputs?: Record<string, unknown>;
    outputs?: Record<string, unknown>;
    instructions?: string;
    tools?: string[];
    knowledge?: string[];
    constraints?: string[];
    risk_level?: string;
    examples?: string[];
    evaluation_criteria?: string[];
};

export type SkillDraftUpdatePayload = Partial<SkillDraftCreatePayload>;

// ─── Task Intelligence Types ─────────────────────────────────

export type TaskAnalysis = {
    id: string;
    task_id: string;
    project_id: string;
    analyzer_version: string;
    model_name: string | null;
    content_fingerprint: string;
    objective: string;
    task_category: string;
    risk_level: string;
    autonomy_recommendation: string;
    required_capabilities_json: string[];
    required_tools_json: string[];
    knowledge_requirements_json: string[];
    expected_artifacts_json: string[];
    acceptance_criteria_json: string[];
    review_requirements_json: string[];
    approval_requirements_json: string[];
    created_at: string;
    /** Normalized convenience aliases used by UI */
    required_capabilities: string[];
    covered_requirements: string[];
    missing_requirements: string[];
    risk_factors: string[];
};

export type SkillMatch = {
    skill_id: string;
    skill_slug: string;
    skill_name: string;
    score: number;
    explanation: string;
    matched_capabilities: string[];
    scope: string;
    status: string;
    /** aliases for older UI fields */
    match_score: number;
    skill_scope?: SkillScope;
    coverage_percentage?: number;
};

export type GapDetection = {
    covered: Array<{ capability: string; skill_id?: string; score?: number }>;
    partial: Array<{ capability: string; skill_id?: string; score?: number }>;
    missing: Array<{ capability: string }>;
    matches: SkillMatch[];
};

export type GeneratedSkillDraft = {
    id: string;
    name: string;
    slug: string;
    purpose?: string;
    description?: string;
    confidence?: number;
    capabilities_json?: string[];
    /** aliases */
    draft_id: string;
    capabilities: string[];
    confidence_score: number;
    reasoning: string;
};

export type AgentMatch = {
    agent_id: string;
    agent_name: string;
    score: number;
    coverage_score?: number;
    explanation: string;
    covered_capabilities?: string[];
    missing_capabilities?: string[];
    matched_skills?: string[];
    /** aliases */
    match_score: number;
    skill_coverage: number;
    missing_skills: string[];
};

export type AssembledAgent = {
    proposed_name?: string;
    proposed_slug?: string;
    skill_ids?: string[];
    skill_slugs?: string[];
    capabilities?: string[];
    tools?: string[];
    rationale?: string;
    recommended_agents?: string[];
    assembly_type?: string;
    historical_success?: string;
    /** aliases for panel */
    agent_id: string;
    agent_name: string;
    recommended_skills: string[];
    estimated_success_probability: number | null;
    notes: string;
};

export type ProjectAnalysis = {
    id: string;
    project_id: string;
    analyzer_version: string;
    recommended_tasks_json: Array<Record<string, unknown>>;
    recommended_skills_json: Array<Record<string, unknown>>;
    recommended_agents_json: Array<Record<string, unknown>>;
    recommended_workflow_json: Record<string, unknown>;
    created_at: string;
};

// ─── Tool & Workflow Types ───────────────────────────────────

export type WorkforceTool = {
    name: string;
    description: string;
    category: string;
    risk_level: string;
    requires_approval: boolean;
};

export type WorkflowDefinition = {
    id: string;
    name: string;
    description: string;
    status?: string;
    slug?: string;
    category?: string;
    stages?: Array<Record<string, unknown>>;
    required_skills?: string[];
    created_at?: string;
};

// ─── Department API ──────────────────────────────────────────

export async function listDepartments(companyId: string): Promise<Department[]> {
    return apiFetch(`/workforce/departments?company_id=${encodeURIComponent(companyId)}`);
}

export async function createDepartment(payload: DepartmentCreatePayload): Promise<Department> {
    return apiFetch("/workforce/departments", {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

export async function updateDepartment(
    departmentId: string,
    payload: DepartmentUpdatePayload
): Promise<Department> {
    return apiFetch(`/workforce/departments/${departmentId}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
    });
}

export async function archiveDepartment(departmentId: string): Promise<void> {
    return apiFetch(`/workforce/departments/${departmentId}/archive`, {
        method: "POST",
    });
}

// ─── Skill API ───────────────────────────────────────────────

export async function listSkills(): Promise<Skill[]> {
    return apiFetch("/workforce/skills");
}

export async function getSkill(skillId: string): Promise<Skill> {
    return apiFetch(`/workforce/skills/${skillId}`);
}

export async function listSkillVersions(skillId: string): Promise<SkillVersion[]> {
    return apiFetch(`/workforce/skills/${skillId}/versions`);
}

export async function getSkillUsage(skillId: string): Promise<SkillUsage> {
    return apiFetch(`/workforce/skills/${skillId}/usage`);
}

export async function promoteSkill(skillId: string, targetScope: SkillScope): Promise<Skill> {
    return apiFetch(`/workforce/skills/${skillId}/promote`, {
        method: "POST",
        body: JSON.stringify({ target_scope: targetScope }),
    });
}

// ─── Skill Draft API ─────────────────────────────────────────

export async function listSkillDrafts(): Promise<SkillDraft[]> {
    return apiFetch("/workforce/skill-drafts");
}

export async function getSkillDraft(draftId: string): Promise<SkillDraft> {
    return apiFetch(`/workforce/skill-drafts/${draftId}`);
}

export async function createSkillDraft(payload: SkillDraftCreatePayload): Promise<SkillDraft> {
    const body = {
        company_id: payload.company_id ?? null,
        source_project_id: payload.project_id ?? null,
        name: payload.name,
        slug: payload.slug,
        scope: payload.scope,
        purpose: payload.purpose,
        when_to_use: payload.when_to_use,
        instructions_markdown: payload.instructions ?? "",
        capabilities: payload.capabilities ?? [],
        required_tools: payload.tools ?? [],
        knowledge_requirements: payload.knowledge ?? [],
        input_schema: payload.inputs ?? {},
        output_schema: payload.outputs ?? {},
        constraints_markdown: Array.isArray(payload.constraints)
            ? payload.constraints.join("\n")
            : "",
        risk_level: payload.risk_level ?? "medium",
        examples: payload.examples ?? [],
        evaluation_criteria: payload.evaluation_criteria ?? [],
        source_type: "manual",
    };
    return apiFetch("/workforce/skill-drafts", {
        method: "POST",
        body: JSON.stringify(body),
    });
}

export async function updateSkillDraft(
    draftId: string,
    payload: SkillDraftUpdatePayload
): Promise<SkillDraft> {
    return apiFetch(`/workforce/skill-drafts/${draftId}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
    });
}

export async function validateSkillDraft(draftId: string): Promise<SkillDraft> {
    return apiFetch(`/workforce/skill-drafts/${draftId}/validate`, {
        method: "POST",
    });
}

export async function publishSkillDraft(draftId: string): Promise<Skill> {
    return apiFetch(`/workforce/skill-drafts/${draftId}/publish`, {
        method: "POST",
    });
}

// ─── Task Intelligence API ───────────────────────────────────

function normalizeTaskAnalysis(raw: Record<string, unknown>): TaskAnalysis {
    const caps = (raw.required_capabilities_json as string[]) || (raw.required_capabilities as string[]) || [];
    return {
        ...(raw as unknown as TaskAnalysis),
        required_capabilities_json: caps,
        required_capabilities: caps,
        covered_requirements: (raw.covered_requirements as string[]) || [],
        missing_requirements: (raw.missing_requirements as string[]) || [],
        risk_factors: raw.risk_level ? [String(raw.risk_level)] : [],
        required_tools_json: (raw.required_tools_json as string[]) || [],
        knowledge_requirements_json: (raw.knowledge_requirements_json as string[]) || [],
        expected_artifacts_json: (raw.expected_artifacts_json as string[]) || [],
        acceptance_criteria_json: (raw.acceptance_criteria_json as string[]) || [],
        review_requirements_json: (raw.review_requirements_json as string[]) || [],
        approval_requirements_json: (raw.approval_requirements_json as string[]) || [],
    };
}

function normalizeSkillMatch(raw: Record<string, unknown>): SkillMatch {
    const score = Number(raw.score ?? raw.match_score ?? 0);
    return {
        skill_id: String(raw.skill_id),
        skill_slug: String(raw.skill_slug || ""),
        skill_name: String(raw.skill_name || ""),
        score,
        match_score: score,
        explanation: String(raw.explanation || ""),
        matched_capabilities: (raw.matched_capabilities as string[]) || [],
        scope: String(raw.scope || "organization"),
        status: String(raw.status || "active"),
        coverage_percentage: Math.round(score * 100),
        skill_scope: (raw.scope as SkillScope) || undefined,
    };
}

function normalizeGeneratedDraft(raw: Record<string, unknown>): GeneratedSkillDraft {
    const id = String(raw.id || raw.draft_id || "");
    const caps = (raw.capabilities_json as string[]) || (raw.capabilities as string[]) || [];
    const confidence = Number(raw.confidence ?? raw.confidence_score ?? 0.8);
    return {
        id,
        draft_id: id,
        name: String(raw.name || ""),
        slug: String(raw.slug || ""),
        purpose: raw.purpose ? String(raw.purpose) : undefined,
        description: raw.description ? String(raw.description) : undefined,
        capabilities_json: caps,
        capabilities: caps,
        confidence,
        confidence_score: confidence,
        reasoning: String(raw.purpose || raw.description || "Generated from task gaps"),
    };
}

function normalizeAgentMatch(raw: Record<string, unknown>): AgentMatch {
    const score = Number(raw.score ?? raw.coverage_score ?? raw.match_score ?? 0);
    const missing = (raw.missing_capabilities as string[]) || (raw.missing_skills as string[]) || [];
    return {
        agent_id: String(raw.agent_id),
        agent_name: String(raw.agent_name || ""),
        score,
        coverage_score: score,
        match_score: score,
        skill_coverage: score,
        explanation: String(raw.explanation || ""),
        covered_capabilities: (raw.covered_capabilities as string[]) || [],
        missing_capabilities: missing,
        missing_skills: missing,
        matched_skills: (raw.matched_skills as string[]) || [],
    };
}

export async function analyzeTask(taskId: string): Promise<TaskAnalysis> {
    const raw = await apiFetch<Record<string, unknown>>(`/workforce/tasks/${taskId}/analyze`, {
        method: "POST",
    });
    return normalizeTaskAnalysis(raw);
}

export async function getTaskAnalysis(taskId: string): Promise<TaskAnalysis> {
    const raw = await apiFetch<Record<string, unknown>>(`/workforce/tasks/${taskId}/analysis`);
    return normalizeTaskAnalysis(raw);
}

export async function findSkillMatches(taskId: string): Promise<SkillMatch[]> {
    const raw = await apiFetch<GapDetection | SkillMatch[]>(`/workforce/tasks/${taskId}/skill-matches`);
    if (Array.isArray(raw)) {
        return raw.map((item) => normalizeSkillMatch(item as unknown as Record<string, unknown>));
    }
    const gap = raw as GapDetection;
    const matches = (gap.matches || []).map((item) =>
        normalizeSkillMatch(item as unknown as Record<string, unknown>),
    );
    // Stash gap coverage onto first match via side channel is awkward; return matches only.
    // Panel reads covered/missing from analysis; enrich analysis after find skills in panel.
    (findSkillMatches as unknown as { lastGap?: GapDetection }).lastGap = {
        covered: gap.covered || [],
        partial: gap.partial || [],
        missing: gap.missing || [],
        matches,
    };
    return matches;
}

export function getLastSkillGap(): GapDetection | undefined {
    return (findSkillMatches as unknown as { lastGap?: GapDetection }).lastGap;
}

export async function generateMissingSkills(taskId: string): Promise<GeneratedSkillDraft[]> {
    const raw = await apiFetch<Array<Record<string, unknown>>>(`/workforce/tasks/${taskId}/generate-skills`, {
        method: "POST",
    });
    return (raw || []).map(normalizeGeneratedDraft);
}

export async function findAgentMatches(taskId: string): Promise<AgentMatch[]> {
    const raw = await apiFetch<Array<Record<string, unknown>>>(`/workforce/tasks/${taskId}/agent-matches`);
    return (raw || []).map(normalizeAgentMatch);
}

export async function assembleAgent(
    taskId: string,
    payload?: {
        name?: string;
        slug?: string;
        assign_to_task?: boolean;
        activate?: boolean;
        preferred_skills?: string[];
        constraints?: Record<string, unknown>;
    }
): Promise<AssembledAgent> {
    const raw = await apiFetch<Record<string, unknown>>(`/workforce/tasks/${taskId}/assemble-agent`, {
        method: "POST",
        body: JSON.stringify(payload ?? { activate: true, assign_to_task: true }),
    });
    const name = String(raw.proposed_name || raw.agent_name || "Proposed agent");
    const skills = (raw.skill_slugs as string[]) || (raw.recommended_skills as string[]) || [];
    const agents = (raw.recommended_agents as string[]) || [];
    return {
        ...(raw as unknown as AssembledAgent),
        agent_id: String(agents[0] || raw.agent_id || raw.proposed_slug || ""),
        agent_name: name,
        recommended_skills: skills,
        // Never fabricate success probability — backend does not return one.
        estimated_success_probability: null,
        historical_success: "Not enough historical data",
        notes: String(raw.rationale || raw.notes || ""),
        proposed_name: name,
        skill_slugs: skills,
        rationale: String(raw.rationale || ""),
        assembly_type: String(raw.assembly_type || ""),
    };
}

export async function importSkillMarkdown(payload: {
    content: string;
    file_name?: string;
    company_id?: string | null;
    scope?: SkillScope;
}): Promise<SkillDraft> {
    return apiFetch("/workforce/skill-drafts/import-markdown", {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

export async function migrateSkillPacks(publish = true): Promise<{
    migrated: number;
    drafts: number;
    skipped: number;
}> {
    return apiFetch(`/workforce/skills/migrate-skill-packs?publish=${publish ? "true" : "false"}`, {
        method: "POST",
    });
}

export async function listWorkforceWorkflows(): Promise<WorkflowDefinition[]> {
    return apiFetch("/workforce/workflows");
}

export async function createWorkforceWorkflow(payload: Record<string, unknown>): Promise<WorkflowDefinition> {
    return apiFetch("/workforce/workflows", {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

export async function publishWorkforceWorkflow(
    workflowId: string,
    payload: Record<string, unknown> = {}
): Promise<WorkflowDefinition> {
    return apiFetch(`/workforce/workflows/${workflowId}/publish`, {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

export async function startWorkforceWorkflowRun(
    workflowId: string,
    payload: Record<string, unknown> = {}
): Promise<Record<string, unknown>> {
    return apiFetch(`/workforce/workflows/${workflowId}/runs`, {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

export async function analyzeProject(projectId: string): Promise<ProjectAnalysis> {
    return apiFetch(`/workforce/projects/${projectId}/analyze`, {
        method: "POST",
    });
}

// ─── Tool & Workflow API ─────────────────────────────────────

export async function listWorkforceTools(): Promise<WorkforceTool[]> {
    return apiFetch("/workforce/tools");
}

export async function listWorkflows(): Promise<WorkflowDefinition[]> {
    return apiFetch("/workforce/workflows");
}

// ─── Marketplace & Connectors ────────────────────────────────

export type MarketplaceCatalog = {
    skills: Array<Record<string, unknown>>;
    workflows: Array<Record<string, unknown>>;
    departments: Array<Record<string, unknown>>;
    agent_templates: Array<Record<string, unknown>>;
    summary: {
        skills: number;
        workflows: number;
        departments: number;
        agent_templates: number;
    };
};

export type MarketplaceInstallResult = {
    status: string;
    kind: string;
    slug: string;
    skill_id?: string;
    draft_id?: string;
    workflow_id?: string;
    department_id?: string;
    template_id?: string;
};

export type ConnectorDefinition = {
    id: string;
    slug: string;
    name: string;
    description: string;
    provider_type: string;
    config_schema_json: Record<string, unknown>;
};

export type ConnectorInstallation = {
    id: string;
    connector_definition_id: string;
    owner_id: string;
    company_id: string | null;
    name: string;
    status: string;
    config_json: Record<string, unknown>;
    metadata_json: Record<string, unknown>;
};

export async function getMarketplaceCatalog(): Promise<MarketplaceCatalog> {
    return apiFetch("/workforce/marketplace");
}

export async function installMarketplaceSkill(payload: {
    slug: string;
    company_id?: string | null;
    publish?: boolean;
}): Promise<MarketplaceInstallResult> {
    return apiFetch("/workforce/marketplace/skills/install", {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

export async function installMarketplaceWorkflow(payload: {
    slug: string;
    company_id?: string | null;
    publish?: boolean;
}): Promise<MarketplaceInstallResult> {
    return apiFetch("/workforce/marketplace/workflows/install", {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

export async function installMarketplaceDepartment(payload: {
    slug: string;
    company_id: string;
}): Promise<MarketplaceInstallResult> {
    return apiFetch("/workforce/marketplace/departments/install", {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

export async function installMarketplaceAgentTemplate(payload: {
    slug: string;
}): Promise<MarketplaceInstallResult> {
    return apiFetch("/workforce/marketplace/agent-templates/install", {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

export async function seedMarketplaceAgentTemplates(): Promise<{
    installed: number;
    skipped: number;
}> {
    return apiFetch("/workforce/marketplace/agent-templates/seed", { method: "POST" });
}

export async function listConnectorDefinitions(): Promise<ConnectorDefinition[]> {
    return apiFetch("/workforce/connectors/definitions");
}

export async function listConnectorInstallations(): Promise<ConnectorInstallation[]> {
    return apiFetch("/workforce/connectors/installations");
}

export async function installConnector(payload: {
    name: string;
    connector_slug?: string;
    connector_definition_id?: string;
    company_id?: string | null;
    config_json: Record<string, unknown>;
}): Promise<ConnectorInstallation> {
    return apiFetch("/workforce/connectors/installations", {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

export async function testConnectorInstallation(
    installationId: string
): Promise<{ ok: boolean; error?: string; provider_type?: string; tool_count?: number }> {
    return apiFetch(`/workforce/connectors/installations/${installationId}/test`, {
        method: "POST",
    });
}
