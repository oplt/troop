import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import OrchestrationProjectDetailView from "./projectDetail/OrchestrationProjectDetailView";
import { buildOrchestrationTaskFixture } from "../features/orchestration/project/viewModel.fixtures";
import {
    getGateConfig,
    getOrchestrationProject,
    listAgents,
    listApprovals,
    listOrchestrationTasks,
    listProjectMilestones,
    listRuns,
} from "../api/orchestration";

vi.mock("../app/snackbarContext", () => ({
    useSnackbar: () => ({ showToast: vi.fn() }),
}));

vi.mock("../hooks/projectLiveSnapshotSync", () => ({
    useProjectLiveSnapshotSync: vi.fn(),
}));

vi.mock("../api/orchestration", () => {
    const fn = vi.fn;
    return {
        addProjectAgent: fn(),
        checkTaskAcceptance: fn(),
        createAgentFromTemplate: fn(),
        createBrainstorm: fn(),
        createOrchestrationTask: fn(),
        createProjectDecision: fn(),
        createProjectMilestone: fn(),
        createTaskArtifact: fn(),
        decideApproval: fn(),
        decomposeTask: fn(),
        deleteAgent: fn(),
        deleteOrchestrationTask: fn(),
        deleteProjectDocument: fn(),
        deleteProjectMemoryEntry: fn(),
        getGateConfig: fn(),
        getMergeResolutionPreview: fn(),
        getOrchestrationProject: fn(),
        getProjectMemorySettings: fn(),
        getProjectRepositoryIndexStatus: fn(),
        getRunWorkingMemory: fn(),
        getTaskExecutionState: fn(),
        getTaskMemoryCoordination: fn(),
        getTaskTimeline: fn(),
        listAgentTemplates: fn(),
        listAgents: fn(),
        listApprovals: fn(),
        listBrainstorms: fn(),
        listDagReadyTasks: fn(),
        listGithubIssueLinks: fn(),
        listGithubSyncEvents: fn(),
        listOrchestrationTasks: fn(),
        listProjectAgents: fn(),
        listProjectDecisions: fn(),
        listProjectDocuments: fn(),
        listProjectMemory: fn(),
        listProjectMemoryIngestJobs: fn(),
        listProjectMilestones: fn(),
        listProjectRepositories: fn(),
        listProviders: fn(),
        listRuns: fn(),
        listSemanticMemory: fn(),
        listSubtasks: fn(),
        listTaskArtifacts: fn(),
        patchProjectMemorySettings: fn(),
        patchTaskMemoryCoordination: fn(),
        queueProjectRepositoryIndex: fn(),
        removeProjectAgent: fn(),
        searchEpisodicMemory: fn(),
        searchProjectKnowledge: fn(),
        startBrainstorm: fn(),
        startDagParallelReady: fn(),
        startMergeResolutionRun: fn(),
        startTaskRun: fn(),
        updateAgent: fn(),
        updateGateConfig: fn(),
        updateLocalRepoWorkspace: fn(),
        updateOrchestrationProject: fn(),
        updateOrchestrationTask: fn(),
        updateProjectAgent: fn(),
        updateProjectMilestone: fn(),
        updateProjectRepository: fn(),
        uploadProjectDocument: fn(),
    };
});

function renderProjectDetail(initialEntry = "/projects/project-1") {
    const queryClient = new QueryClient({
        defaultOptions: {
            queries: { retry: false },
            mutations: { retry: false },
        },
    });

    return render(
        <QueryClientProvider client={queryClient}>
            <MemoryRouter initialEntries={[initialEntry]}>
                <Routes>
                    <Route path="/projects/:projectId" element={<OrchestrationProjectDetailView />} />
                </Routes>
            </MemoryRouter>
        </QueryClientProvider>,
    );
}

describe("OrchestrationProjectDetailPage", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.mocked(getOrchestrationProject).mockResolvedValue({
            id: "project-1",
            name: "Launch Ops",
            slug: "launch-ops",
            description: "Coordinate launch work",
            status: "active",
            goals_markdown: "Ship safely",
            settings: {
                workspace_overview: {
                    executive_summary: "Launch control summary",
                    current_focus: "Readiness",
                    decision_focus: "Cutover",
                },
            },
            memory_scope: "project",
            knowledge_summary: null,
            company_id: null,
            created_at: "2026-06-18T00:00:00.000Z",
            updated_at: "2026-06-18T00:00:00.000Z",
        });
        vi.mocked(listAgents).mockResolvedValue([]);
        vi.mocked(listOrchestrationTasks).mockResolvedValue([]);
        vi.mocked(listRuns).mockResolvedValue([]);
        vi.mocked(listApprovals).mockResolvedValue([]);
        vi.mocked(listProjectMilestones).mockResolvedValue([]);
        vi.mocked(getGateConfig).mockResolvedValue({
            autonomy_level: "assisted",
            approval_gates: [],
        });
    });

    it("renders the overview tab from project data", async () => {
        renderProjectDetail();

        expect(await screen.findByText("Launch Ops")).toBeInTheDocument();
        expect(screen.getByText("Workspace")).toBeInTheDocument();
        expect(screen.getByText("Launch control summary")).toBeInTheDocument();
        expect(screen.getByRole("tab", { name: "Overview" })).toBeInTheDocument();
    });

    it("honors the tab query param for deep links", async () => {
        renderProjectDetail("/projects/project-1?tab=runs");

        expect(await screen.findByRole("tab", { name: "Runs" })).toHaveAttribute("aria-selected", "true");
        expect(screen.getByText("Runs & approvals")).toBeInTheDocument();
    });

    it("opens the overview edit drawer", async () => {
        const user = userEvent.setup();
        renderProjectDetail();

        await screen.findByText("Launch Ops");
        await user.click(screen.getByRole("button", { name: "Edit overview" }));

        expect(await screen.findByLabelText("Executive summary")).toBeInTheDocument();
        expect(screen.getByText("Edit overview", { selector: "h6" })).toBeInTheDocument();
    });

    it("switches to the board tab and loads task data", async () => {
        const user = userEvent.setup();
        vi.mocked(listOrchestrationTasks).mockResolvedValue([
            buildOrchestrationTaskFixture(),
        ]);

        renderProjectDetail();
        await screen.findByText("Launch Ops");
        await user.click(screen.getByRole("tab", { name: "Board" }));

        await waitFor(() => {
            expect(screen.getByText("Verify rollout checklist")).toBeInTheDocument();
        });
        expect(listOrchestrationTasks).toHaveBeenCalledWith("project-1");
    });
});
