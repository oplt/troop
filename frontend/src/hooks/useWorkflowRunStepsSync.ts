import { useEffect, useRef } from "react";
import { useQueryClient, type QueryClient, type QueryKey } from "@tanstack/react-query";

import { queryKeys } from "../config/queryKeys";
import { useLiveSnapshotStream, type LiveSnapshotStreamStatus } from "./useLiveSnapshotStream";

export type WorkflowRunStepsSnapshot = {
    run_id: string;
    run_status: string;
    current_node_id: string | null;
    steps: Array<{
        id: string;
        node_id: string;
        node_type: string;
        status: string;
        retry_count: number;
        started_at: string | null;
        finished_at: string | null;
        error: string | null;
    }>;
};

export const WORKFLOW_RUN_TERMINAL_STATUSES = new Set(["completed", "failed", "cancelled"]);

/** Fallback polling when the run SSE stream is unhealthy (replaces constant 3s polling). */
export const WORKFLOW_RUN_STEPS_FALLBACK_POLL_MS = 30_000;

export function workflowRunStreamPath(runId: string): string {
    return `/workforce/workflows/runs/${encodeURIComponent(runId)}/stream`;
}

export function isWorkflowRunStepsSnapshot(
    payload: Record<string, unknown>,
): payload is WorkflowRunStepsSnapshot {
    return typeof payload.run_id === "string" && Array.isArray(payload.steps);
}

export function isWorkflowRunTerminal(status: string | null | undefined): boolean {
    return Boolean(status && WORKFLOW_RUN_TERMINAL_STATUSES.has(status));
}

export function workflowRunStreamHealthy(status: LiveSnapshotStreamStatus): boolean {
    return status === "open";
}

function stableSnapshotSignature(snapshot: WorkflowRunStepsSnapshot): string {
    return JSON.stringify({
        run_status: snapshot.run_status,
        current_node_id: snapshot.current_node_id,
        steps: snapshot.steps.map((step) => ({
            id: step.id,
            status: step.status,
            retry_count: step.retry_count,
            started_at: step.started_at,
            finished_at: step.finished_at,
            error: step.error,
        })),
    });
}

/** Returns query keys to invalidate when the run step snapshot changes. */
export function collectWorkflowRunStepsInvalidationKeys(
    snapshot: WorkflowRunStepsSnapshot,
    previous: WorkflowRunStepsSnapshot | null,
): QueryKey[] {
    if (!previous) {
        return [];
    }
    if (stableSnapshotSignature(snapshot) === stableSnapshotSignature(previous)) {
        return [];
    }
    const keys: QueryKey[] = [
        queryKeys.workforce.workflowRunSteps(snapshot.run_id),
    ];
    if (snapshot.run_status !== previous.run_status || snapshot.current_node_id !== previous.current_node_id) {
        keys.push(queryKeys.workforce.workflowRun(snapshot.run_id));
    }
    return keys;
}

export function applyWorkflowRunStepsSnapshotSync(
    queryClient: QueryClient,
    payload: Record<string, unknown>,
    previousRef: { current: WorkflowRunStepsSnapshot | null },
): void {
    if (!isWorkflowRunStepsSnapshot(payload)) {
        return;
    }
    const keys = collectWorkflowRunStepsInvalidationKeys(payload, previousRef.current);
    for (const queryKey of keys) {
        void queryClient.invalidateQueries({ queryKey });
    }
    previousRef.current = payload;
}

export function useWorkflowRunStepsStream(
    runId: string | null,
    runStatus: string | null | undefined,
    enabled: boolean,
) {
    const queryClient = useQueryClient();
    const previousRef = useRef<WorkflowRunStepsSnapshot | null>(null);
    const streamEnabled = enabled && Boolean(runId) && !isWorkflowRunTerminal(runStatus);

    useEffect(() => {
        if (!streamEnabled) {
            previousRef.current = null;
        }
    }, [streamEnabled, runId]);

    return useLiveSnapshotStream(runId ? workflowRunStreamPath(runId) : null, {
        enabled: streamEnabled,
        coalesceMs: 120,
        onSnapshot: (payload) => {
            applyWorkflowRunStepsSnapshotSync(queryClient, payload, previousRef);
        },
    });
}

/**
 * Idle polling budget for an active workflow run monitor:
 * - healthy stream: 0 interval polls/min
 * - prior 3s polling: 20 polls/min
 */
export function workflowRunStepsPollsPerMinute(streamHealthy: boolean, runActive: boolean): number {
    if (!runActive) return 0;
    if (streamHealthy) return 0;
    return Math.ceil(60_000 / WORKFLOW_RUN_STEPS_FALLBACK_POLL_MS);
}
