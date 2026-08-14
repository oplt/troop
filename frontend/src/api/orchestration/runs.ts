import { apiFetch } from "../client";

export type TaskRun = {
    id: string;
    parent_run_id: string | null;
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
    /** Present on POST .../runs when the server attaches startup notices (e.g. missing provider). */
    startup_warnings?: string[];
};

export type RunTraceSpanKind =
    | "trigger"
    | "node"
    | "model_attempt"
    | "tool_auth"
    | "approval"
    | "tool_effect"
    | "retry_checkpoint";

export type RunTraceRestrictedRef = {
    has_restricted: boolean;
    restricted_fields: string[];
};

export type RunTraceSpan = {
    id: string;
    run_id: string;
    kind: RunTraceSpanKind;
    title: string;
    status: string;
    message: string | null;
    started_at: string;
    finished_at: string | null;
    safe_payload: Record<string, unknown>;
    restricted: RunTraceRestrictedRef;
    source_event_id: string | null;
    source_event_type: string | null;
    parent_span_id: string | null;
    tokens_input: number;
    tokens_output: number;
    cost_usd_micros: number;
};

export type CursorToken = {
    created_at: string;
    id: string;
    position?: number | null;
};

export type CursorPage<T> = {
    items: T[];
    next_cursor: CursorToken | null;
};

export type RunTracePage = CursorPage<RunTraceSpan> & {
    meta: {
        run_id: string;
        span_kinds_present: string[];
        truncated: boolean;
    };
};

export type RunEventListItem = {
    id: string;
    run_id: string;
    task_id: string | null;
    level: string;
    event_type: string;
    message: string;
    input_tokens: number;
    output_tokens: number;
    cost_usd_micros: number;
    created_at: string;
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

function listItemToRunEvent(item: RunEventListItem): RunEvent {
    return { ...item, payload: {} };
}

export type RunArtifact = {
    id: string;
    run_id: string | null;
    task_id: string;
    type: string;
    name: string;
    path_or_url: string | null;
    metadata: Record<string, unknown>;
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
    child_runs: TaskRun[];
    blocker_queue: Array<Record<string, unknown>>;
    review_state: Record<string, unknown>;
    github_action_state: Record<string, unknown>;
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
    child_runs: TaskRun[];
    blocker_queue: Array<Record<string, unknown>>;
    review_state: Record<string, unknown>;
    github_action_state: Record<string, unknown>;
    resumable: boolean;
};

export async function listRuns(
    projectId?: string,
    limit = 50,
    cursor?: { created_at: string; id: string },
): Promise<TaskRun[]> {
    const params = new URLSearchParams({ limit: String(limit) });
    if (projectId) params.set("project_id", projectId);
    if (cursor?.created_at) params.set("cursor_created_at", cursor.created_at);
    if (cursor?.id) params.set("cursor_id", cursor.id);
    return apiFetch(`/orchestration/runs?${params.toString()}`);
}

export async function getRun(runId: string): Promise<TaskRun> {
    return apiFetch(`/orchestration/runs/${runId}`);
}

export async function getAgentRun(runId: string): Promise<TaskRun> {
    return apiFetch(`/runs/${runId}`);
}

export async function listAgentRunSteps(runId: string): Promise<RunEvent[]> {
    return apiFetch(`/runs/${runId}/steps`);
}

export async function approveAgentRunPlan(runId: string): Promise<TaskRun> {
    return apiFetch(`/runs/${runId}/approve-plan`, { method: "POST" });
}

export async function cancelAgentRun(runId: string): Promise<TaskRun> {
    return apiFetch(`/runs/${runId}/cancel`, { method: "POST" });
}

export async function listAgentRunArtifacts(runId: string): Promise<RunArtifact[]> {
    return apiFetch(`/runs/${runId}/artifacts`);
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

export async function listRunEventsPage(
    runId: string,
    options: { limit?: number; cursor?: CursorToken | null } = {},
): Promise<CursorPage<RunEventListItem>> {
    const params = new URLSearchParams();
    if (options.limit) params.set("limit", String(options.limit));
    if (options.cursor?.created_at) params.set("cursor_created_at", options.cursor.created_at);
    if (options.cursor?.id) params.set("cursor_id", options.cursor.id);
    const query = params.toString();
    return apiFetch(`/orchestration/runs/${runId}/events${query ? `?${query}` : ""}`);
}

export async function listRunEvents(runId: string, limit = 100): Promise<RunEvent[]> {
    const page = await listRunEventsPage(runId, { limit });
    return page.items.map(listItemToRunEvent);
}

export async function listRunTracePage(
    runId: string,
    options: { limit?: number; cursor?: CursorToken | null } = {},
): Promise<RunTracePage> {
    const params = new URLSearchParams();
    if (options.limit) params.set("limit", String(options.limit));
    if (options.cursor?.created_at) params.set("cursor_created_at", options.cursor.created_at);
    if (options.cursor?.id) params.set("cursor_id", options.cursor.id);
    const query = params.toString();
    return apiFetch(`/orchestration/runs/${runId}/trace${query ? `?${query}` : ""}`);
}

export async function listRunTrace(runId: string, pageSize = 100): Promise<RunTracePage> {
    const all: RunTraceSpan[] = [];
    let cursor: CursorToken | null = null;
    let meta: RunTracePage["meta"] = { run_id: runId, span_kinds_present: [], truncated: false };

    for (;;) {
        const page = await listRunTracePage(runId, { limit: pageSize, cursor });
        meta = page.meta;
        all.push(...page.items);
        if (!page.next_cursor) {
            return { items: all, next_cursor: null, meta };
        }
        cursor = page.next_cursor;
    }
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

export async function getRunExplanation(runId: string): Promise<Record<string, unknown>> {
    return apiFetch(`/orchestration/runs/${runId}/explanation`);
}
