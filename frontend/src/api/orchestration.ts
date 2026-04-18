import { apiFetch } from "./client";

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
    visibility: string;
    is_active: boolean;
    tags: string[];
    budget: Record<string, unknown>;
    timeout_seconds: number;
    retry_limit: number;
    memory_policy: Record<string, unknown>;
    output_schema: Record<string, unknown>;
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
};

export type AgentInheritancePreview = {
    parent_template_slug: string | null;
    inherited_fields: Record<string, unknown>;
    overridden_fields: Record<string, unknown>;
    effective: AgentResolvedProfile;
};

export type OrchestrationProject = {
    id: string;
    name: string;
    slug: string;
    description: string | null;
    status: string;
    goals_markdown: string;
    settings: Record<string, unknown>;
    memory_scope: string;
    knowledge_summary: string | null;
    created_at: string;
    updated_at: string;
};

export type ProjectAgentMembership = {
    id: string;
    project_id: string;
    agent_id: string;
    role: string;
    is_default_manager: boolean;
    created_at: string;
};

export type OrchestrationTask = {
    id: string;
    project_id: string;
    created_by_user_id: string;
    assigned_agent_id: string | null;
    reviewer_agent_id: string | null;
    github_issue_link_id: string | null;
    github_issue_number?: number | null;
    github_issue_url?: string | null;
    github_repository_full_name?: string | null;
    parent_task_id?: string | null;
    title: string;
    description: string | null;
    source: string;
    task_type: string;
    priority: string;
    status: string;
    acceptance_criteria: string | null;
    due_date: string | null;
    response_sla_hours?: number | null;
    labels: string[];
    result_summary: string | null;
    result_payload: Record<string, unknown>;
    position: number;
    metadata: Record<string, unknown>;
    dependency_ids: string[];
    created_at: string;
    updated_at: string;
};

export type DagReadyTask = {
    id: string;
    title: string;
    status: string;
    dependency_count: number;
};

export type DagParallelStartResult = {
    started_run_ids: string[];
    skipped_task_ids: string[];
    messages: string[];
};

export type TaskRun = {
    id: string;
    project_id: string;
    task_id: string | null;
    triggered_by_user_id: string | null;
    orchestrator_agent_id: string | null;
    worker_agent_id: string | null;
    reviewer_agent_id: string | null;
    provider_config_id: string | null;
    brainstorm_id: string | null;
    run_mode: string;
    status: string;
    model_name: string | null;
    attempt_number: number;
    token_input: number;
    token_output: number;
    token_total: number;
    estimated_cost_micros: number;
    latency_ms: number | null;
    error_message: string | null;
    retry_count: number;
    checkpoint_json: Record<string, unknown>;
    input_payload: Record<string, unknown>;
    output_payload: Record<string, unknown>;
    created_at: string;
    started_at: string | null;
    completed_at: string | null;
    cancelled_at: string | null;
};

export type RunEvent = {
    id: string;
    run_id: string;
    task_id: string | null;
    level: string;
    event_type: string;
    message: string;
    payload: Record<string, unknown>;
    input_tokens: number;
    output_tokens: number;
    cost_usd_micros: number;
    created_at: string;
};

export type ExecutionSnapshotMeta = {
    schema_version: string;
    execution_truth: string;
    sources_read: string[];
};

export type ActiveRunSummary = {
    id: string;
    status: string;
    run_mode: string;
    attempt_number: number;
    retry_count: number;
    started_at: string | null;
    created_at: string;
    error_message: string | null;
};

export type PendingApprovalSummary = {
    id: string;
    approval_type: string;
    run_id: string | null;
    task_id: string | null;
    reason: string | null;
    created_at: string;
};

export type PendingGithubSyncSummary = {
    id: string;
    action: string;
    status: string;
    detail: string | null;
    created_at: string;
};

export type RunEventTailItem = {
    event_type: string;
    level: string;
    message: string;
    created_at: string;
};

export type RunTraceStep = {
    step_id: string;
    title: string;
    actor: string;
    status: string;
    sequence: number;
    started_at: string | null;
    completed_at: string | null;
    last_error: string | null;
    is_current: boolean;
    resumable: boolean;
    attempts: number;
    metadata: Record<string, unknown>;
};

export type DurableWorkflowState = {
    workflow_id: string | null;
    backend: string | null;
    schema_version: string | null;
    status: string | null;
    execution_handle: Record<string, unknown>;
    current_step_id: string | null;
    last_completed_step_id: string | null;
    resume_count: number;
    recovery_count: number;
    last_failure: Record<string, unknown>;
    signal_queue: Array<Record<string, unknown>>;
    signal_history: Array<Record<string, unknown>>;
    query_snapshot: Record<string, unknown>;
    migration: Record<string, unknown>;
    resumable: boolean;
};

export type TaskExecutionSnapshot = {
    meta: ExecutionSnapshotMeta;
    project_id: string;
    task_id: string;
    task_status: string;
    task_title: string;
    has_active_run: boolean;
    active_runs: ActiveRunSummary[];
    pending_approvals: PendingApprovalSummary[];
    pending_github_sync: PendingGithubSyncSummary[];
    metadata_views: Record<string, unknown>;
    routing_explainability: Record<string, unknown>;
    acceptance_summary: Record<string, unknown>;
    execution_memory: Record<string, unknown>;
    changed_artifacts: Array<Record<string, unknown>>;
    last_run_id: string | null;
    focal_run_id: string | null;
    checkpoint_excerpt: Record<string, unknown>;
    recent_events_tail: RunEventTailItem[];
    trace: RunTraceStep[];
    durable_workflow: DurableWorkflowState;
};

export type RunExecutionSnapshot = {
    meta: ExecutionSnapshotMeta;
    project_id: string;
    run: TaskRun;
    task_id: string | null;
    pending_approvals: PendingApprovalSummary[];
    pending_github_sync: PendingGithubSyncSummary[];
    routing_explainability: Record<string, unknown>;
    execution_memory: Record<string, unknown>;
    changed_artifacts: Array<Record<string, unknown>>;
    checkpoint_excerpt: Record<string, unknown>;
    recent_events_tail: RunEventTailItem[];
    trace: RunTraceStep[];
    durable_workflow: DurableWorkflowState;
    resumable: boolean;
};

