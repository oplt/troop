import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AdapterDayjs } from "@mui/x-date-pickers/AdapterDayjs";
import { LocalizationProvider } from "@mui/x-date-pickers/LocalizationProvider";
import { ThemeProvider } from "@mui/material/styles";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { lightTheme } from "../app/theme";
import { expectNoA11yViolations } from "../test/a11y";
import { VISUAL_BASELINES } from "../test/visualBaselines";
import DashboardPage from "./DashboardPage";
import {
    getExecutionInsights,
    getOrchestrationOverview,
} from "../api/orchestration";
import { getNotifications } from "../api/notifications";
import { listCompanies } from "../api/companies";
import { getGmailStatus, getTelegramStatus } from "../api/integrations";

vi.mock("../api/orchestration", () => ({
    getExecutionInsights: vi.fn(),
    getOrchestrationOverview: vi.fn(),
}));

vi.mock("../api/notifications", () => ({
    getNotifications: vi.fn(),
    markAllRead: vi.fn(),
    markRead: vi.fn(),
}));

vi.mock("../api/companies", () => ({
    listCompanies: vi.fn(),
}));

vi.mock("../api/integrations", () => ({
    getGmailStatus: vi.fn(),
    getTelegramStatus: vi.fn(),
}));

function renderDashboard() {
    const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    return render(
        <QueryClientProvider client={queryClient}>
            <ThemeProvider theme={lightTheme}>
                <LocalizationProvider dateAdapter={AdapterDayjs}>
                    <MemoryRouter>
                        <DashboardPage />
                    </MemoryRouter>
                </LocalizationProvider>
            </ThemeProvider>
        </QueryClientProvider>,
    );
}

describe("Dashboard accessibility + visual baseline", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.mocked(getNotifications).mockResolvedValue([]);
        vi.mocked(listCompanies).mockResolvedValue([]);
        vi.mocked(getGmailStatus).mockResolvedValue({
            provider: "gmail",
            status: "disconnected",
            account_label: null,
            error: null,
            granted_scopes: [],
            required_scopes: [],
            last_successful_event_at: null,
            expires_at: null,
            installation_id: null,
            metadata: {},
        });
        vi.mocked(getTelegramStatus).mockResolvedValue({
            provider: "telegram",
            status: "disconnected",
            account_label: null,
            error: null,
            granted_scopes: [],
            required_scopes: [],
            last_successful_event_at: null,
            expires_at: null,
            installation_id: null,
            metadata: {},
        });
        vi.mocked(getOrchestrationOverview).mockResolvedValue({
            active_runs: [],
            pending_approvals: [],
            agents: [],
            projects: [],
            github_events: [],
        });
        vi.mocked(getExecutionInsights).mockResolvedValue({
            since: "2026-06-18T00:00:00.000Z",
            days: 30,
            by_event_type: [],
            tool_failures_by_tool: [],
            reopen_events: 0,
            brainstorm_round_summary_events: 0,
            blocked_events: 0,
            tool_call_failed_events: 0,
        });
    });

    it("matches dashboard visual title baseline", async () => {
        const dash = VISUAL_BASELINES.pages.find((p) => p.route === "/dashboard");
        renderDashboard();
        for (const hint of dash?.titleHints ?? []) {
            expect(await screen.findByText(hint)).toBeInTheDocument();
        }
    });

    it("has no serious axe violations", async () => {
        const { container } = renderDashboard();
        await screen.findByText("Do next");
        await expectNoA11yViolations(container);
    });
});
