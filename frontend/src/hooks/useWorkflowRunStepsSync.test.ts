import { describe, expect, it } from "vitest";

import { queryKeys } from "../config/queryKeys";
import {
    collectWorkflowRunStepsInvalidationKeys,
    isWorkflowRunStepsSnapshot,
    isWorkflowRunTerminal,
    workflowRunStepsPollsPerMinute,
    workflowRunStreamHealthy,
} from "./useWorkflowRunStepsSync";

const snapshot = (
    overrides: Partial<ReturnType<typeof baseSnapshot>> = {},
) => baseSnapshot(overrides);

function baseSnapshot(
    overrides: Partial<{
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
    }> = {},
) {
    return {
        run_id: "run-1",
        run_status: overrides.run_status ?? "running",
        current_node_id: overrides.current_node_id ?? "node-a",
        steps: overrides.steps ?? [
            {
                id: "step-1",
                node_id: "node-a",
                node_type: "trigger",
                status: "completed",
                retry_count: 0,
                started_at: "2026-06-18T10:00:00.000Z",
                finished_at: "2026-06-18T10:00:01.000Z",
                error: null,
            },
        ],
    };
}

describe("isWorkflowRunStepsSnapshot", () => {
    it("accepts valid workflow run snapshots", () => {
        expect(isWorkflowRunStepsSnapshot(snapshot() as unknown as Record<string, unknown>)).toBe(true);
    });

    it("rejects malformed payloads", () => {
        expect(isWorkflowRunStepsSnapshot({ run_id: "run-1" })).toBe(false);
    });
});

describe("workflow run polling budget", () => {
    it("uses zero interval polls while the stream is healthy", () => {
        expect(workflowRunStepsPollsPerMinute(true, true)).toBe(0);
    });

    it("falls back to low-frequency polling when the stream is unhealthy", () => {
        expect(workflowRunStepsPollsPerMinute(false, true)).toBe(2);
    });

    it("does not poll when the run monitor is inactive", () => {
        expect(workflowRunStepsPollsPerMinute(false, false)).toBe(0);
    });
});

describe("isWorkflowRunTerminal", () => {
    it("detects terminal statuses", () => {
        expect(isWorkflowRunTerminal("completed")).toBe(true);
        expect(isWorkflowRunTerminal("running")).toBe(false);
    });
});

describe("collectWorkflowRunStepsInvalidationKeys", () => {
    it("returns no keys for the first snapshot baseline", () => {
        expect(collectWorkflowRunStepsInvalidationKeys(snapshot(), null)).toEqual([]);
    });

    it("invalidates step queries when step status changes", () => {
        const previous = snapshot();
        const next = snapshot({
            steps: [{ ...previous.steps[0], status: "running" }],
        });
        const keys = collectWorkflowRunStepsInvalidationKeys(next, previous);
        expect(keys).toContainEqual(queryKeys.workforce.workflowRunSteps("run-1"));
    });

    it("invalidates run detail when run status changes", () => {
        const previous = snapshot();
        const next = snapshot({ run_status: "paused" });
        const keys = collectWorkflowRunStepsInvalidationKeys(next, previous);
        expect(keys).toContainEqual(queryKeys.workforce.workflowRun("run-1"));
    });
});

describe("workflowRunStreamHealthy", () => {
    it("treats open streams as healthy", () => {
        expect(workflowRunStreamHealthy("open")).toBe(true);
        expect(workflowRunStreamHealthy("reconnecting")).toBe(false);
    });
});