export type Brainstorm = {
    id: string;
    project_id: string;
    task_id: string | null;
    initiator_user_id: string;
    moderator_agent_id: string | null;
    topic: string;
    status: string;
    mode: string;
    output_type: string;
    max_rounds: number;
    stop_conditions: Record<string, unknown>;
    participant_count: number;
    current_round: number;
    consensus_status: string;
    latest_round_summary: string | null;
    summary: string | null;
    final_recommendation: string | null;
    decision_log: Array<Record<string, unknown>>;
    created_at: string;
    updated_at: string;
};

export type BrainstormParticipant = {
    id: string;
    brainstorm_id: string;
    agent_id: string;
    order_index: number;
    stance: string | null;
    created_at: string;
};

export type BrainstormMessage = {
    id: string;
    brainstorm_id: string;
    agent_id: string | null;
    round_number: number;
    message_type: string;
    content: string;
    metadata: Record<string, unknown>;
    created_at: string;
};

export type ProviderConfig = {
    id: string;
    project_id: string | null;
    name: string;
    provider_type: string;
    base_url: string | null;
    api_key_hint: string | null;
    organization: string | null;
    default_model: string;
    fallback_model: string | null;
    temperature: number;
    max_tokens: number;
    timeout_seconds: number;
    is_default: boolean;
    is_enabled: boolean;
    metadata: Record<string, unknown>;
    last_healthcheck_status: string | null;
    last_healthcheck_latency_ms: number | null;
    is_healthy: boolean;
    last_healthcheck_at: string | null;
    created_at: string;
    updated_at: string;
};

export type ProviderModelList = {
    provider_id: string;
    provider_type: string;
    models: Array<Record<string, unknown>>;
};

export type ModelCapability = {
    id: string;
    provider_type: string;
    model_slug: string;
    display_name: string | null;
    supports_tools: boolean;
    supports_vision: boolean;
    max_context_tokens: number;
    cost_per_1k_input: number;
    cost_per_1k_output: number;
    metadata: Record<string, unknown>;
    is_active: boolean;
    created_at: string;
    updated_at: string;
};

export type ProviderCompareResult = {
    provider_id: string;
    provider_name: string;
    provider_type: string;
    model_name: string;
    latency_ms: number;
    input_tokens: number;
    output_tokens: number;
    token_total: number;
    estimated_cost_usd: number;
    output_text: string;
    is_healthy: boolean;
};

export type ProviderCompareResponse = {
    prompt_preview: string;
    result_a: ProviderCompareResult;
    result_b: ProviderCompareResult;
};

export type GithubConnection = {
    id: string;
    name: string;
    api_url: string;
    connection_mode: string;
    installation_id: number | null;
    organization_login: string | null;
    token_hint: string | null;
    account_login: string | null;
    is_active: boolean;
    metadata: Record<string, unknown>;
    created_at: string;
    updated_at: string;
};

export type GithubRepository = {
    id: string;
    connection_id: string;
    project_id: string | null;
    owner_name: string;
    repo_name: string;
    full_name: string;
    default_branch: string | null;
    repo_url: string | null;
    is_active: boolean;
    metadata: Record<string, unknown>;
    last_synced_at: string | null;
    created_at: string;
};

export type GithubIssueLink = {
    id: string;
    repository_id: string;
    task_id: string | null;
    issue_number: number;
    title: string;
    body: string | null;
    state: string;
    labels: string[];
    assignee_login: string | null;
    issue_url: string | null;
    sync_status: string;
    last_comment_posted_at: string | null;
    last_synced_at: string | null;
    last_error: string | null;
    metadata: Record<string, unknown>;
    created_at: string;
    updated_at: string;
};

export type GithubSyncEvent = {
    id: string;
    repository_id: string | null;
    issue_link_id: string | null;
    action: string;
    status: string;
    detail: string | null;
    payload: Record<string, unknown>;
    created_at: string;
};

export type ProjectRepositoryLink = {
    id: string;
    github_repository_id: string | null;
    provider: string;
    owner_name: string;
    repo_name: string;
    full_name: string;
    default_branch: string | null;
    repository_url: string | null;
    metadata: Record<string, unknown>;
};

export type ProjectRepositoryIndexStatus = {
    repository_link_id: string;
    github_repository_id: string | null;
    full_name: string;
    default_branch: string | null;
    repository_url: string | null;
    index_settings: Record<string, unknown>;
    indexed_files: number;
    chunk_count: number;
    searchable_documents: number;
    last_indexed_at: string | null;
    latest_job: {
        id: string;
        status: string;
        error_text: string | null;
        created_at: string;
        started_at: string | null;
        finished_at: string | null;
        mode: string;
        path_prefixes: string[];
    } | null;
    last_successful_job_id: string | null;
    pending_jobs: number;
    running_jobs: number;
    recent_files: Array<{
        document_id: string;
        path: string;
        branch: string;
        chunk_count: number;
        status: string;
    }>;
    recent_errors: Array<{
        job_id: string;
        error_text: string | null;
        created_at: string;
        mode: string;
        path_prefixes: string[];
    }>;
};

export type Approval = {
    id: string;
    project_id: string | null;
    task_id: string | null;
    run_id: string | null;
    issue_link_id: string | null;
    requested_by_user_id: string | null;
    approved_by_user_id: string | null;
    approval_type: string;
    status: string;
    reason: string | null;
    payload: Record<string, unknown>;
    created_at: string;
    resolved_at: string | null;
};

export type ProjectDocument = {
    id: string;
    project_id: string;
    task_id: string | null;
    uploaded_by_user_id: string;
    filename: string;
    content_type: string;
    source_text: string;
    object_key: string | null;
    size_bytes: number;
    summary_text: string | null;
    ingestion_status: string;
    chunk_count: number;
    ttl_days: number | null;
    expires_at: string | null;
    deleted_at: string | null;
    metadata: Record<string, unknown>;
    created_at: string;
    updated_at: string;
};

export type KnowledgeSearchResult = {
    hit_kind?: "chunk" | "decision";
    document_id: string;
    chunk_id: string;
    filename: string;
    chunk_index: number;
    score: number;
    content: string;
    metadata: Record<string, unknown>;
    decision_id?: string | null;
};

