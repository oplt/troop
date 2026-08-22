import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AdapterDayjs } from "@mui/x-date-pickers/AdapterDayjs";
import { LocalizationProvider } from "@mui/x-date-pickers/LocalizationProvider";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import DashboardPage from "./DashboardPage";
import {
    getActivationStatus,
    getExecutionInsights,
    getOrchestrationOverview,
} from "../api/orchestration";
import { getNotifications } from "../api/notifications";
import { listCompanies } from "../api/companies";
import { getGmailStatus, getTelegramStatus } from "../api/integrations";

vi.mock("../api/orchestration", () => ({
    getActivationStatus: vi.fn(),
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
        defaultOptions: {
            queries: { retry: false },
            mutations: { retry: false },
        },
    });

    return render(
        <QueryClientProvider client={queryClient}>
            <LocalizationProvider dateAdapter={AdapterDayjs}>
                <MemoryRouter>
                    <DashboardPage />
                </MemoryRouter>
            </LocalizationProvider>
        </QueryClientProvider>,
    );
}

describe("DashboardPage", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.mocked(getActivationStatus).mockResolvedValue({
            workspace_id: "workspace-1",
            baseline_at: "2026-06-18T00:00:00.000Z",
            milestones: [],
            completed_count: 0,
            total_count: 0,
            activated: true,
            seconds_to_activate: null,
            next_step: null,
        });
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

    it("renders dashboard sections after data loads", async () => {
        renderDashboard();

        expect(await screen.findByText("Projects")).toBeInTheDocument();
        expect(screen.getByText("Do next")).toBeInTheDocument();
        expect(screen.getByText("Schedule & analytics")).toBeInTheDocument();
        expect(screen.getByText("Check my tasks")).toBeInTheDocument();
        expect(await screen.findByText("Get your workspace ready")).toBeInTheDocument();
    });

    it("shows retryable dashboard errors", async () => {
        vi.mocked(getExecutionInsights).mockRejectedValueOnce(new Error("insights unavailable"));

        renderDashboard();

        expect(await screen.findByText("insights unavailable")).toBeInTheDocument();
        expect(screen.getAllByRole("button", { name: /retry/i }).length).toBeGreaterThan(0);
    });

    it("filters unread notifications and renders the latest items", async () => {
        vi.mocked(getNotifications).mockResolvedValue([
            {
                id: "n1",
                type: "test",
                title: "Hello",
                body_preview: "Preview",
                is_read: false,
                created_at: "2026-08-14T10:00:00Z",
            },
            {
                id: "n2",
                type: "test",
                title: "Already seen",
                body_preview: "Old",
                is_read: true,
                created_at: "2026-08-13T10:00:00Z",
            },
        ]);

        renderDashboard();

        expect(await screen.findByText("Hello")).toBeInTheDocument();
        expect(screen.getByText("Already seen")).toBeInTheDocument();
        expect(screen.getByText("New")).toBeInTheDocument();
        expect(screen.getByRole("button", { name: /mark all read/i })).toBeInTheDocument();
    });
});
