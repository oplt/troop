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
    getApproval,
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
    getApproval: vi.fn(),
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
        reason: "Needs review",
        effect_hash: null,
        effect_version: 1,
        expires_at: null,
        created_at: "2026-01-01T00:00:00Z",
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
        reason: "Escalated",
        effect_hash: null,
        effect_version: 1,
        expires_at: null,
        created_at: "2026-01-02T00:00:00Z",
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
        vi.mocked(getApproval).mockImplementation(async (id: string) => ({
            ...(pendingApprovals.find((item) => item.id === id) ?? pendingApprovals[0]),
            requested_by_user_id: "user-1",
            approved_by_user_id: null,
            payload: {},
            precondition_fingerprint: null,
            proposed_effect: null,
            workspace_id: null,
            eligible_approvers: [],
            routing_snapshot: {},
            decided_eligibility_reason: null,
            due_at: null,
            sla_policy: {},
            delegations: [],
            escalation_state: {},
        }));
        vi.mocked(listRuns).mockResolvedValue([]);
        vi.mocked(listOrchestrationProjects).mockResolvedValue([]);
        vi.mocked(listAgents).mockResolvedValue([]);
        vi.mocked(listGithubSyncEvents).mockResolvedValue([]);
        vi.mocked(listHITLAuditLogs).mockResolvedValue([]);
        vi.mocked(decideApproval).mockResolvedValue({
            ...pendingApprovals[0],
            requested_by_user_id: "user-1",
            approved_by_user_id: null,
            payload: {},
            precondition_fingerprint: null,
            proposed_effect: null,
            workspace_id: null,
            eligible_approvers: [],
            routing_snapshot: {},
            decided_eligibility_reason: null,
            due_at: null,
            sla_policy: {},
            delegations: [],
            escalation_state: {},
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
            expect(vi.mocked(decideApproval).mock.calls[0][0]).toBe("appr-1");
            expect(vi.mocked(decideApproval).mock.calls[0][1]).toEqual({ status: "approved", reason: undefined });
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
