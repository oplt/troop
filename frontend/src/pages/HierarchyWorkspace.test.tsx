import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import HierarchyWorkspace from "./hierarchy/HierarchyWorkspace";
import { buildHierarchyAgentFixture } from "../features/hierarchy/viewModel.fixtures";

vi.mock("../app/snackbarContext", () => ({
    useSnackbar: () => ({ showToast: vi.fn() }),
}));

vi.mock("@xyflow/react", async (importOriginal) => {
    const actual = await importOriginal<typeof import("@xyflow/react")>();
    return {
        ...actual,
        ReactFlowProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
        useNodesState: (initial: unknown) => [initial, vi.fn(), vi.fn()],
        useEdgesState: (initial: unknown) => [initial, vi.fn(), vi.fn()],
    };
});

vi.mock("./hierarchy/HierarchyReactFlowCanvas", () => ({
    HierarchyTeamReactFlow: () => <div>Hierarchy canvas</div>,
    HierarchyTemplatePreviewFlow: () => <div>Template preview</div>,
}));

vi.mock("../api/orchestration", () => {
    const fn = vi.fn;
    return {
        addProjectAgent: fn(),
        createAgent: fn(),
        createAgentTemplate: fn(),
        createTeamProfileFromTemplate: fn(),
        createTeamTemplate: fn(),
        deleteAgentTemplate: fn(),
        deleteSkillPack: fn(),
        deleteTeamTemplate: fn(),
        listAgents: fn(),
        listAgentTemplates: fn(),
        listModelCapabilities: fn(),
        listOrchestrationProjects: fn(),
        listProjectAgents: fn(),
        listProviders: fn(),
        listRuns: fn(),
        listSkillCatalog: fn(),
        listTeamProfiles: fn(),
        listTeamTemplates: fn(),
        updateAgent: fn(),
        updateAgentTemplate: fn(),
        updateHierarchyPolicy: fn(),
        updateOrchestrationProject: fn(),
        updateProjectAgent: fn(),
        updateSkillPack: fn(),
        updateTeamTemplate: fn(),
    };
});

import {
    listAgentTemplates,
    listAgents,
    listModelCapabilities,
    listOrchestrationProjects,
    listProviders,
    listRuns,
    listSkillCatalog,
    listTeamProfiles,
    listTeamTemplates,
} from "../api/orchestration";

function renderHierarchy(initialEntry = "/hierarchy") {
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
                    <Route path="/hierarchy" element={<HierarchyWorkspace />} />
                </Routes>
            </MemoryRouter>
        </QueryClientProvider>,
    );
}

describe("HierarchyWorkspace", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        window.localStorage.setItem("troop:hierarchy-builder:selected-project:v1", "project-1");
        vi.mocked(listAgents).mockImplementation(async (projectId?: string) =>
            projectId ? [buildHierarchyAgentFixture({ project_id: projectId })] : [],
        );
        vi.mocked(listAgentTemplates).mockResolvedValue([]);
        vi.mocked(listSkillCatalog).mockResolvedValue([]);
        vi.mocked(listTeamTemplates).mockResolvedValue([]);
        vi.mocked(listRuns).mockResolvedValue([]);
        vi.mocked(listTeamProfiles).mockResolvedValue([]);
        vi.mocked(listProviders).mockResolvedValue([]);
        vi.mocked(listModelCapabilities).mockResolvedValue([]);
        vi.mocked(listOrchestrationProjects).mockResolvedValue([
            {
                id: "project-1",
                name: "Launch Ops",
                slug: "launch-ops",
                description: null,
                status: "active",
                goals_markdown: "",
                settings: {},
                memory_scope: "project",
                knowledge_summary: null,
                company_id: null,
                created_at: "2026-06-18T00:00:00.000Z",
                updated_at: "2026-06-18T00:00:00.000Z",
            },
        ]);
    });

    it("renders the team builder tab on /hierarchy", async () => {
        renderHierarchy();

        expect(await screen.findByRole("tab", { name: "Team Builder" })).toHaveAttribute("aria-selected", "true");
        expect(await screen.findByRole("button", { name: "Add agent" })).toBeInTheDocument();
    });

    it("switches to the templates library tab", async () => {
        const user = userEvent.setup();
        renderHierarchy();

        await screen.findByRole("tab", { name: "Templates" });
        await user.click(screen.getByRole("tab", { name: "Templates" }));

        await waitFor(() => {
            expect(screen.getByText("Agent templates")).toBeInTheDocument();
        });
    });

    it("opens the add-agent dialog from the team builder surface", async () => {
        const user = userEvent.setup();
        renderHierarchy();

        await screen.findByRole("button", { name: "Add agent" });
        await user.click(screen.getByRole("button", { name: "Add agent" }));

        expect(await screen.findByRole("dialog")).toBeInTheDocument();
        expect(screen.getByText("Add agent to team")).toBeInTheDocument();
    });
});
