import { apiFetch } from "../client";
import type { Agent } from "./agents";
import type { Approval } from "./approvals";
import type { GithubSyncEvent, OrchestrationProject } from "./projects";
import type { TaskRun } from "./runs";

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

export type ActivationMilestone = {
    key: string;
    label: string;
    completed: boolean;
    completed_at: string | null;
    seconds_from_baseline: number | null;
    resource_type?: string | null;
    resource_id?: string | null;
    metadata?: Record<string, unknown>;
};

export type ActivationStatus = {
    workspace_id: string;
    baseline_at: string;
    milestones: ActivationMilestone[];
    completed_count: number;
    total_count: number;
    activated: boolean;
    seconds_to_activate: number | null;
    next_step: {
        key: string;
        label: string;
        cta: string;
        path: string;
    } | null;
};

export async function getActivationStatus(): Promise<ActivationStatus> {
    return apiFetch("/orchestration/activation");
}

export type CostAggregation = {
    period: string;
    by_project: Array<{ name: string; cost_usd: number; tokens: number; runs: number }>;
    by_agent: Array<{ name: string; cost_usd: number; tokens: number; runs: number }>;
    by_task: Array<{ name: string; cost_usd: number; tokens: number; runs: number }>;
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
    total_runs?: number;
    completed_runs?: number;
    failed_runs?: number;
    total_tokens?: number;
    total_cost_usd?: number;
    avg_latency_ms?: number;
    p95_latency_ms?: number;
    retry_count?: number;
    retry_rate?: number;
    validation_failures?: number;
    hallucination_failures?: number;
    github_sync_events?: number;
    github_sync_failures?: number;
    discussion_rounds?: number;
    discussion_loop_score?: number | null;
    discussion_loop_detected?: number;
    acceptance_checks?: number;
    accepted_after_review?: number;
    acceptance_rate_after_review?: number | null;
    evaluation_records?: number;
    by_project?: ExecutionRollup[];
    by_agent?: ExecutionRollup[];
    by_task?: ExecutionRollup[];
    by_provider?: ExecutionRollup[];
};

export type ExecutionRollup = {
    id: string | null;
    name: string;
    runs: number;
    tokens: number;
    cost_usd: number;
    avg_latency_ms: number;
    retries: number;
    tool_failures: number;
    validation_failures: number;
    acceptance_rate: number | null;
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

export type RuntimeInfo = {
    orchestration_provider_failover: boolean;
    orchestration_use_langgraph: boolean;
    orchestration_durable_queue_backend: string;
    durable_signal_model: string;
    durable_query_model: string;
    durable_backend: Record<string, unknown>;
    execution_topology: Record<string, unknown>;
    realtime_transport: Record<string, unknown>;
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

export async function getOrchestrationRuntimeInfo(): Promise<RuntimeInfo> {
    return apiFetch("/orchestration/runtime-info");
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

export type AgentPattern = {
    id: string;
    name: string;
    description: string;
    category: string;
    baseline_run_mode: string;
    pattern_run_mode: string;
    execution_overlay: Record<string, unknown>;
};

export type AgentPatternStatus = {
    pattern_id: string;
    status: "disabled" | "eval_pending" | "released";
    eval_ready: boolean;
    applied_at: string | null;
    enabled_at: string | null;
    last_eval_id: string | null;
    last_advantage: Record<string, unknown> | null;
};

export async function listEvalRecords(projectId: string): Promise<EvalRecord[]> {
    return apiFetch(`/orchestration/projects/${projectId}/evals`);
}

export async function listAgentPatterns(): Promise<AgentPattern[]> {
    return apiFetch("/orchestration/agent-patterns");
}

export async function listProjectAgentPatterns(
    projectId: string,
): Promise<{ project_id: string; patterns: AgentPatternStatus[] }> {
    return apiFetch(`/orchestration/projects/${projectId}/agent-patterns`);
}

export async function applyAgentPattern(
    projectId: string,
    patternId: string,
): Promise<{ project_id: string; pattern: AgentPattern; status: string; applied_execution: Record<string, unknown> }> {
    return apiFetch(`/orchestration/projects/${projectId}/agent-patterns/${patternId}/apply`, { method: "POST" });
}

export async function benchmarkAgentPattern(
    projectId: string,
    patternId: string,
    payload: { task_id: string; agent_id: string; model_a?: string; model_b?: string },
): Promise<{ eval_id: string; pattern_id: string; task_id: string; runs: Array<{ side: string; run_id: string }> }> {
    return apiFetch(`/orchestration/projects/${projectId}/agent-patterns/${patternId}/benchmark`, {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

export async function scoreAgentPatternEval(
    projectId: string,
    evalId: string,
): Promise<{ eval: EvalRecord; pattern_id: string; advantage: Record<string, unknown> }> {
    return apiFetch(`/orchestration/projects/${projectId}/agent-patterns/evals/${evalId}/score`, { method: "POST" });
}

export async function enableAgentPattern(
    projectId: string,
    patternId: string,
): Promise<{ project_id: string; pattern_id: string; status: string; enabled_at: string }> {
    return apiFetch(`/orchestration/projects/${projectId}/agent-patterns/${patternId}/enable`, { method: "POST" });
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

export async function getAgentPerformance(days: number = 30): Promise<Array<Record<string, unknown>>> {
    return apiFetch(`/orchestration/analytics/agent-performance?days=${days}`);
}

export async function getBudgetProjection(days: number = 30): Promise<Record<string, unknown>> {
    return apiFetch(`/orchestration/analytics/budget-projection?days=${days}`);
}
