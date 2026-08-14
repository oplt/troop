import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "@mui/material/styles";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { lightTheme } from "../app/theme";
import { ActivityAuditContent } from "../features/activityAudit/ActivityAuditContent";
import {
    decideApproval,
    listAgents,
    listApprovals,
    listGithubSyncEvents,
    listHITLAuditLogs,
    listOrchestrationProjects,
    listRuns,
} from "../api/orchestration";

vi.mock("../app/snackbarContext", () => ({
    useSnackbar: () => ({ showToast: vi.fn() }),
}));

vi.mock("../api/orchestration", () => ({
    decideApproval: vi.fn(),
    listAgents: vi.fn(),
    listApprovals: vi.fn(),
    listGithubSyncEvents: vi.fn(),
    listHITLAuditLogs: vi.fn(),
    listOrchestrationProjects: vi.fn(),
    listRuns: vi.fn(),
}));

const pendingApprovals = [
    {
        id: "appr-1",
        status: "pending" as const,
        approval_type: "task_escalation",
        project_id: "proj-1",
        task_id: "task-1",
        run_id: "run-1",
        issue_link_id: null,
        requested_by_user_id: "user-1",
        approved_by_user_id: null,
        reason: "Needs review",
        payload: {},
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
        resolved_at: null,
    },
    {
        id: "appr-2",
        status: "pending" as const,
        approval_type: "rule_escalation",
        project_id: "proj-1",
        task_id: "task-2",
        run_id: "run-2",
        issue_link_id: null,
        requested_by_user_id: "user-1",
        approved_by_user_id: null,
        reason: "Escalated",
        payload: {},
        created_at: "2026-01-02T00:00:00Z",
        updated_at: "2026-01-02T00:00:00Z",
        resolved_at: null,
    },
];

function renderAudit() {
    const queryClient = new QueryClient({
        defaultOptions: {
            queries: { retry: false },
            mutations: { retry: false },
        },
    });

    return render(
        <QueryClientProvider client={queryClient}>
            <ThemeProvider theme={lightTheme}>
                <MemoryRouter>
                    <ActivityAuditContent />
                </MemoryRouter>
            </ThemeProvider>
        </QueryClientProvider>,
    );
}

describe("ActivityAuditContent keyboard queue", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        Element.prototype.scrollIntoView = vi.fn();
        vi.mocked(listApprovals).mockResolvedValue(pendingApprovals);
        vi.mocked(listRuns).mockResolvedValue([]);
        vi.mocked(listOrchestrationProjects).mockResolvedValue([]);
        vi.mocked(listAgents).mockResolvedValue([]);
        vi.mocked(listGithubSyncEvents).mockResolvedValue([]);
        vi.mocked(listHITLAuditLogs).mockResolvedValue([]);
        vi.mocked(decideApproval).mockResolvedValue({
            ...pendingApprovals[0],
            status: "approved",
        });
    });

    it("moves queue focus with j and approves focused card with a", async () => {
        const user = userEvent.setup();
        renderAudit();
        expect(await screen.findByText("Pending approvals")).toBeInTheDocument();

        await user.keyboard("j");
        await user.keyboard("a");

        await waitFor(() => {
            expect(decideApproval).toHaveBeenCalled();
            expect(decideApproval.mock.calls[0][0]).toBe("appr-1");
            expect(decideApproval.mock.calls[0][1]).toEqual({ status: "approved", reason: undefined });
        });
    });

    it("rejects focused card with r", async () => {
        const user = userEvent.setup();
        renderAudit();
        expect(await screen.findByText("Pending approvals")).toBeInTheDocument();

        await user.keyboard("r");

        await waitFor(() => {
            expect(decideApproval).toHaveBeenCalledWith("appr-2", {
                status: "rejected",
                reason: "Rejected via keyboard shortcut",
            });
        });
    });
});
