import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "@mui/material/styles";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { lightTheme } from "../app/theme";
import { expectNoA11yViolations } from "../test/a11y";
import OrchestrationProjectDetailView from "./projectDetail/OrchestrationProjectDetailView";
import {
    getGateConfig,
    getOrchestrationProject,
    listAgents,
    listApprovals,
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
        getOrchestrationTask: fn(),
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

function renderProjectDetail() {
    const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    return render(
        <QueryClientProvider client={queryClient}>
            <ThemeProvider theme={lightTheme}>
                <MemoryRouter initialEntries={["/projects/project-1"]}>
                    <Routes>
                        <Route path="/projects/:projectId" element={<OrchestrationProjectDetailView />} />
                    </Routes>
                </MemoryRouter>
            </ThemeProvider>
        </QueryClientProvider>,
    );
}

describe("OrchestrationProjectDetailPage a11y", () => {
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
        vi.mocked(listRuns).mockResolvedValue([]);
        vi.mocked(listApprovals).mockResolvedValue([]);
        vi.mocked(listProjectMilestones).mockResolvedValue([]);
        vi.mocked(getGateConfig).mockResolvedValue({
            autonomy_level: "assisted",
            approval_gates: [],
        });
    });

    it("workspace tabs pass axe", async () => {
        const { container } = renderProjectDetail();
        expect(await screen.findByRole("tab", { name: "Overview" })).toBeInTheDocument();
        await expectNoA11yViolations(container);
    });
});