export type AgentMemoryEntry = {
    id: string;
    owner_id: string;
    agent_id: string;
    project_id: string | null;
    source_run_id: string | null;
    key: string;
    value_text: string;
    scope: string;
    status: string;
    approved_by_user_id: string | null;
    ttl_days: number | null;
    expires_at: string | null;
    deleted_at: string | null;
    metadata: Record<string, unknown>;
    created_at: string;
    updated_at: string;
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

export type OrchestrationOverview = {
    projects: OrchestrationProject[];
    agents: Agent[];
    active_runs: TaskRun[];
    pending_approvals: Approval[];
    github_events: GithubSyncEvent[];
};

export async function getOrchestrationOverview(): Promise<OrchestrationOverview> {
    return apiFetch("/orchestration/overview");
}

export async function listAgents(projectId?: string): Promise<Agent[]> {
    const suffix = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
    return apiFetch(`/orchestration/agents${suffix}`);
}

export async function createAgent(payload: Record<string, unknown>): Promise<Agent> {
    return apiFetch("/orchestration/agents", { method: "POST", body: JSON.stringify(payload) });
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

export async function updateAgent(agentId: string, payload: Record<string, unknown>): Promise<Agent> {
    return apiFetch(`/orchestration/agents/${agentId}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export async function duplicateAgent(agentId: string): Promise<Agent> {
    return apiFetch(`/orchestration/agents/${agentId}/duplicate`, { method: "POST" });
}

export async function activateAgent(agentId: string, active: boolean): Promise<Agent> {
    return apiFetch(`/orchestration/agents/${agentId}/${active ? "activate" : "deactivate"}`, { method: "POST" });
}

export async function listOrchestrationProjects(): Promise<OrchestrationProject[]> {
    return apiFetch("/orchestration/projects");
}

export async function createOrchestrationProject(payload: Record<string, unknown>): Promise<OrchestrationProject> {
    return apiFetch("/orchestration/projects", { method: "POST", body: JSON.stringify(payload) });
}

export async function getOrchestrationProject(projectId: string): Promise<OrchestrationProject> {
    return apiFetch(`/orchestration/projects/${projectId}`);
}

export async function updateOrchestrationProject(projectId: string, payload: Record<string, unknown>): Promise<OrchestrationProject> {
    return apiFetch(`/orchestration/projects/${projectId}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export async function listProjectAgents(projectId: string): Promise<ProjectAgentMembership[]> {
    return apiFetch(`/orchestration/projects/${projectId}/agents`);
}

export async function addProjectAgent(projectId: string, payload: Record<string, unknown>): Promise<ProjectAgentMembership> {
    return apiFetch(`/orchestration/projects/${projectId}/agents`, { method: "POST", body: JSON.stringify(payload) });
}

export async function updateProjectAgent(projectId: string, membershipId: string, payload: Record<string, unknown>): Promise<ProjectAgentMembership> {
    return apiFetch(`/orchestration/projects/${projectId}/agents/${membershipId}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export async function listOrchestrationTasks(projectId: string): Promise<OrchestrationTask[]> {
    return apiFetch(`/orchestration/projects/${projectId}/tasks`);
}

export async function createOrchestrationTask(projectId: string, payload: Record<string, unknown>): Promise<OrchestrationTask> {
    return apiFetch(`/orchestration/projects/${projectId}/tasks`, { method: "POST", body: JSON.stringify(payload) });
}

export async function updateOrchestrationTask(projectId: string, taskId: string, payload: Record<string, unknown>): Promise<OrchestrationTask> {
    return apiFetch(`/orchestration/projects/${projectId}/tasks/${taskId}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export async function deleteOrchestrationTask(projectId: string, taskId: string): Promise<void> {
    await apiFetch(`/orchestration/projects/${projectId}/tasks/${taskId}`, { method: "DELETE" });
}

export async function startTaskRun(projectId: string, taskId: string, payload: Record<string, unknown>): Promise<TaskRun> {
    return apiFetch(`/orchestration/projects/${projectId}/tasks/${taskId}/runs`, { method: "POST", body: JSON.stringify(payload) });
}

export async function listDagReadyTasks(projectId: string): Promise<DagReadyTask[]> {
    return apiFetch(`/orchestration/projects/${projectId}/dag/ready-tasks`);
}

export async function startDagParallelReady(
    projectId: string,
    payload: { run_mode?: string; limit?: number; task_ids?: string[]; input_payload?: Record<string, unknown> },
): Promise<DagParallelStartResult> {
    return apiFetch(`/orchestration/projects/${projectId}/dag/start-ready`, {
        method: "POST",
        body: JSON.stringify({
            run_mode: payload.run_mode ?? "single_agent",
            limit: payload.limit ?? 8,
            task_ids: payload.task_ids,
            input_payload: payload.input_payload ?? {},
        }),
    });
}

export async function getMergeResolutionPreview(projectId: string, parentTaskId: string): Promise<Record<string, unknown>> {
    return apiFetch(`/orchestration/projects/${projectId}/tasks/${parentTaskId}/merge-preview`);
}

export async function startMergeResolutionRun(
    projectId: string,
    parentTaskId: string,
    body?: { run_mode?: string; model_name?: string | null; notes?: string | null; input_payload?: Record<string, unknown> },
): Promise<TaskRun> {
    return apiFetch(`/orchestration/projects/${projectId}/tasks/${parentTaskId}/merge-resolve-run`, {
        method: "POST",
        body: JSON.stringify(body ?? {}),
    });
}

export async function listRuns(projectId?: string): Promise<TaskRun[]> {
    const suffix = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
    return apiFetch(`/orchestration/runs${suffix}`);
}

export async function getRun(runId: string): Promise<TaskRun> {
    return apiFetch(`/orchestration/runs/${runId}`);
}

export type RunCostSummary = {
    run_id: string;
    project_id: string;
    status: string;
    estimated_cost_usd: number;
    event_cost_sum_usd: number;
    token_input: number;
    token_output: number;
    token_total: number;
    model_name: string | null;
};

export async function getRunCostSummary(runId: string): Promise<RunCostSummary> {
    return apiFetch(`/orchestration/runs/${runId}/cost`);
}

export async function listRunEvents(runId: string): Promise<RunEvent[]> {
    return apiFetch(`/orchestration/runs/${runId}/events`);
}

export async function getTaskExecutionState(
    projectId: string,
    taskId: string
): Promise<TaskExecutionSnapshot> {
    return apiFetch(
        `/orchestration/projects/${projectId}/tasks/${taskId}/execution-state`
    );
}

export async function getRunExecutionState(runId: string): Promise<RunExecutionSnapshot> {
    return apiFetch(`/orchestration/runs/${runId}/execution-state`);
}

export type WorkingMemory = {
    schema_version: string;
    objective: string;
    accepted_plan: string;
    latest_findings: string;
    temp_notes: string;
    open_questions: string;
    discussion_summary: string;
    artifact_refs: string[];
    updated_at: string;
};

export async function getRunWorkingMemory(runId: string): Promise<WorkingMemory> {
    return apiFetch(`/orchestration/runs/${runId}/working-memory`);
}

export async function patchRunWorkingMemory(
    runId: string,
    patch: Partial<
        Pick<
            WorkingMemory,
            | "objective"
            | "accepted_plan"
            | "latest_findings"
            | "temp_notes"
            | "open_questions"
            | "discussion_summary"
            | "artifact_refs"
        >
    >
): Promise<WorkingMemory> {
    return apiFetch(`/orchestration/runs/${runId}/working-memory`, {
        method: "PATCH",
        body: JSON.stringify(patch),
    });
}

export type SemanticMemoryEntry = {
    id: string;
    owner_id: string;
    scope: string;
    project_id: string | null;
    agent_id: string | null;
    entry_type: string;
    namespace: string;
    title: string;
    body: string;
    metadata: Record<string, unknown>;
    source_chunk_id: string | null;
    source_task_id: string | null;
    source_run_id: string | null;
    provenance: Record<string, unknown>;
    created_by_user_id: string | null;
    created_at: string;
    updated_at: string;
};

export type ProjectMemorySettings = {
    auto_promote_decisions: boolean;
    auto_promote_approved_agent_memory: boolean;
    auto_ingest_bypasses_semantic_approval: boolean;
    second_stage_rag: boolean;
    semantic_write_requires_approval: boolean;
    episodic_retrieval_depth: number;
    episodic_retention_days: number;
    episodic_archive_enabled: boolean;
    episodic_delete_index_after_archive: boolean;
    task_close_auto_promote_working_memory: boolean;
    enable_semantic_vector_search: boolean;
    enable_episodic_vector_search: boolean;
    deep_recall_mode: boolean;
    deep_recall_episodic_candidates: number;
    classifier_worker_enabled: boolean;
};

/** Returned when semantic writes require human approval (HTTP 202). */
export type PendingSemanticWriteResponse = {
    pending: true;
    approval_id: string;
    approval_type: string;
};

export function isPendingSemanticWrite(
    r: unknown
): r is PendingSemanticWriteResponse {
    return (
        typeof r === "object" &&
        r !== null &&
        "pending" in r &&
        (r as PendingSemanticWriteResponse).pending === true &&
        typeof (r as PendingSemanticWriteResponse).approval_id === "string"
    );
}

export async function getProjectMemorySettings(projectId: string): Promise<ProjectMemorySettings> {
    return apiFetch(`/orchestration/projects/${projectId}/memory-settings`);
}

export async function patchProjectMemorySettings(
    projectId: string,
    patch: Partial<ProjectMemorySettings>
): Promise<ProjectMemorySettings> {
    return apiFetch(`/orchestration/projects/${projectId}/memory-settings`, {
        method: "PATCH",
        body: JSON.stringify(patch),
    });
}

export async function listSemanticMemory(
    projectId: string,
    params?: {
        q?: string;
        vec_q?: string;
        entry_type?: string;
        namespace_prefix?: string;
        limit?: number;
    }
): Promise<SemanticMemoryEntry[]> {
    const sp = new URLSearchParams();
    if (params?.q) sp.set("q", params.q);
    if (params?.vec_q) sp.set("vec_q", params.vec_q);
    if (params?.entry_type) sp.set("entry_type", params.entry_type);
    if (params?.namespace_prefix) sp.set("namespace_prefix", params.namespace_prefix);
    if (params?.limit != null) sp.set("limit", String(params.limit));
    const qs = sp.toString();
    return apiFetch(
        `/orchestration/projects/${projectId}/semantic-memory${qs ? `?${qs}` : ""}`
    );
}

export async function createSemanticMemory(
    projectId: string,
    body: {
        entry_type: string;
        title: string;
        body: string;
        scope?: string;
        namespace?: string | null;
        metadata?: Record<string, unknown>;
    }
): Promise<SemanticMemoryEntry | PendingSemanticWriteResponse> {
    return apiFetch(`/orchestration/projects/${projectId}/semantic-memory`, {
        method: "POST",
        body: JSON.stringify(body),
    });
}

export async function promoteWorkingMemoryToSemantic(
    projectId: string,
    payload: { run_id: string; entry_type?: string; title?: string | null }
): Promise<SemanticMemoryEntry> {
    return apiFetch(
        `/orchestration/projects/${projectId}/semantic-memory/promote-from-working-memory`,
        { method: "POST", body: JSON.stringify(payload) }
    );
}

export async function deleteSemanticMemory(
    projectId: string,
    entryId: string
): Promise<void | PendingSemanticWriteResponse> {
    return apiFetch(`/orchestration/projects/${projectId}/semantic-memory/${entryId}`, {
        method: "DELETE",
    });
}

export type SemanticConflictGroup = {
    group_key: string;
    entries: Array<{
        id: string;
        title: string | null;
        namespace: string;
        updated_at: string;
    }>;
};

export async function listSemanticMemoryConflicts(
    projectId: string
): Promise<SemanticConflictGroup[]> {
    return apiFetch(`/orchestration/projects/${projectId}/semantic-memory/conflicts`);
}

export async function mergeSemanticMemoryEntries(
    projectId: string,
    body: {
        canonical_entry_id: string;
        merge_entry_ids: string[];
        link_relation?: string;
    }
): Promise<SemanticMemoryEntry> {
    return apiFetch(`/orchestration/projects/${projectId}/semantic-memory/merge`, {
        method: "POST",
        body: JSON.stringify(body),
    });
}

export type EpisodicSearchResponse = { hits: Array<Record<string, unknown>> };

export async function searchEpisodicMemory(
    projectId: string,
    params?: {
        q?: string;
        vec_q?: string;
        limit?: number;
        since?: string;
        until?: string;
        task_id?: string;
        kinds?: string;
    }
): Promise<EpisodicSearchResponse> {
    const sp = new URLSearchParams();
    if (params?.q) sp.set("q", params.q);
    if (params?.vec_q) sp.set("vec_q", params.vec_q);
    if (params?.limit != null) sp.set("limit", String(params.limit));
    if (params?.since) sp.set("since", params.since);
    if (params?.until) sp.set("until", params.until);
    if (params?.task_id) sp.set("task_id", params.task_id);
    if (params?.kinds) sp.set("kinds", params.kinds);
    const qs = sp.toString();
    return apiFetch(
        `/orchestration/projects/${projectId}/episodic-memory/search${qs ? `?${qs}` : ""}`
    );
}

export type EpisodicArchiveManifest = {
    id: string;
    object_key: string;
    period_start: string;
    period_end: string;
    record_count: number;
    byte_size: number;
    stats_json: Record<string, unknown>;
    created_at: string;
};

export async function listEpisodicArchives(projectId: string): Promise<EpisodicArchiveManifest[]> {
    return apiFetch(`/orchestration/projects/${projectId}/episodic-memory/archives`);
}

export async function reindexEpisodicMemory(
    projectId: string,
    limit: number = 200
): Promise<{ indexed: number }> {
    return apiFetch(
        `/orchestration/projects/${projectId}/episodic-memory/reindex?limit=${encodeURIComponent(String(limit))}`,
        { method: "POST" }
    );
}

export async function retryRun(runId: string): Promise<TaskRun> {
    return apiFetch(`/orchestration/runs/${runId}/retry`, { method: "POST" });
}

export async function cancelRun(runId: string): Promise<TaskRun> {
    return apiFetch(`/orchestration/runs/${runId}/cancel`, { method: "POST" });
}

export async function resumeRun(runId: string): Promise<TaskRun> {
    return apiFetch(`/orchestration/runs/${runId}/resume`, { method: "POST" });
}

export async function replayRun(
    runId: string,
    payload: { from_event_index?: number; model_name?: string } = {},
): Promise<TaskRun> {
    return apiFetch(`/orchestration/runs/${runId}/replay`, {
        method: "POST",
        body: JSON.stringify({
            from_event_index: payload.from_event_index ?? 0,
            model_name: payload.model_name ?? null,
        }),
    });
}

// ── Cost analytics ───────────────────────────────────────────

export type CostAggregation = {
    period: string;
    by_project: Array<{ name: string; cost_usd: number; tokens: number; runs: number }>;
    by_agent: Array<{ name: string; cost_usd: number; tokens: number; runs: number }>;
    by_provider: Array<{ name: string; cost_usd: number; tokens: number; runs: number }>;
    most_expensive_runs: Array<{ id: string; model_name: string | null; cost_usd: number; tokens: number; status: string; created_at: string }>;
    total_cost_usd: number;
    total_tokens: number;
};

export async function getCostAnalytics(days: number = 30): Promise<CostAggregation> {
    return apiFetch(`/orchestration/analytics/cost?days=${days}`);
}

export type PortfolioProjectSummary = {
    project_id: string;
    name: string;
    slug: string;
    active_runs: number;
    open_tasks: number;
    repository_links: number;
};

export type PortfolioProjectControlPlane = {
    project_id: string;
    name: string;
    slug: string;
    manager: Record<string, unknown>;
    health: Record<string, unknown>;
    queue_depth: Record<string, number>;
    cost_rollup: Record<string, unknown>;
    blocked_work: Array<Record<string, unknown>>;
    escalation_inbox: Array<Record<string, unknown>>;
    latest_run: Record<string, unknown> | null;
    execution_policy: Record<string, unknown>;
};

export type PortfolioExecutionPolicy = {
    routing_mode: string;
    approval_policy: string;
    repo_indexing_cadence: string;
    cost_cap_usd: number;
};

export type OperatorHealthCard = {
    key: string;
    label: string;
    status: string;
    summary: string;
    metrics: Record<string, unknown>;
};

export type OperatorDashboard = {
    generated_at: string;
    queue_health: Record<string, unknown>;
    webhook_lag: Record<string, unknown>;
    replay_backlog: Record<string, unknown>;
    stuck_runs: Record<string, unknown>;
    services: OperatorHealthCard[];
};

export type PortfolioControlPlane = {
    generated_at: string;
    totals: Record<string, unknown>;
    execution_policy: PortfolioExecutionPolicy;
    operator_dashboard: OperatorDashboard;
    projects: PortfolioProjectControlPlane[];
};

export type ExecutionInsights = {
    since: string;
    days: number;
    by_event_type: Array<{ event_type: string; count: number }>;
    tool_failures_by_tool: Array<{ tool: string; count: number }>;
    reopen_events: number;
    brainstorm_round_summary_events: number;
    blocked_events: number;
    tool_call_failed_events: number;
};

export type TaskTimelineEntry = {
    kind: "comment" | "github_sync";
    id: string;
    created_at: string;
    title: string;
    body: string | null;
    detail: string | null;
    payload: Record<string, unknown>;
};

export type WorkflowTemplate = {
    id: string;
    name: string;
    description: string;
    suggested_execution: Record<string, unknown>;
};

export type RuntimeInfo = {
    orchestration_offline_mode: boolean;
    orchestration_provider_failover: boolean;
    orchestration_use_langgraph: boolean;
    orchestration_durable_queue_backend: string;
    durable_signal_model: string;
    durable_query_model: string;
    /** Logical service plane → broker queue name */
    celery_queues: Record<string, string>;
};

export type BrainstormDiscourseInsights = {
    message_count: number;
    same_agent_streak_ratio: number;
    top_repeated_terms: string[];
    rounds_with_messages: number;
    last_round_repetition_score: number | null;
    last_round_pairwise_min_similarity: number | null;
    consensus_kind: string | null;
    conflict_signal: boolean | null;
};

export async function getOrchestrationPortfolio(): Promise<PortfolioProjectSummary[]> {
    return apiFetch("/orchestration/portfolio");
}

export async function getOrchestrationPortfolioControlPlane(): Promise<PortfolioControlPlane> {
    return apiFetch("/orchestration/portfolio/control-plane");
}

export async function getPortfolioExecutionPolicy(): Promise<PortfolioExecutionPolicy> {
    return apiFetch("/orchestration/portfolio/execution-policy");
}

export async function updatePortfolioExecutionPolicy(
    payload: Partial<PortfolioExecutionPolicy>
): Promise<PortfolioExecutionPolicy> {
    return apiFetch("/orchestration/portfolio/execution-policy", {
        method: "PUT",
        body: JSON.stringify(payload),
    });
}

export async function getExecutionInsights(days: number = 7): Promise<ExecutionInsights> {
    return apiFetch(`/orchestration/analytics/execution-insights?days=${days}`);
}

export async function getTaskTimeline(projectId: string, taskId: string): Promise<TaskTimelineEntry[]> {
    return apiFetch(`/orchestration/projects/${projectId}/tasks/${taskId}/timeline`);
}

export async function listWorkflowTemplates(): Promise<WorkflowTemplate[]> {
    return apiFetch("/orchestration/workflow-templates");
}

export async function getOrchestrationRuntimeInfo(): Promise<RuntimeInfo> {
    return apiFetch("/orchestration/runtime-info");
}

export async function getRunDurableWorkflow(runId: string): Promise<DurableWorkflowState> {
    return apiFetch(`/orchestration/runs/${runId}/durable-workflow`);
}

export async function signalRunWorkflow(
    runId: string,
    payload: { signal_name: string; payload?: Record<string, unknown> }
): Promise<DurableWorkflowState> {
    return apiFetch(`/orchestration/runs/${runId}/signals`, {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

export async function getBrainstormDiscourseInsights(brainstormId: string): Promise<BrainstormDiscourseInsights> {
    return apiFetch(`/orchestration/brainstorms/${brainstormId}/discourse-insights`);
}

// ── Eval records ─────────────────────────────────────────────

export type EvalRecord = {
    id: string;
    project_id: string;
    task_id: string | null;
    name: string;
    run_a_id: string | null;
    run_b_id: string | null;
    agent_a_id: string | null;
    agent_b_id: string | null;
    model_a: string | null;
    model_b: string | null;
    winner: string | null;
    score_a: number | null;
    score_b: number | null;
    criteria_met_a: boolean | null;
    criteria_met_b: boolean | null;
    notes: string | null;
    metadata_json: Record<string, unknown>;
    created_at: string;
    updated_at: string;
};

export type EvalLeaderboardEntry = {
    agent_id: string;
    agent_name: string;
    wins: number;
    losses: number;
    ties: number;
    total: number;
    win_rate: number;
    avg_score: number;
    avg_cost_usd: number;
    avg_latency_ms: number;
};

export async function listEvalRecords(projectId: string): Promise<EvalRecord[]> {
    return apiFetch(`/orchestration/projects/${projectId}/evals`);
}

export async function createEvalRecord(projectId: string, payload: Record<string, unknown>): Promise<EvalRecord> {
    return apiFetch(`/orchestration/projects/${projectId}/evals`, { method: "POST", body: JSON.stringify(payload) });
}

export async function updateEvalRecord(projectId: string, evalId: string, payload: Record<string, unknown>): Promise<EvalRecord> {
    return apiFetch(`/orchestration/projects/${projectId}/evals/${evalId}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export async function startBenchmark(projectId: string, evalId: string): Promise<{ eval_id: string; runs: Array<{ side: string; run_id: string }> }> {
    return apiFetch(`/orchestration/projects/${projectId}/evals/${evalId}/start`, { method: "POST" });
}

export async function scoreEvalRecord(projectId: string, evalId: string): Promise<EvalRecord> {
    return apiFetch(`/orchestration/projects/${projectId}/evals/${evalId}/score`, { method: "POST" });
}

export async function getEvalLeaderboard(projectId: string): Promise<EvalLeaderboardEntry[]> {
    return apiFetch(`/orchestration/projects/${projectId}/evals/leaderboard`);
}

export async function startHistoricalBenchmarks(
    projectId: string,
    payload: {
        agent_a_id: string;
        agent_b_id: string;
        model_a?: string;
        model_b?: string;
        days?: number;
        limit?: number;
    },
): Promise<{ count: number; created: Array<{ eval_id: string; task_id: string; runs: Array<{ side: string; run_id: string }> }> }> {
    const params = new URLSearchParams({
        agent_a_id: payload.agent_a_id,
        agent_b_id: payload.agent_b_id,
        days: String(payload.days ?? 60),
        limit: String(payload.limit ?? 8),
    });
    if (payload.model_a) params.set("model_a", payload.model_a);
    if (payload.model_b) params.set("model_b", payload.model_b);
    return apiFetch(`/orchestration/projects/${projectId}/evals/benchmark-historical?${params.toString()}`, {
        method: "POST",
    });
}

export async function listBrainstorms(projectId?: string): Promise<Brainstorm[]> {
    const suffix = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
    return apiFetch(`/orchestration/brainstorms${suffix}`);
}

export async function createBrainstorm(payload: Record<string, unknown>): Promise<Brainstorm> {
    return apiFetch("/orchestration/brainstorms", { method: "POST", body: JSON.stringify(payload) });
}

export async function getBrainstorm(brainstormId: string): Promise<Brainstorm> {
    return apiFetch(`/orchestration/brainstorms/${brainstormId}`);
}

export async function listBrainstormParticipants(brainstormId: string): Promise<BrainstormParticipant[]> {
    return apiFetch(`/orchestration/brainstorms/${brainstormId}/participants`);
}

export async function listBrainstormMessages(brainstormId: string): Promise<BrainstormMessage[]> {
    return apiFetch(`/orchestration/brainstorms/${brainstormId}/messages`);
}

export async function startBrainstorm(brainstormId: string): Promise<TaskRun> {
    return apiFetch(`/orchestration/brainstorms/${brainstormId}/start`, { method: "POST" });
}

export async function startBrainstormNextRound(brainstormId: string): Promise<TaskRun> {
    return apiFetch(`/orchestration/brainstorms/${brainstormId}/next-round`, { method: "POST" });
}

export async function forceBrainstormSummary(brainstormId: string): Promise<Brainstorm> {
    return apiFetch(`/orchestration/brainstorms/${brainstormId}/force-summary`, { method: "POST" });
}

export async function promoteBrainstorm(brainstormId: string): Promise<OrchestrationTask[]> {
    return apiFetch(`/orchestration/brainstorms/${brainstormId}/promote`, { method: "POST" });
}

export async function promoteBrainstormAdr(brainstormId: string): Promise<ProjectDecision> {
    return apiFetch(`/orchestration/brainstorms/${brainstormId}/promote-adr`, { method: "POST" });
}

export async function promoteBrainstormDocument(brainstormId: string): Promise<ProjectDocument> {
    return apiFetch(`/orchestration/brainstorms/${brainstormId}/promote-document`, { method: "POST" });
}

export async function listProviders(projectId?: string): Promise<ProviderConfig[]> {
    const suffix = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
    return apiFetch(`/orchestration/providers${suffix}`);
}

export async function createProvider(payload: Record<string, unknown>): Promise<ProviderConfig> {
    return apiFetch("/orchestration/providers", { method: "POST", body: JSON.stringify(payload) });
}

export async function updateProvider(providerId: string, payload: Record<string, unknown>): Promise<ProviderConfig> {
    return apiFetch(`/orchestration/providers/${providerId}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export async function testProvider(providerId: string): Promise<Record<string, unknown>> {
    return apiFetch(`/orchestration/providers/${providerId}/test`, { method: "POST" });
}

export async function listProviderModels(providerId: string): Promise<ProviderModelList> {
    return apiFetch(`/orchestration/providers/${providerId}/models`);
}

export async function listModelCapabilities(): Promise<ModelCapability[]> {
    return apiFetch("/orchestration/providers/model-capabilities");
}

export async function compareProviders(payload: Record<string, unknown>): Promise<ProviderCompareResponse> {
    return apiFetch("/orchestration/providers/compare", {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

export async function listGithubConnections(): Promise<GithubConnection[]> {
    return apiFetch("/orchestration/github/connections");
}

export async function getGithubAppInstallUrl(): Promise<{ install_url: string }> {
    return apiFetch("/orchestration/github/app/install-url");
}

export async function createGithubConnection(payload: Record<string, unknown>): Promise<GithubConnection> {
    return apiFetch("/orchestration/github/connections", { method: "POST", body: JSON.stringify(payload) });
}

export async function deleteGithubConnection(connectionId: string): Promise<void> {
    return apiFetch(`/orchestration/github/connections/${connectionId}`, { method: "DELETE" });
}

export async function syncGithubRepositories(connectionId: string): Promise<GithubRepository[]> {
    return apiFetch(`/orchestration/github/connections/${connectionId}/sync-repos`, { method: "POST" });
}

export async function listGithubRepositories(): Promise<GithubRepository[]> {
    return apiFetch("/orchestration/github/repositories");
}

export async function importGithubIssues(payload: Record<string, unknown>): Promise<OrchestrationTask[]> {
    return apiFetch("/orchestration/github/import-issues", { method: "POST", body: JSON.stringify(payload) });
}

export async function listGithubIssueLinks(projectId?: string): Promise<GithubIssueLink[]> {
    const suffix = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
    return apiFetch(`/orchestration/github/issues${suffix}`);
}

export async function refreshGithubIssueLink(issueLinkId: string): Promise<GithubIssueLink> {
    return apiFetch(`/orchestration/github/issues/${issueLinkId}/refresh`, { method: "POST" });
}

export async function listGithubSyncEvents(projectId?: string): Promise<GithubSyncEvent[]> {
    const suffix = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
    return apiFetch(`/orchestration/github/sync-events${suffix}`);
}

export async function replayGithubSyncEvent(
    syncEventId: string,
    payload?: { force?: boolean }
): Promise<GithubSyncEvent> {
    return apiFetch(`/orchestration/github/sync-events/${syncEventId}/replay`, {
        method: "POST",
        body: JSON.stringify(payload ?? {}),
    });
}

export async function requestGithubComment(issueLinkId: string, payload: { body: string; close_issue: boolean }): Promise<Approval> {
    return apiFetch(`/orchestration/github/issues/${issueLinkId}/comment`, { method: "POST", body: JSON.stringify(payload) });
}

export async function listApprovals(): Promise<Approval[]> {
    return apiFetch("/orchestration/approvals");
}

export async function decideApproval(approvalId: string, payload: { status: "approved" | "rejected"; reason?: string }): Promise<Approval> {
    return apiFetch(`/orchestration/approvals/${approvalId}`, { method: "POST", body: JSON.stringify(payload) });
}

export async function getPendingApprovalsCount(): Promise<{ count: number }> {
    return apiFetch("/orchestration/approvals/pending-count");
}

export async function uploadProjectDocument(projectId: string, file: File, taskId?: string, ttlDays?: number): Promise<ProjectDocument> {
    const formData = new FormData();
    formData.append("file", file);
    if (taskId) formData.append("task_id", taskId);
    if (typeof ttlDays === "number") formData.append("ttl_days", String(ttlDays));
    return apiFetch(`/orchestration/projects/${projectId}/documents`, { method: "POST", body: formData });
}

export async function listProjectDocuments(projectId: string, taskId?: string): Promise<ProjectDocument[]> {
    const suffix = taskId ? `?task_id=${encodeURIComponent(taskId)}` : "";
    return apiFetch(`/orchestration/projects/${projectId}/documents${suffix}`);
}

export async function deleteProjectDocument(projectId: string, documentId: string): Promise<void> {
    return apiFetch(`/orchestration/projects/${projectId}/documents/${documentId}`, { method: "DELETE" });
}

export async function searchProjectKnowledge(
    projectId: string,
    query: string,
    taskId?: string,
    options?: { includeDecisions?: boolean },
): Promise<KnowledgeSearchResult[]> {
    const params = new URLSearchParams({ q: query });
    if (taskId) params.set("task_id", taskId);
    if (options?.includeDecisions) params.set("include_decisions", "true");
    return apiFetch(`/orchestration/projects/${projectId}/knowledge?${params.toString()}`);
}

export async function listProjectMemory(projectId: string, options?: { agentId?: string; status?: string }): Promise<AgentMemoryEntry[]> {
    const params = new URLSearchParams();
    if (options?.agentId) params.set("agent_id", options.agentId);
    if (options?.status) params.set("status", options.status);
    const suffix = params.toString() ? `?${params.toString()}` : "";
    return apiFetch(`/orchestration/projects/${projectId}/memory${suffix}`);
}

export async function deleteProjectMemoryEntry(projectId: string, memoryId: string): Promise<void> {
    return apiFetch(`/orchestration/projects/${projectId}/memory/${memoryId}`, { method: "DELETE" });
}

export async function indexProjectRepository(projectId: string, repositoryLinkId: string): Promise<Record<string, unknown>> {
    return apiFetch(`/orchestration/projects/${projectId}/repositories/${repositoryLinkId}/index`, { method: "POST" });
}

export async function queueProjectRepositoryIndex(
    projectId: string,
    repositoryLinkId: string,
    payload?: {
        mode?: "full" | "incremental";
        path_prefixes?: string[];
        schedule_label?: string | null;
        auto_enabled?: boolean | null;
    }
): Promise<Record<string, unknown>> {
    return apiFetch(`/orchestration/projects/${projectId}/repositories/${repositoryLinkId}/index`, {
        method: "POST",
        body: JSON.stringify(payload ?? {}),
    });
}

export async function listProjectRepositories(projectId: string): Promise<ProjectRepositoryLink[]> {
    return apiFetch(`/orchestration/projects/${projectId}/repositories`);
}

export async function updateProjectRepository(
    projectId: string,
    repositoryLinkId: string,
    payload: { default_branch?: string | null; metadata?: Record<string, unknown> }
): Promise<ProjectRepositoryLink> {
    return apiFetch(`/orchestration/projects/${projectId}/repositories/${repositoryLinkId}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
    });
}

export async function getProjectRepositoryIndexStatus(projectId: string): Promise<ProjectRepositoryIndexStatus[]> {
    return apiFetch(`/orchestration/projects/${projectId}/repositories/index-status`);
}

export type MemoryIngestJob = {
    id: string;
    project_id: string | null;
    job_type: string;
    status: "pending" | "running" | "completed" | "failed" | string;
    error_text: string | null;
    created_at: string;
    started_at: string | null;
    finished_at: string | null;
    payload: Record<string, unknown>;
};

export async function listProjectMemoryIngestJobs(
    projectId: string,
    limit: number = 60
): Promise<MemoryIngestJob[]> {
    const safe = Math.max(1, Math.min(limit, 300));
    return apiFetch(`/orchestration/projects/${projectId}/memory-ingest-jobs?limit=${safe}`);
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
    budget: Record<string, unknown>;
    memory_policy: Record<string, unknown>;
    output_schema: Record<string, unknown>;
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
    slug: string,
    payload: Partial<Omit<AgentTemplate, "id">>,
): Promise<AgentTemplate> {
    return apiFetch(`/orchestration/agents/templates/${encodeURIComponent(slug)}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
    });
}

export async function deleteAgentTemplate(slug: string): Promise<void> {
    return apiFetch(`/orchestration/agents/templates/${encodeURIComponent(slug)}`, {
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

export async function simulateAgent(
    agentId: string,
    payload: { scenarios?: Array<Record<string, unknown>> } = {},
): Promise<Record<string, unknown>> {
    return apiFetch(`/orchestration/agents/${agentId}/simulate`, {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

export async function bootstrapProjectFromText(prompt: string): Promise<Record<string, unknown>> {
    return apiFetch("/orchestration/projects/bootstrap-from-text", {
        method: "POST",
        body: JSON.stringify({ prompt }),
    });
}

export async function applyBootstrappedProject(payload: Record<string, unknown>): Promise<OrchestrationProject> {
    return apiFetch("/orchestration/projects/bootstrap-apply", {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

export async function getRunExplanation(runId: string): Promise<Record<string, unknown>> {
    return apiFetch(`/orchestration/runs/${runId}/explanation`);
}

export async function getAgentPerformance(days: number = 30): Promise<Array<Record<string, unknown>>> {
    return apiFetch(`/orchestration/analytics/agent-performance?days=${days}`);
}

export async function getBudgetProjection(days: number = 30): Promise<Record<string, unknown>> {
    return apiFetch(`/orchestration/analytics/budget-projection?days=${days}`);
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

export type ProjectMilestone = {
    id: string;
    project_id: string;
    title: string;
    description: string | null;
    due_date: string | null;
    status: string;
    position: number;
    created_at: string;
    updated_at: string;
};

export async function listProjectMilestones(projectId: string): Promise<ProjectMilestone[]> {
    return apiFetch(`/orchestration/projects/${projectId}/milestones`);
}

export async function createProjectMilestone(projectId: string, payload: Record<string, unknown>): Promise<ProjectMilestone> {
    return apiFetch(`/orchestration/projects/${projectId}/milestones`, { method: "POST", body: JSON.stringify(payload) });
}

export async function updateProjectMilestone(projectId: string, milestoneId: string, payload: Record<string, unknown>): Promise<ProjectMilestone> {
    return apiFetch(`/orchestration/projects/${projectId}/milestones/${milestoneId}`, { method: "PATCH", body: JSON.stringify(payload) });
}

// ── Decisions ───────────────────────────────────────────────

export type ProjectDecision = {
    id: string;
    project_id: string;
    task_id: string | null;
    brainstorm_id: string | null;
    title: string;
    decision: string;
    rationale: string | null;
    author_label: string | null;
    created_at: string;
};

export async function listProjectDecisions(projectId: string): Promise<ProjectDecision[]> {
    return apiFetch(`/orchestration/projects/${projectId}/decisions`);
}

export async function createProjectDecision(projectId: string, payload: Record<string, unknown>): Promise<ProjectDecision> {
    return apiFetch(`/orchestration/projects/${projectId}/decisions`, { method: "POST", body: JSON.stringify(payload) });
}

// ── Task Artifacts ───────────────────────────────────────────

export type TaskArtifact = {
    id: string;
    task_id: string;
    run_id: string | null;
    kind: string;
    title: string;
    content: string | null;
    metadata: Record<string, unknown>;
    created_at: string;
};

export async function listTaskArtifacts(taskId: string): Promise<TaskArtifact[]> {
    return apiFetch(`/orchestration/tasks/${taskId}/artifacts`);
}

export async function createTaskArtifact(taskId: string, payload: Record<string, unknown>): Promise<TaskArtifact> {
    return apiFetch(`/orchestration/tasks/${taskId}/artifacts`, { method: "POST", body: JSON.stringify(payload) });
}

// ── Subtasks ─────────────────────────────────────────────────

export async function decomposeTask(projectId: string, taskId: string, payload?: Record<string, unknown>): Promise<OrchestrationTask[]> {
    return apiFetch(`/orchestration/projects/${projectId}/tasks/${taskId}/decompose`, { method: "POST", body: JSON.stringify(payload ?? {}) });
}

export async function listSubtasks(projectId: string, taskId: string): Promise<OrchestrationTask[]> {
    return apiFetch(`/orchestration/projects/${projectId}/tasks/${taskId}/subtasks`);
}

// ── Acceptance check ─────────────────────────────────────────

export type AcceptanceCheckResult = {
    task_id: string;
    passed: boolean;
    config: Record<string, unknown>;
    checks: Array<{ name: string; passed: boolean; detail: string } & Record<string, unknown>>;
};

export async function checkTaskAcceptance(projectId: string, taskId: string): Promise<AcceptanceCheckResult> {
    return apiFetch(`/orchestration/projects/${projectId}/tasks/${taskId}/check-acceptance`, { method: "POST" });
}


// ── Gate config ──────────────────────────────────────────────

export type GateConfig = {
    autonomy_level: string;
    approval_gates: string[];
};

export async function getGateConfig(projectId: string): Promise<GateConfig> {
    return apiFetch(`/orchestration/projects/${projectId}/gate-config`);
}

export async function updateGateConfig(projectId: string, payload: Partial<GateConfig>): Promise<GateConfig> {
    return apiFetch(`/orchestration/projects/${projectId}/gate-config`, {
        method: "PATCH",
        body: JSON.stringify(payload),
    });
}
