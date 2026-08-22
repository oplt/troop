import { apiFetch } from "../client";
import { appendCursorParams, assertCursorPage, type CursorPage, type CursorToken } from "../pagination";
import type { Approval } from "./approvals";
import type { TaskRun } from "./runs";

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
    company_id: string | null;
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

export type HierarchyEdge = {
    source_agent_id: string;
    target_agent_id: string;
    relationship: "delegates_to" | "reviews" | "escalates_to" | "collaborates_with";
};

export type HierarchyPolicy = {
    manager_agent_id: string | null;
    edges: HierarchyEdge[];
    delegation_rules: Record<string, string[]>;
    brainstorm_rules: Record<string, string[]>;
    reviewer_agent_ids: string[];
    reviewer_chain_mode: string;
    routing_mode: string;
    sibling_load_balance: string;
    default_execution_mode: "single_agent" | "manager_worker" | "debate";
    blocked_handoff: {
        mode: string;
        target_agent_id: string | null;
        fallback_to_manager: boolean;
    };
    final_authority: "human_user";
    validation_errors: string[];
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
    required_tools: string[];
    external_links: Array<Record<string, unknown>>;
    result_summary: string | null;
    result_payload: Record<string, unknown>;
    position: number;
    metadata: Record<string, unknown>;
    dependency_ids: string[];
    created_at: string;
    updated_at: string;
};

export type TaskListItem = {
    id: string;
    project_id: string;
    title: string;
    status: string;
    priority: string;
    task_type: string;
    position: number;
    assigned_agent_id: string | null;
    human_assignee_id: string | null;
    parent_task_id: string | null;
    github_issue_number: number | null;
    github_issue_url: string | null;
    github_repository_full_name: string | null;
    due_date: string | null;
    labels: string[];
    dependency_ids: string[];
    has_result: boolean;
    created_at: string;
    updated_at: string;
};

export type DagReadyTask = {
    id: string;
    title: string;
    status: string;
    dependency_count: number;
};

export type TaskBlockerReport = {
    task_id: string;
    can_start: boolean;
    blockers: Array<Record<string, unknown>>;
    warnings: Array<Record<string, unknown>>;
};

export type DagParallelStartResult = {
    started_run_ids: string[];
    skipped_task_ids: string[];
    messages: string[];
};

