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
    purpose: string;
    when_to_use: string;
    instructions_markdown: string;
    input_schema_json: Record<string, unknown>;
    output_schema_json: Record<string, unknown>;
    capabilities_json: string[];
    required_tools_json: string[];
    knowledge_requirements_json: string[];
    constraints_markdown: string;
    risk_level: string;
    approval_policy_json: Record<string, unknown>;
    examples_json: string[];
    evaluation_criteria_json: string[];
    source_type: string;
    is_published: boolean;
    generated_by_model: string | null;
    created_at: string;
    /** Flattened aliases for UI */
    instructions?: string;
    capabilities?: string[];
    tools?: string[];
    knowledge?: string[];
    constraints?: string[];
    inputs?: Record<string, unknown>;
    outputs?: Record<string, unknown>;
    examples?: string[];
    evaluation_criteria?: string[];
    /** @deprecated Legacy snapshot field — prefer structured version fields */
    snapshot_json?: Record<string, unknown>;
};

export type SkillUsage = {
    skill_id: string;
    skill_version_id: string | null;
    run_count: number;
    success_count: number;
    human_accept_count: number;
    success_rate: number;
    avg_latency_ms: number | null;
    avg_cost_usd: number | null;
    retry_rate: number;
    last_used_at: string | null;
    promotion_recommendation: string | null;
    /** @deprecated Derived from run_count for legacy UI */
    task_count?: number;
    /** @deprecated Not tracked server-side — omit or use run_count proxy */
    agent_count?: number;
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
    confidence?: number | null;
    capabilities_json?: string[];
    /** aliases */
    draft_id: string;
    capabilities: string[];
    confidence_score?: number | null;
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
    owner_id?: string;
    current_version_id?: string | null;
    draft_version_id?: string | null;
    published_version_id?: string | null;
};

export type WorkflowDraftGraph = {
    nodes: Array<Record<string, unknown>>;
    edges: Array<Record<string, unknown>>;
    entry_node_id: string | null;
};

export type WorkflowDetail = WorkflowDefinition & {
    draft: WorkflowDraftGraph | null;
};

export type WorkflowValidationResponse = {
    valid: boolean;
    errors: string[];
    warnings: string[];
    infos: string[];
    external_write_nodes: Array<{ node_id: string; tool_slug: string; type?: string }>;
};

export type WorkflowDiffResponse = {
    nodes_added: string[];
    nodes_removed: string[];
    nodes_changed: Array<{ id: string; changed_fields: string[] }>;
    edges_added: Array<Record<string, unknown>>;
    edges_removed: Array<Record<string, unknown>>;
    entry_node_changed: boolean;
    entry_node_before: string | null;
    entry_node_after: string | null;
    graph_hash_before: string | null;
    graph_hash_after: string | null;
    graph_changed: boolean;
    summary: Record<string, number>;
};

export type WorkflowVersionSummary = {
    id: string;
    version_number: number;
    graph_hash: string | null;
    entry_node_id: string | null;
    created_at: string | null;
};

export type WorkflowRunResponse = {
    id: string;
    workflow_id: string;
    workflow_version_id: string;
    status: string;
    current_node_id: string | null;
    context_json: Record<string, unknown>;
    result_json: Record<string, unknown>;
};

export type WorkflowScaffoldGap = {
    kind: "missing_connection" | "missing_scope" | "missing_approval_step" | "unavailable_operation" | "missing_agent";
    node_id: string | null;
    provider_slug: string | null;
    operation_slug: string | null;
    message: string;
    remediation: string | null;
};

export type WorkflowGenerateResponse = {
    workflow_id: string;
    name: string;
    slug: string;
    summary: string;
    draft: WorkflowDraftGraph;
    validation: WorkflowValidationResponse;
    gaps: WorkflowScaffoldGap[];
    provenance: {
        source: string;
        prompt: string;
        model: string | null;
        generated_at: string;
        catalog_snapshot_hash: string;
        generation_mode: string;
    };
    published: boolean;
};

export type WorkflowEnvironmentSummary = {
    environment: string;
    deployed: boolean;
    deployment_id: string | null;
    workflow_version_id: string | null;
    version_number: number | null;
    graph_hash: string | null;
    deployed_at: string | null;
    connection_bindings: Record<string, Record<string, string>>;
};

