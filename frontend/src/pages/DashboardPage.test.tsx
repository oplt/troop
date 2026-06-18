import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AdapterDayjs } from "@mui/x-date-pickers/AdapterDayjs";
import { LocalizationProvider } from "@mui/x-date-pickers/LocalizationProvider";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import DashboardPage from "./DashboardPage";
import {
    getExecutionInsights,
    getOrchestrationOverview,
    listOrchestrationProjects,
} from "../api/orchestration";
import { getNotifications } from "../api/notifications";

vi.mock("../api/orchestration", () => ({
    getExecutionInsights: vi.fn(),
    getOrchestrationOverview: vi.fn(),
    listOrchestrationProjects: vi.fn(),
}));

vi.mock("../api/notifications", () => ({
    getNotifications: vi.fn(),
    markAllRead: vi.fn(),
    markRead: vi.fn(),
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
        vi.mocked(listOrchestrationProjects).mockResolvedValue([]);
        vi.mocked(getNotifications).mockResolvedValue([]);
        vi.mocked(getOrchestrationOverview).mockResolvedValue({
            active_runs: [],
            pending_approvals: [],
            recent_failures: 0,
            runs_by_status: {},
            agents: [],
            projects: [],
        });
        vi.mocked(getExecutionInsights).mockResolvedValue({
            since: "2026-06-18T00:00:00.000Z",
            by_event_type: [],
            tool_failures_by_tool: [],
        });
    });

    it("renders dashboard sections after data loads", async () => {
        renderDashboard();

        expect(await screen.findByText("Agent Projects")).toBeInTheDocument();
        expect(screen.getByText("Orchestration")).toBeInTheDocument();
        expect(screen.getByText("Run activity")).toBeInTheDocument();
    });

    it("shows retryable dashboard errors", async () => {
        vi.mocked(getExecutionInsights).mockRejectedValueOnce(new Error("insights unavailable"));

        renderDashboard();

        expect(await screen.findByText("insights unavailable")).toBeInTheDocument();
        expect(screen.getAllByRole("button", { name: /retry/i }).length).toBeGreaterThan(0);
    });
});