export type ProjectLiveSnapshot = {
    project_id: string;
    agent_counts: {
        total: number;
    };
    resource_counts: {
        repositories: number;
        documents: number;
        decisions: number;
        memory_entries: number;
    };
    task_counts: {
        total: number;
        open: number;
        blocked: number;
        review: number;
    };
    run_counts: {
        total: number;
        active: number;
        failed: number;
    };
    approval_counts: {
        pending: number;
    };
    sync_counts: {
        pending: number;
        failed: number;
    };
    ingest_counts: {
        pending: number;
        running: number;
        failed: number;
    };
    latest: {
        task_updated_at: string | null;
        run_created_at: string | null;
        sync_created_at: string | null;
    };
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

export type BrainstormArtifact = {
    artifact_kind: "task_artifact" | "project_document" | "project_decision";
    artifact_id: string;
    output_type: string;
    title: string;
    content: string;
    created_at: string;
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

export type LocalRepoWorkspaceStatus = {
    valid: boolean;
    blocked_reasons: string[];
    workspace: Record<string, unknown>;
    branch: string | null;
    dirty: boolean | null;
    status: string | null;
    remotes: string | null;
    last_commit: string | null;
    diff_bytes: number | null;
    inspected_at: string | null;
};

export type LocalRepoCommandResult = {
    command: string;
    cwd: string;
    exit_code: number;
    stdout: string;
    stderr: string;
    duration_ms: number;
    timed_out: boolean;
};

export type LocalRepoReadFileResult = {
    path: string;
    content: string;
    truncated: boolean;
};

export type LocalRepoWorktree = {
    branch: string;
    path: string;
    base_repo_path: string;
    created_at: string;
};

export type LocalRepoContextPack = {
    repo: Record<string, unknown>;
    issue_text: string;
    acceptance_criteria: string | null;
    tree: string[];
    files: Array<Record<string, unknown>>;
    constraints: Record<string, unknown>;
    created_at: string;
};

export type AgentWorkSession = {
    status: string;
    agent_id: string | null;
    repository_link_id: string | null;
    local_repo: Record<string, unknown>;
    acceptance_criteria: string | null;
    risk_level: string;
    required_tests: string[];
    planning_gate_required: boolean;
    plan_status: string | null;
    plan?: string | null;
    blocker?: string | null;
    summary?: string | null;
    quality_score: Record<string, unknown> | null;
    artifacts: Array<Record<string, unknown>>;
    created_by_user_id: string | null;
    updated_by_user_id: string | null;
    created_at: string | null;
    updated_at: string | null;
};

export type AgentQualityScore = {
    correctness: number;
    test_coverage: number;
    diff_size: number;
    blast_radius: number;
    confidence: number;
    security_risk: number;
    ux_impact: number;
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

export async function listOrchestrationProjects(): Promise<OrchestrationProject[]> {
    return apiFetch("/orchestration/projects");
}

export async function createOrchestrationProject(payload: Record<string, unknown>): Promise<OrchestrationProject> {
    return apiFetch("/orchestration/projects", { method: "POST", body: JSON.stringify(payload) });
}

export async function getOrchestrationProject(projectId: string): Promise<OrchestrationProject> {
    return apiFetch(`/orchestration/projects/${projectId}`);
}

export async function getProjectLiveSnapshot(projectId: string): Promise<ProjectLiveSnapshot> {
    return apiFetch(`/orchestration/projects/${projectId}/live-snapshot`);
}

export async function updateOrchestrationProject(projectId: string, payload: Record<string, unknown>): Promise<OrchestrationProject> {
    return apiFetch(`/orchestration/projects/${projectId}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export async function getHierarchyPolicy(projectId: string): Promise<HierarchyPolicy> {
    return apiFetch(`/orchestration/projects/${projectId}/hierarchy-policy`);
}

export async function updateHierarchyPolicy(projectId: string, payload: Partial<HierarchyPolicy>): Promise<HierarchyPolicy> {
    return apiFetch(`/orchestration/projects/${projectId}/hierarchy-policy`, {
        method: "PUT",
        body: JSON.stringify(payload),
    });
}

export async function deleteOrchestrationProject(projectId: string): Promise<void> {
    return apiFetch(`/orchestration/projects/${projectId}`, { method: "DELETE" });
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

export async function removeProjectAgent(projectId: string, membershipId: string): Promise<void> {
    return apiFetch(`/orchestration/projects/${projectId}/agents/${membershipId}`, { method: "DELETE" });
}

export async function listOrchestrationTasksPage(
    projectId: string,
    options: { limit?: number; cursor?: CursorToken | null } = {},
): Promise<CursorPage<TaskListItem>> {
    const params = new URLSearchParams();
    appendCursorParams(params, options);
    const query = params.toString();
    const payload = await apiFetch<unknown>(
        `/orchestration/projects/${projectId}/tasks${query ? `?${query}` : ""}`,
    );
    return assertCursorPage<TaskListItem>(payload, `/orchestration/projects/${projectId}/tasks`);
}

export async function listOrchestrationTasks(
    projectId: string,
    limit = 100,
): Promise<TaskListItem[]> {
    const page = await listOrchestrationTasksPage(projectId, { limit });
    return page.items;
}

export async function getOrchestrationTask(projectId: string, taskId: string): Promise<OrchestrationTask> {
    return apiFetch(`/orchestration/projects/${projectId}/tasks/${taskId}`);
}

export async function getTaskBlockers(projectId: string, taskId: string): Promise<TaskBlockerReport> {
    return apiFetch(`/orchestration/projects/${projectId}/tasks/${taskId}/blockers`);
}

export async function createOrchestrationTask(projectId: string, payload: Record<string, unknown>): Promise<OrchestrationTask> {
    return apiFetch(`/orchestration/projects/${projectId}/tasks`, { method: "POST", body: JSON.stringify(payload) });
}

export async function updateOrchestrationTask(projectId: string, taskId: string, payload: Record<string, unknown>): Promise<OrchestrationTask> {
    return apiFetch(`/orchestration/projects/${projectId}/tasks/${taskId}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export async function assignOrchestrationTask(
    projectId: string,
    taskId: string,
    assignedAgentId: string | null,
    source: "drag_drop" | "manual" = "drag_drop",
): Promise<OrchestrationTask> {
    return apiFetch(`/orchestration/projects/${projectId}/tasks/${taskId}/assign`, {
        method: "POST",
        body: JSON.stringify({ assigned_agent_id: assignedAgentId, source }),
    });
}

export async function deleteOrchestrationTask(projectId: string, taskId: string): Promise<void> {
    await apiFetch(`/orchestration/projects/${projectId}/tasks/${taskId}`, { method: "DELETE" });
}

export async function startTaskRun(projectId: string, taskId: string, payload: Record<string, unknown>): Promise<TaskRun> {
    return apiFetch(`/orchestration/projects/${projectId}/tasks/${taskId}/runs`, { method: "POST", body: JSON.stringify(payload) });
}

export async function createPlannedTaskRun(taskId: string, payload: Record<string, unknown>): Promise<TaskRun> {
    return apiFetch(`/tasks/${taskId}/runs`, { method: "POST", body: JSON.stringify(payload) });
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

export async function addBrainstormParticipant(
    brainstormId: string,
    payload: Record<string, unknown>,
): Promise<BrainstormParticipant> {
    return apiFetch(`/orchestration/brainstorms/${brainstormId}/participants`, {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

export async function updateBrainstormParticipant(
    brainstormId: string,
    participantId: string,
    payload: Record<string, unknown>,
): Promise<BrainstormParticipant> {
    return apiFetch(`/orchestration/brainstorms/${brainstormId}/participants/${participantId}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
    });
}

export async function removeBrainstormParticipant(brainstormId: string, participantId: string): Promise<void> {
    await apiFetch(`/orchestration/brainstorms/${brainstormId}/participants/${participantId}`, { method: "DELETE" });
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

export async function exportBrainstormArtifact(brainstormId: string): Promise<BrainstormArtifact> {
    return apiFetch(`/orchestration/brainstorms/${brainstormId}/export-artifact`, { method: "POST" });
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

export async function requestGithubComment(
    issueLinkId: string,
    payload: { body: string; close_issue?: boolean; idempotency_key?: string; artifact_ids?: string[] },
): Promise<Approval> {
    return apiFetch(`/orchestration/github/issues/${issueLinkId}/comment`, { method: "POST", body: JSON.stringify(payload) });
}

export async function requestGithubPr(
    issueLinkId: string,
    payload: { run_id?: string; draft_pr?: boolean } = {},
): Promise<Approval> {
    return apiFetch(`/orchestration/github/issues/${issueLinkId}/pr`, {
        method: "POST",
        body: JSON.stringify(payload),
    });
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

export async function inspectLocalRepoWorkspace(projectId: string): Promise<LocalRepoWorkspaceStatus> {
    return apiFetch(`/orchestration/projects/${projectId}/local-repo`);
}

export async function validateLocalRepoWorkspace(payload: Record<string, unknown>): Promise<LocalRepoWorkspaceStatus> {
    return apiFetch("/orchestration/local-repo/validate", {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

export async function updateLocalRepoWorkspace(
    projectId: string,
    payload: Record<string, unknown>
): Promise<LocalRepoWorkspaceStatus> {
    return apiFetch(`/orchestration/projects/${projectId}/local-repo`, {
        method: "PUT",
        body: JSON.stringify(payload),
    });
}

export async function runLocalRepoCommand(
    projectId: string,
    payload: { command: string; cwd?: string | null; timeout_seconds?: number }
): Promise<LocalRepoCommandResult> {
    return apiFetch(`/orchestration/projects/${projectId}/local-repo/commands`, {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

export async function readLocalRepoFile(projectId: string, path: string): Promise<LocalRepoReadFileResult> {
    return apiFetch(`/orchestration/projects/${projectId}/local-repo/files?path=${encodeURIComponent(path)}`);
}

export async function startAgentWorkSession(
    projectId: string,
    taskId: string,
    payload: {
        agent_id?: string | null;
        repository_link_id?: string | null;
        acceptance_criteria?: string | null;
        risk_level?: "low" | "medium" | "high";
        required_tests?: string[];
    }
): Promise<AgentWorkSession> {
    return apiFetch(`/orchestration/projects/${projectId}/tasks/${taskId}/agent-session`, {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

export async function updateAgentWorkSession(
    projectId: string,
    taskId: string,
    payload: Record<string, unknown>
): Promise<AgentWorkSession> {
    return apiFetch(`/orchestration/projects/${projectId}/tasks/${taskId}/agent-session`, {
        method: "PATCH",
        body: JSON.stringify(payload),
    });
}

export async function createLocalRepoWorktree(projectId: string, taskId: string): Promise<LocalRepoWorktree> {
    return apiFetch(`/orchestration/projects/${projectId}/tasks/${taskId}/agent-session/worktree`, {
        method: "POST",
    });
}

export async function buildLocalRepoContextPack(projectId: string, taskId: string): Promise<LocalRepoContextPack> {
    return apiFetch(`/orchestration/projects/${projectId}/tasks/${taskId}/agent-session/context-pack`, {
        method: "POST",
    });
}

export async function scoreAgentWorkSession(projectId: string, taskId: string): Promise<AgentQualityScore> {
    return apiFetch(`/orchestration/projects/${projectId}/tasks/${taskId}/agent-session/quality-score`, {
        method: "POST",
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
    mandatory_approval_gates?: string[];
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