export type WorkflowEnvironmentHistoryEvent = {
    id: string;
    action: string;
    workflow_version_id: string;
    connection_bindings: Record<string, Record<string, string>>;
    previous_version_id: string | null;
    actor_user_id: string | null;
    created_at: string;
};

export type WorkflowEnvironmentDiffResponse = WorkflowDiffResponse & {
    environment: string;
    current_version_id: string | null;
    candidate_version_id: string;
    bindings_added: string[];
    bindings_removed: string[];
    bindings_changed: Array<{ node_id: string; before: unknown; after: unknown }>;
    bindings_changed_count: number;
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

function asStringList(value: unknown): string[] {
    if (Array.isArray(value)) {
        return value.map((item) => String(item)).filter(Boolean);
    }
    if (typeof value === "string" && value.trim()) {
        return value.split("\n").map((line) => line.trim()).filter(Boolean);
    }
    return [];
}

function asRecord(value: unknown): Record<string, unknown> {
    return value && typeof value === "object" && !Array.isArray(value)
        ? (value as Record<string, unknown>)
        : {};
}

export function normalizeSkill(raw: Record<string, unknown>): Skill {
    const version = asRecord(raw.current_version);
    const purpose = String(raw.purpose ?? version.purpose ?? "");
    const capabilities = asStringList(raw.capabilities ?? version.capabilities_json);
    const tools = asStringList(raw.tools ?? version.required_tools_json);
    const knowledge = asStringList(raw.knowledge ?? version.knowledge_requirements_json);
    const instructions = String(
        raw.instructions ?? raw.instructions_markdown ?? version.instructions_markdown ?? ""
    );
    const constraints = asStringList(raw.constraints ?? version.constraints_markdown);
    return {
        id: String(raw.id),
        owner_id: String(raw.owner_id || ""),
        company_id: (raw.company_id as string | null) ?? null,
        project_id: (raw.project_id as string | null) ?? null,
        name: String(raw.name || ""),
        slug: String(raw.slug || ""),
        scope: (raw.scope as SkillScope) || "organization",
        status: (raw.status as SkillStatus) || "draft",
        purpose,
        when_to_use: String(raw.when_to_use ?? version.when_to_use ?? ""),
        capabilities,
        inputs: asRecord(raw.inputs ?? version.input_schema_json),
        outputs: asRecord(raw.outputs ?? version.output_schema_json),
        instructions,
        tools,
        knowledge,
        constraints,
        risk_level: String(raw.risk_level ?? version.risk_level ?? "low"),
        examples: asStringList(raw.examples ?? version.examples_json),
        evaluation_criteria: asStringList(
            raw.evaluation_criteria ?? version.evaluation_criteria_json
        ),
        version: Number(raw.version ?? version.version_number ?? 0),
        parent_skill_id: (raw.parent_skill_id as string | null) ?? null,
        created_at: String(raw.created_at || ""),
        updated_at: String(raw.updated_at || ""),
    };
}

export function normalizeSkillVersion(raw: Record<string, unknown>): SkillVersion {
    const capabilities = asStringList(raw.capabilities ?? raw.capabilities_json);
    const tools = asStringList(raw.tools ?? raw.required_tools_json);
    const knowledge = asStringList(raw.knowledge ?? raw.knowledge_requirements_json);
    const instructions = String(raw.instructions ?? raw.instructions_markdown ?? "");
    const constraintsMarkdown = String(raw.constraints_markdown ?? "");
    const constraints = asStringList(raw.constraints ?? constraintsMarkdown);
    const inputs = asRecord(raw.inputs ?? raw.input_schema_json);
    const outputs = asRecord(raw.outputs ?? raw.output_schema_json);
    const examples = asStringList(raw.examples ?? raw.examples_json);
    const evaluationCriteria = asStringList(
        raw.evaluation_criteria ?? raw.evaluation_criteria_json
    );
    return {
        id: String(raw.id),
        skill_id: String(raw.skill_id || ""),
        version_number: Number(raw.version_number ?? 0),
        purpose: String(raw.purpose ?? ""),
        when_to_use: String(raw.when_to_use ?? ""),
        instructions_markdown: instructions,
        input_schema_json: inputs,
        output_schema_json: outputs,
        capabilities_json: capabilities,
        required_tools_json: tools,
        knowledge_requirements_json: knowledge,
        constraints_markdown: constraintsMarkdown,
        risk_level: String(raw.risk_level ?? "low"),
        approval_policy_json: asRecord(raw.approval_policy_json),
        examples_json: examples,
        evaluation_criteria_json: evaluationCriteria,
        source_type: String(raw.source_type ?? "manual"),
        is_published: Boolean(raw.is_published ?? false),
        generated_by_model: (raw.generated_by_model as string | null) ?? null,
        created_at: String(raw.created_at || ""),
        instructions,
        capabilities,
        tools,
        knowledge,
        constraints,
        inputs,
        outputs,
        examples,
        evaluation_criteria: evaluationCriteria,
        snapshot_json: asRecord(raw.snapshot_json),
    };
}

export function normalizeSkillUsage(raw: Record<string, unknown>): SkillUsage {
    const runCount = Number(raw.run_count ?? raw.task_count ?? 0);
    const successCount = Number(raw.success_count ?? 0);
    const humanAcceptCount = Number(raw.human_accept_count ?? 0);
    const successRateRaw = raw.success_rate;
    const successRate =
        successRateRaw === null || successRateRaw === undefined || successRateRaw === ""
            ? runCount > 0
                ? successCount / runCount
                : 0
            : Number(successRateRaw);
    const avgLatencyRaw = raw.avg_latency_ms;
    const avgCostRaw = raw.avg_cost_usd;
    const retryRateRaw = raw.retry_rate;
    return {
        skill_id: String(raw.skill_id || ""),
        skill_version_id: (raw.skill_version_id as string | null) ?? null,
        run_count: runCount,
        success_count: successCount,
        human_accept_count: humanAcceptCount,
        success_rate: Number.isFinite(successRate) ? successRate : 0,
        avg_latency_ms:
            avgLatencyRaw === null || avgLatencyRaw === undefined || avgLatencyRaw === ""
                ? null
                : Number(avgLatencyRaw),
        avg_cost_usd:
            avgCostRaw === null || avgCostRaw === undefined || avgCostRaw === ""
                ? null
                : Number(avgCostRaw),
        retry_rate:
            retryRateRaw === null || retryRateRaw === undefined || retryRateRaw === ""
                ? 0
                : Number(retryRateRaw),
        last_used_at: raw.last_used_at ? String(raw.last_used_at) : null,
        promotion_recommendation: raw.promotion_recommendation
            ? String(raw.promotion_recommendation)
            : null,
        task_count: runCount,
        agent_count: raw.agent_count !== undefined ? Number(raw.agent_count) : undefined,
    };
}

export function normalizeSkillDraft(raw: Record<string, unknown>): SkillDraft {
    const errors = asStringList(raw.validation_errors ?? raw.validation_errors_json);
    const warnings = asStringList(raw.validation_warnings ?? raw.warnings_json);
    const capabilities = asStringList(raw.capabilities ?? raw.capabilities_json);
    const tools = asStringList(raw.tools ?? raw.required_tools_json);
    const knowledge = asStringList(raw.knowledge ?? raw.knowledge_requirements_json);
    const instructions = String(raw.instructions ?? raw.instructions_markdown ?? "");
    return {
        id: String(raw.id),
        owner_id: String(raw.owner_id || ""),
        company_id: (raw.company_id as string | null) ?? null,
        project_id: (raw.project_id as string | null) ?? (raw.source_project_id as string | null) ?? null,
        name: String(raw.name || ""),
        slug: String(raw.slug || ""),
        scope: (raw.scope as SkillScope) || "project",
        purpose: String(raw.purpose || ""),
        when_to_use: String(raw.when_to_use || ""),
        capabilities,
        inputs: asRecord(raw.inputs ?? raw.input_schema_json),
        outputs: asRecord(raw.outputs ?? raw.output_schema_json),
        instructions,
        tools,
        knowledge,
        constraints: asStringList(raw.constraints ?? raw.constraints_markdown),
        risk_level: String(raw.risk_level || "low"),
        examples: asStringList(raw.examples ?? raw.examples_json),
        evaluation_criteria: asStringList(
            raw.evaluation_criteria ?? raw.evaluation_criteria_json
        ),
        validation_errors: errors,
        validation_warnings: warnings,
        duplicate_matches: Array.isArray(raw.duplicate_matches)
            ? (raw.duplicate_matches as SkillDraft["duplicate_matches"])
            : Array.isArray(raw.duplicate_matches_json)
              ? (raw.duplicate_matches_json as SkillDraft["duplicate_matches"])
              : [],
        is_valid: Boolean(raw.is_valid ?? (errors.length === 0 && Boolean(raw.purpose))),
        created_at: String(raw.created_at || ""),
        updated_at: String(raw.updated_at || ""),
        target_scope: (raw.scope as SkillScope) || undefined,
    };
}

function toBackendDraftPayload(
    payload: SkillDraftCreatePayload | SkillDraftUpdatePayload
): Record<string, unknown> {
    const body: Record<string, unknown> = {};
    if ("company_id" in payload) body.company_id = payload.company_id ?? null;
    if ("project_id" in payload && payload.project_id !== undefined) {
        body.source_project_id = payload.project_id;
    }
    if (payload.name !== undefined) body.name = payload.name;
    if (payload.slug !== undefined) body.slug = payload.slug;
    if (payload.scope !== undefined) body.scope = payload.scope;
    if (payload.purpose !== undefined) body.purpose = payload.purpose;
    if (payload.when_to_use !== undefined) body.when_to_use = payload.when_to_use;
    if (payload.instructions !== undefined) body.instructions_markdown = payload.instructions;
    if (payload.capabilities !== undefined) body.capabilities = payload.capabilities;
    if (payload.tools !== undefined) body.required_tools = payload.tools;
    if (payload.knowledge !== undefined) body.knowledge_requirements = payload.knowledge;
    if (payload.inputs !== undefined) body.input_schema = payload.inputs;
    if (payload.outputs !== undefined) body.output_schema = payload.outputs;
    if (payload.constraints !== undefined) {
        body.constraints_markdown = Array.isArray(payload.constraints)
            ? payload.constraints.join("\n")
            : payload.constraints;
    }
    if (payload.risk_level !== undefined) body.risk_level = payload.risk_level;
    if (payload.examples !== undefined) body.examples = payload.examples;
    if (payload.evaluation_criteria !== undefined) {
        body.evaluation_criteria = payload.evaluation_criteria;
    }
    return body;
}

export async function listSkills(): Promise<Skill[]> {
    const raw = await apiFetch<Array<Record<string, unknown>>>("/workforce/skills");
    return (raw || []).map(normalizeSkill);
}

export async function getSkill(skillId: string): Promise<Skill> {
    const raw = await apiFetch<Record<string, unknown>>(`/workforce/skills/${skillId}`);
    return normalizeSkill(raw);
}

export async function listSkillVersions(skillId: string): Promise<SkillVersion[]> {
    const raw = await apiFetch<Array<Record<string, unknown>>>(
        `/workforce/skills/${skillId}/versions`
    );
    return (raw || []).map(normalizeSkillVersion);
}

export async function getSkillUsage(skillId: string): Promise<SkillUsage> {
    const raw = await apiFetch<Record<string, unknown>>(`/workforce/skills/${skillId}/usage`);
    return normalizeSkillUsage(raw);
}

export async function promoteSkill(skillId: string, targetScope: SkillScope): Promise<Skill> {
    const raw = await apiFetch<Record<string, unknown>>(`/workforce/skills/${skillId}/promote`, {
        method: "POST",
        body: JSON.stringify({ target_scope: targetScope }),
    });
    return normalizeSkill(raw);
}

// ─── Skill Draft API ─────────────────────────────────────────

export async function listSkillDrafts(): Promise<SkillDraft[]> {
    const raw = await apiFetch<Array<Record<string, unknown>>>("/workforce/skill-drafts");
    return (raw || []).map(normalizeSkillDraft);
}

export async function getSkillDraft(draftId: string): Promise<SkillDraft> {
    const raw = await apiFetch<Record<string, unknown>>(`/workforce/skill-drafts/${draftId}`);
    return normalizeSkillDraft(raw);
}

export async function createSkillDraft(payload: SkillDraftCreatePayload): Promise<SkillDraft> {
    const raw = await apiFetch<Record<string, unknown>>("/workforce/skill-drafts", {
        method: "POST",
        body: JSON.stringify({ ...toBackendDraftPayload(payload), source_type: "manual" }),
    });
    return normalizeSkillDraft(raw);
}

export async function updateSkillDraft(
    draftId: string,
    payload: SkillDraftUpdatePayload
): Promise<SkillDraft> {
    const raw = await apiFetch<Record<string, unknown>>(`/workforce/skill-drafts/${draftId}`, {
        method: "PATCH",
        body: JSON.stringify(toBackendDraftPayload(payload)),
    });
    return normalizeSkillDraft(raw);
}

export async function validateSkillDraft(draftId: string): Promise<SkillDraft> {
    const raw = await apiFetch<Record<string, unknown>>(`/workforce/skill-drafts/${draftId}/validate`, {
        method: "POST",
    });
    return normalizeSkillDraft(raw);
}

export async function publishSkillDraft(draftId: string): Promise<Skill> {
    const raw = await apiFetch<Record<string, unknown>>(`/workforce/skill-drafts/${draftId}/publish`, {
        method: "POST",
    });
    return normalizeSkill(raw);
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
    const confidenceRaw = raw.confidence ?? raw.confidence_score;
    const confidence =
        confidenceRaw === null || confidenceRaw === undefined || confidenceRaw === ""
            ? null
            : Number(confidenceRaw);
    const calibrated =
        confidence !== null && Number.isFinite(confidence) ? confidence : null;
    return {
        id,
        draft_id: id,
        name: String(raw.name || ""),
        slug: String(raw.slug || ""),
        purpose: raw.purpose ? String(raw.purpose) : undefined,
        description: raw.description ? String(raw.description) : undefined,
        capabilities_json: caps,
        capabilities: caps,
        confidence: calibrated ?? undefined,
        confidence_score: calibrated ?? undefined,
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
    const raw = await apiFetch<Record<string, unknown>>("/workforce/skill-drafts/import-markdown", {
        method: "POST",
        body: JSON.stringify(payload),
    });
    return normalizeSkillDraft(raw);
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

export async function getWorkforceWorkflow(workflowId: string): Promise<WorkflowDetail> {
    return apiFetch(`/workforce/workflows/${workflowId}`);
}

export async function updateWorkforceWorkflowDraft(
    workflowId: string,
    payload: Record<string, unknown>,
): Promise<WorkflowDefinition> {
    return apiFetch(`/workforce/workflows/${workflowId}/draft`, {
        method: "PATCH",
        body: JSON.stringify(payload),
    });
}

export async function validateWorkforceWorkflow(workflowId: string): Promise<WorkflowValidationResponse> {
    return apiFetch(`/workforce/workflows/${workflowId}/validate`);
}

export async function diffWorkforceWorkflow(workflowId: string): Promise<WorkflowDiffResponse> {
    return apiFetch(`/workforce/workflows/${workflowId}/diff`);
}

export async function listWorkforceWorkflowVersions(workflowId: string): Promise<WorkflowVersionSummary[]> {
    return apiFetch(`/workforce/workflows/${workflowId}/versions`);
}

export async function rollbackWorkforceWorkflow(
    workflowId: string,
    versionId: string,
): Promise<WorkflowDefinition> {
    return apiFetch(`/workforce/workflows/${workflowId}/rollback`, {
        method: "POST",
        body: JSON.stringify({ version_id: versionId }),
    });
}

export async function startWorkforceWorkflowTestRun(
    workflowId: string,
    payload: Record<string, unknown> = {},
): Promise<WorkflowRunResponse> {
    return apiFetch(`/workforce/workflows/${workflowId}/test-runs`, {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

export async function createWorkforceWorkflow(payload: Record<string, unknown>): Promise<WorkflowDefinition> {
    return apiFetch("/workforce/workflows", {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

export async function generateWorkforceWorkflowDraft(payload: {
    prompt: string;
    workflow_id?: string | null;
    name?: string;
    slug?: string;
    company_id?: string | null;
    deterministic?: boolean;
}): Promise<WorkflowGenerateResponse> {
    return apiFetch("/workforce/workflows/generate", {
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

export async function listWorkforceWorkflowEnvironments(
    workflowId: string,
): Promise<WorkflowEnvironmentSummary[]> {
    return apiFetch(`/workforce/workflows/${workflowId}/environments`);
}

export async function promoteWorkforceWorkflowEnvironment(
    workflowId: string,
    environment: string,
    payload: { version_id: string; connection_bindings?: Record<string, Record<string, string>> },
): Promise<Record<string, unknown>> {
    return apiFetch(`/workforce/workflows/${workflowId}/environments/${environment}/promote`, {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

export async function rollbackWorkforceWorkflowEnvironment(
    workflowId: string,
    environment: string,
): Promise<Record<string, unknown>> {
    return apiFetch(`/workforce/workflows/${workflowId}/environments/${environment}/rollback`, {
        method: "POST",
    });
}

export async function diffWorkforceWorkflowEnvironment(
    workflowId: string,
    environment: string,
    payload: { version_id: string; connection_bindings?: Record<string, Record<string, string>> },
): Promise<WorkflowEnvironmentDiffResponse> {
    return apiFetch(`/workforce/workflows/${workflowId}/environments/${environment}/diff`, {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

export async function listWorkforceWorkflowEnvironmentHistory(
    workflowId: string,
    environment: string,
): Promise<WorkflowEnvironmentHistoryEvent[]> {
    return apiFetch(`/workforce/workflows/${workflowId}/environments/${environment}/history`);
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
    policy?: MarketplacePolicy;
};

export type MarketplacePolicy = {
    public_marketplace_enabled: boolean;
    private_workspace_packages_enabled: boolean;
    requires_signed_versions: boolean;
    requires_permission_diff_on_upgrade: boolean;
    deferred: string[];
};

export type WorkspacePackageSummary = {
    id: string;
    slug: string;
    name: string;
    description: string;
    kind: string;
    visibility: string;
    source_marketplace_slug: string | null;
    installed_version_id: string | null;
    latest_version_id: string | null;
    latest_version_label: string | null;
    trust_level: string | null;
};

export type PermissionDiff = {
    added: Record<string, string[]>;
    removed: Record<string, string[]>;
    has_escalation: boolean;
    requires_explicit_acceptance: boolean;
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

export async function listWorkspacePackages(): Promise<WorkspacePackageSummary[]> {
    return apiFetch("/workforce/marketplace/workspace-packages");
}

export async function importWorkspacePackage(payload: {
    kind: string;
    marketplace_slug: string;
    changelog?: string;
}): Promise<{ package: WorkspacePackageSummary; version: Record<string, unknown> }> {
    return apiFetch("/workforce/marketplace/workspace-packages/import", {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

export async function installWorkspacePackage(
    packageId: string,
    payload: { version_id: string; accept_permission_changes?: boolean },
): Promise<{ status: string; permission_diff: PermissionDiff }> {
    return apiFetch(`/workforce/marketplace/workspace-packages/${packageId}/install`, {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

export async function getWorkspacePackagePermissionDiff(
    packageId: string,
    toVersionId: string,
    fromVersionId?: string,
): Promise<{ diff: PermissionDiff }> {
    const params = new URLSearchParams({ to_version_id: toVersionId });
    if (fromVersionId) params.set("from_version_id", fromVersionId);
    return apiFetch(`/workforce/marketplace/workspace-packages/${packageId}/permission-diff?${params.toString()}`);
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
    connector_installation_ids?: Record<string, string>;
    agent_id?: string | null;
    project_id?: string | null;
    task_id?: string | null;
}): Promise<MarketplaceInstallResult> {
    return apiFetch("/workforce/marketplace/workflows/install", {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

export async function bootstrapEmailApprovalTemplate(payload: {
    company_id?: string | null;
    gmail_installation_id: string;
    telegram_installation_id?: string | null;
    approval_channel?: "in_app" | "telegram";
    publish?: boolean;
    project_id?: string | null;
    task_id?: string | null;
    agent_id?: string | null;
}): Promise<
    MarketplaceInstallResult & {
        project_id: string;
        task_id: string;
        agent_id: string;
        approval_channel: string;
        published: boolean;
        configuration_required: string[];
        template_pack?: Record<string, unknown>;
    }
> {
    return apiFetch("/workforce/marketplace/workflows/email-approval/bootstrap", {
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
