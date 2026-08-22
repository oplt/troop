import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import MyTasksPage from "./MyTasksPage";
import { listMyTasksPage } from "../api/orchestration";

vi.mock("../api/orchestration", () => ({
    listMyTasksPage: vi.fn(),
}));

function renderPage() {
    const queryClient = new QueryClient({
        defaultOptions: {
            queries: { retry: false },
            mutations: { retry: false },
        },
    });
    return render(
        <QueryClientProvider client={queryClient}>
            <MemoryRouter>
                <MyTasksPage />
            </MemoryRouter>
        </QueryClientProvider>,
    );
}

describe("MyTasksPage", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.mocked(listMyTasksPage).mockResolvedValue({
            items: [{
                id: "task-1",
                project_id: "proj-1",
                project_name: "Launch Ops",
                title: "Open checklist",
                status: "queued",
                priority: "normal",
                task_type: "general",
                position: 0,
                assigned_agent_id: "agent-1",
                human_assignee_id: null,
                parent_task_id: null,
                github_issue_number: null,
                github_issue_url: null,
                github_repository_full_name: null,
                due_date: null,
                labels: [],
                dependency_ids: [],
                has_result: false,
                created_at: "2026-08-14T10:00:00Z",
                updated_at: "2026-08-14T10:00:00Z",
            }],
            next_cursor: null,
        });
    });

    it("loads one owner-scoped task feed and opens a right-hand inspector", async () => {
        const user = userEvent.setup();
        renderPage();

        await user.click(await screen.findByRole("button", { name: "Open checklist" }));
        expect(screen.getAllByText("Launch Ops")).toHaveLength(2);
        expect(screen.getByRole("link", { name: "Open task" })).toBeInTheDocument();
        expect(listMyTasksPage).toHaveBeenCalledWith({ limit: 50, cursor: null });
    });
});
