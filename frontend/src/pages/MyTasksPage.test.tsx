import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import MyTasksPage from "./MyTasksPage";
import { listOrchestrationProjects, listOrchestrationTasks } from "../api/orchestration";

vi.mock("../api/orchestration", () => ({
    listOrchestrationProjects: vi.fn(),
    listOrchestrationTasks: vi.fn(),
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
        vi.mocked(listOrchestrationProjects).mockResolvedValue([
            {
                id: "proj-1",
                name: "Launch Ops",
                slug: "launch-ops",
                description: null,
                status: "active",
                goals_markdown: "",
                settings: {},
                memory_scope: "project",
                knowledge_summary: null,
                company_id: null,
                created_at: "2026-08-14T10:00:00Z",
                updated_at: "2026-08-14T10:00:00Z",
            },
        ]);
        vi.mocked(listOrchestrationTasks).mockResolvedValue([
            {
                id: "task-1",
                project_id: "proj-1",
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
            },
        ]);
    });

    it("iterates task list items without treating the response as a page object", async () => {
        renderPage();

        expect(await screen.findByText("Open checklist")).toBeInTheDocument();
        expect(screen.getByText("Launch Ops")).toBeInTheDocument();
        expect(listOrchestrationTasks).toHaveBeenCalledWith("proj-1");
    });
});
