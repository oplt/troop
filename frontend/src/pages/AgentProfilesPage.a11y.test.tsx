import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "@mui/material/styles";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { lightTheme } from "../app/theme";
import { expectNoA11yViolations } from "../test/a11y";
import AgentProfilesPage from "./AgentProfilesPage";
import {
    listAgentTemplates,
    listAgentVersions,
    listAgents,
    listOrchestrationProjects,
    listTools,
} from "../api/orchestration";

vi.mock("../api/orchestration", () => ({
    listAgentTemplates: vi.fn(),
    listAgentVersions: vi.fn(),
    listAgents: vi.fn(),
    listOrchestrationProjects: vi.fn(),
    listTools: vi.fn(),
    activateAgent: vi.fn(),
    createAgent: vi.fn(),
    createAgentFromTemplate: vi.fn(),
    duplicateAgent: vi.fn(),
    testRunAgent: vi.fn(),
    updateAgent: vi.fn(),
    validateAgentContract: vi.fn(),
}));

function renderPage() {
    const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    return render(
        <QueryClientProvider client={queryClient}>
            <ThemeProvider theme={lightTheme}>
                <MemoryRouter>
                    <AgentProfilesPage />
                </MemoryRouter>
            </ThemeProvider>
        </QueryClientProvider>,
    );
}

describe("Agents accessibility", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.mocked(listOrchestrationProjects).mockResolvedValue([]);
        vi.mocked(listAgents).mockResolvedValue([]);
        vi.mocked(listTools).mockResolvedValue([]);
        vi.mocked(listAgentTemplates).mockResolvedValue([]);
        vi.mocked(listAgentVersions).mockResolvedValue([]);
    });

    it("has no serious axe violations", async () => {
        const { container } = renderPage();
        expect(await screen.findByText("Agents")).toBeInTheDocument();
        await expectNoA11yViolations(container);
    });
});
