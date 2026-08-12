import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TaskIntelligencePanel } from "./TaskIntelligencePanel";
import * as workforceApi from "../../api/workforce";

vi.mock("../../api/workforce", () => ({
    analyzeTask: vi.fn(),
    findSkillMatches: vi.fn(),
    generateMissingSkills: vi.fn(),
    findAgentMatches: vi.fn(),
    assembleAgent: vi.fn(),
    getTaskAnalysis: vi.fn(),
    getLastSkillGap: vi.fn(),
}));

vi.mock("../../app/snackbarContext", () => ({
    useSnackbar: () => ({
        showToast: vi.fn(),
    }),
}));

function renderPanel() {
    const queryClient = new QueryClient({
        defaultOptions: {
            queries: { retry: false },
            mutations: { retry: false },
        },
    });

    return render(
        <QueryClientProvider client={queryClient}>
            <TaskIntelligencePanel projectId="test-project" taskId="test-task" />
        </QueryClientProvider>,
    );
}

describe("TaskIntelligencePanel", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.mocked(workforceApi.getTaskAnalysis).mockRejectedValue(new Error("Not analyzed yet"));
    });

    it("renders action buttons", () => {
        renderPanel();

        expect(screen.getByRole("button", { name: /analyze task/i })).toBeInTheDocument();
        expect(screen.getByRole("button", { name: /find skills/i })).toBeInTheDocument();
        expect(screen.getByRole("button", { name: /generate missing skills/i })).toBeInTheDocument();
        expect(screen.getByRole("button", { name: /recommend agent/i })).toBeInTheDocument();
        expect(screen.getByRole("button", { name: /create agent/i })).toBeInTheDocument();
    });

    it("shows empty state when no data", () => {
        renderPanel();

        expect(
            screen.getByText(/click a button above to start analyzing this task/i),
        ).toBeInTheDocument();
    });

    it("calls analyzeTask when Analyze button is clicked", async () => {
        const mockAnalysis = {
            id: "a1",
            task_id: "test-task",
            project_id: "test-project",
            analyzer_version: "1.0.0",
            model_name: null,
            content_fingerprint: "abc",
            objective: "Ship tests",
            task_category: "software_engineering",
            risk_level: "medium",
            autonomy_recommendation: "semi-autonomous",
            required_capabilities_json: ["python", "testing"],
            required_tools_json: [],
            knowledge_requirements_json: [],
            expected_artifacts_json: [],
            acceptance_criteria_json: [],
            review_requirements_json: [],
            approval_requirements_json: [],
            required_capabilities: ["python", "testing"],
            covered_requirements: ["unit tests"],
            missing_requirements: ["integration tests"],
            risk_factors: ["medium"],
            created_at: "2026-08-12T00:00:00Z",
        };

        vi.mocked(workforceApi.analyzeTask).mockResolvedValue(mockAnalysis);

        renderPanel();

        const analyzeButton = screen.getByRole("button", { name: /analyze task/i });
        await userEvent.click(analyzeButton);

        await waitFor(() => {
            expect(workforceApi.analyzeTask).toHaveBeenCalledWith("test-task");
        });
    });

    it("displays analysis results after successful analysis", async () => {
        const mockAnalysis = {
            id: "a1",
            task_id: "test-task",
            project_id: "test-project",
            analyzer_version: "1.0.0",
            model_name: null,
            content_fingerprint: "abc",
            objective: "Ship tests",
            task_category: "software_engineering",
            risk_level: "medium",
            autonomy_recommendation: "semi-autonomous",
            required_capabilities_json: ["python", "testing"],
            required_tools_json: [],
            knowledge_requirements_json: [],
            expected_artifacts_json: [],
            acceptance_criteria_json: [],
            review_requirements_json: [],
            approval_requirements_json: [],
            required_capabilities: ["python", "testing"],
            covered_requirements: ["unit tests"],
            missing_requirements: ["integration tests"],
            risk_factors: ["medium"],
            created_at: "2026-08-12T00:00:00Z",
        };

        vi.mocked(workforceApi.analyzeTask).mockResolvedValue(mockAnalysis);
        vi.mocked(workforceApi.getTaskAnalysis).mockResolvedValue(mockAnalysis);

        renderPanel();

        await waitFor(() => {
            expect(screen.getByText(/analysis results/i)).toBeInTheDocument();
        });
    });

    it("calls findSkillMatches when Find Skills button is clicked", async () => {
        const mockMatches = [
            {
                skill_id: "skill-1",
                skill_slug: "python-testing",
                skill_name: "Python Testing",
                skill_scope: "organization" as const,
                scope: "organization",
                status: "active",
                score: 0.85,
                match_score: 0.85,
                coverage_percentage: 80,
                matched_capabilities: ["python", "testing"],
                explanation: "Good match for testing requirements",
            },
        ];

        vi.mocked(workforceApi.findSkillMatches).mockResolvedValue(mockMatches);

        renderPanel();

        const findSkillsButton = screen.getByRole("button", { name: /find skills/i });
        await userEvent.click(findSkillsButton);

        await waitFor(() => {
            expect(workforceApi.findSkillMatches).toHaveBeenCalledWith("test-task");
        });
    });
});
