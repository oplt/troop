import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";

import { useApprovals } from "./useApprovals";
import {
    listAgents,
    listApprovals,
    listGithubSyncEvents,
    listOrchestrationProjects,
    listRuns,
} from "../../../api/orchestration";

vi.mock("../../../app/snackbarContext", () => ({
    useSnackbar: () => ({ showToast: vi.fn() }),
}));

vi.mock("../../../api/orchestration", () => ({
    decideApproval: vi.fn(),
    listAgents: vi.fn(),
    listApprovals: vi.fn(),
    listGithubSyncEvents: vi.fn(),
    listOrchestrationProjects: vi.fn(),
    listRuns: vi.fn(),
}));

function wrapper({ children }: { children: ReactNode }) {
    const queryClient = new QueryClient({
        defaultOptions: {
            queries: { retry: false },
            mutations: { retry: false },
        },
    });
    return (
        <QueryClientProvider client={queryClient}>
            <MemoryRouter>{children}</MemoryRouter>
        </QueryClientProvider>
    );
}

describe("useApprovals", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.mocked(listApprovals).mockResolvedValue([
            {
                id: "appr-1",
                project_id: "proj-1",
                task_id: "task-1",
                run_id: "run-1",
                issue_link_id: null,
                approval_type: "task_escalation",
                status: "pending",
                reason: "Needs review",
                effect_hash: null,
                effect_version: 1,
                expires_at: null,
                created_at: "2026-08-14T10:00:00Z",
                resolved_at: null,
            },
        ]);
        vi.mocked(listRuns).mockResolvedValue([
            {
                id: "run-1",
                parent_run_id: null,
                project_id: "proj-1",
                task_id: "task-1",
                run_mode: "single_agent",
                status: "in_progress",
                model_name: "gpt-test",
                attempt_number: 1,
                token_input: 1,
                token_output: 1,
                token_total: 2,
                estimated_cost_micros: 0,
                latency_ms: 10,
                error_message: null,
                retry_count: 0,
                created_at: "2026-08-14T10:00:00Z",
                started_at: null,
                completed_at: null,
                cancelled_at: null,
            },
        ]);
        vi.mocked(listOrchestrationProjects).mockResolvedValue([]);
        vi.mocked(listAgents).mockResolvedValue([]);
        vi.mocked(listGithubSyncEvents).mockResolvedValue([]);
    });

    it("filters approvals and runs from unwrapped list items", async () => {
        const { result } = renderHook(() => useApprovals(), { wrapper });

        await waitFor(() => {
            expect(result.current.pending).toHaveLength(1);
            expect(result.current.filteredRuns).toHaveLength(1);
        });
        expect(result.current.pending.filter((item) => item.status === "pending")).toHaveLength(1);
        expect(result.current.filteredRuns.filter((run) => run.status === "in_progress")).toHaveLength(1);
        expect(result.current.pending[0]).not.toHaveProperty("payload");
        expect(result.current.filteredRuns[0]).not.toHaveProperty("worker_agent_id");
    });
});
