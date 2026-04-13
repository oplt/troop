import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import AgentLibraryPage from "./AgentLibraryPage";
import { SnackbarContext } from "../app/snackbarContext";

vi.mock("../api/orchestration", () => ({
    listAgents: vi.fn(async () => []),
    listAgentTemplates: vi.fn(async () => []),
    listSkillCatalog: vi.fn(async () => []),
    listAgentVersions: vi.fn(async () => []),
    createAgent: vi.fn(),
    createAgentFromTemplate: vi.fn(),
    duplicateAgent: vi.fn(),
    activateAgent: vi.fn(),
    updateAgent: vi.fn(),
    testRunAgent: vi.fn(),
    importAgentMarkdown: vi.fn(),
    validateAgentMarkdown: vi.fn(),
}));

function renderPage() {
    const queryClient = new QueryClient();
    render(
        <MemoryRouter>
            <QueryClientProvider client={queryClient}>
                <SnackbarContext.Provider value={{ showToast: vi.fn() }}>
                    <AgentLibraryPage />
                </SnackbarContext.Provider>
            </QueryClientProvider>
        </MemoryRouter>
    );
}

describe("AgentLibraryPage", () => {
    it("renders the empty state", async () => {
        renderPage();

        expect(await screen.findByText("Agent Library")).toBeInTheDocument();
        expect(await screen.findByText("No agents yet")).toBeInTheDocument();
        expect(await screen.findByText("Skill catalog")).toBeInTheDocument();
    });
});
