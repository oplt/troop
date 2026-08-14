import type { RunCostSummary, RunTraceSpan, TaskRun } from "../../api/orchestration";

export type RunTraceFilter =
    | "all"
    | "models"
    | "tools"
    | "approvals"
    | "errors"
    | "memory"
    | "retries";

export type RunTraceSummaryStats = {
    status: string;
    activeTimeMs: number | null;
    humanWaitMs: number;
    costUsd: number | null;
    modelCount: number;
    toolCount: number;
    approvalCount: number;
    retryCount: number;
    errorCount: number;
    externalEffectCount: number;
};

const MODEL_KINDS = new Set(["model_attempt"]);
const TOOL_KINDS = new Set(["tool_auth", "tool_effect"]);
const RETRY_KINDS = new Set(["retry_checkpoint"]);
const MEMORY_KINDS = new Set(["node"]);

function spanDurationMs(span: RunTraceSpan): number | null {
    if (!span.finished_at) return null;
    const start = new Date(span.started_at).getTime();
    const end = new Date(span.finished_at).getTime();
    if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return null;
    return end - start;
}

export function computeTraceSummary(
    run: TaskRun,
    spans: RunTraceSpan[],
    costSummary?: RunCostSummary | null,
): RunTraceSummaryStats {
    const modelCount = spans.filter((span) => MODEL_KINDS.has(span.kind)).length;
    const toolCount = spans.filter((span) => TOOL_KINDS.has(span.kind)).length;
    const approvalCount = spans.filter((span) => span.kind === "approval").length;
    const retryCount = Math.max(
        run.retry_count,
        spans.filter((span) => RETRY_KINDS.has(span.kind)).length,
    );
    const errorCount = spans.filter(
        (span) =>
            span.status === "failed"
            || span.status === "rejected"
            || span.status === "blocked"
            || Boolean(span.message?.toLowerCase().includes("error")),
    ).length;
    const externalEffectCount = spans.filter(
        (span) =>
            span.kind === "tool_effect"
            && (span.id.startsWith("effect:") || span.safe_payload.external_result_id),
    ).length;

    const humanWaitMs = spans
        .filter((span) => span.kind === "approval")
        .reduce((total, span) => total + (spanDurationMs(span) ?? 0), 0);

    let activeTimeMs = run.latency_ms;
    if (activeTimeMs == null && run.started_at && run.completed_at) {
        activeTimeMs = new Date(run.completed_at).getTime() - new Date(run.started_at).getTime();
    }
    if (activeTimeMs != null && humanWaitMs > 0) {
        activeTimeMs = Math.max(0, activeTimeMs - humanWaitMs);
    }

    const costUsd = costSummary?.estimated_cost_usd
        ?? (run.estimated_cost_micros > 0 ? run.estimated_cost_micros / 1_000_000 : null);

    return {
        status: run.status,
        activeTimeMs,
        humanWaitMs,
        costUsd,
        modelCount,
        toolCount,
        approvalCount,
        retryCount,
        errorCount,
        externalEffectCount,
    };
}

export function filterTraceSpans(spans: RunTraceSpan[], filter: RunTraceFilter): RunTraceSpan[] {
    if (filter === "all") return spans;
    if (filter === "models") return spans.filter((span) => MODEL_KINDS.has(span.kind));
    if (filter === "tools") return spans.filter((span) => TOOL_KINDS.has(span.kind));
    if (filter === "approvals") return spans.filter((span) => span.kind === "approval");
    if (filter === "retries") return spans.filter((span) => RETRY_KINDS.has(span.kind));
    if (filter === "memory") return spans.filter((span) => MEMORY_KINDS.has(span.kind));
    return spans.filter(
        (span) =>
            span.status === "failed"
            || span.status === "rejected"
            || span.status === "blocked"
            || span.message?.toLowerCase().includes("error"),
    );
}

export function formatDurationMs(ms: number | null): string {
    if (ms == null || !Number.isFinite(ms)) return "—";
    if (ms < 1000) return `${ms} ms`;
    if (ms < 60_000) return `${(ms / 1000).toFixed(1)} s`;
    const minutes = Math.floor(ms / 60_000);
    const seconds = Math.round((ms % 60_000) / 1000);
    return `${minutes}m ${seconds}s`;
}

export function spanKindLabel(kind: RunTraceSpan["kind"]): string {
    return kind.replaceAll("_", " ");
}
