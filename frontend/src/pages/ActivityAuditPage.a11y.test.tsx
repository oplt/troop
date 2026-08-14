import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "@mui/material/styles";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { lightTheme } from "../app/theme";
import { expectNoA11yViolations } from "../test/a11y";
import ActivityAuditPage from "./ActivityAuditPage";
import {
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
    listAgents: vi.fn(),
    listApprovals: vi.fn(),
    listGithubSyncEvents: vi.fn(),
    listHITLAuditLogs: vi.fn(),
    listOrchestrationProjects: vi.fn(),
    listRuns: vi.fn(),
    decideApproval: vi.fn(),
}));

vi.mock("../api/integrations", () => ({
    editEmailApprovalPayload: vi.fn(),
    requestApprovalChanges: vi.fn(),
}));

function renderPage() {
    const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    return render(
        <QueryClientProvider client={queryClient}>
            <ThemeProvider theme={lightTheme}>
                <MemoryRouter>
                    <ActivityAuditPage />
                </MemoryRouter>
            </ThemeProvider>
        </QueryClientProvider>,
    );
}

describe("Approvals accessibility", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.mocked(listApprovals).mockResolvedValue([]);
        vi.mocked(listAgents).mockResolvedValue([]);
        vi.mocked(listOrchestrationProjects).mockResolvedValue([]);
        vi.mocked(listRuns).mockResolvedValue([]);
        vi.mocked(listGithubSyncEvents).mockResolvedValue([]);
        vi.mocked(listHITLAuditLogs).mockResolvedValue([]);
    });

    it("has no serious axe violations", async () => {
        const { container } = renderPage();
        expect(await screen.findByRole("heading", { name: "Approvals" })).toBeInTheDocument();
        expect(await screen.findByText(/All caught up/i)).toBeInTheDocument();
        await expectNoA11yViolations(container);
    });
});
