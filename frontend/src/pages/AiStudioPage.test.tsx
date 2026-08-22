import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "@mui/material/styles";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { lightTheme } from "../app/theme";
import AiStudioPage from "./AiStudioPage";
import {
    createAiDocument,
    createPromptTemplate,
    getAiOverview,
    listAiEvaluationRuns,
    listAiReviews,
} from "../api/ai";

vi.mock("../api/ai", () => ({
    getAiOverview: vi.fn(),
    listAiReviews: vi.fn(),
    listAiEvaluationRuns: vi.fn(),
    listPromptVersions: vi.fn(),
    listAiDatasetCases: vi.fn(),
    createPromptTemplate: vi.fn(),
    createPromptVersion: vi.fn(),
    createAiRun: vi.fn(),
    createAiDocument: vi.fn(),
    uploadAiDocument: vi.fn(),
    createAiReview: vi.fn(),
    decideAiReview: vi.fn(),
    createAiFeedback: vi.fn(),
    createAiDataset: vi.fn(),
    createAiDatasetCase: vi.fn(),
    runAiEvaluation: vi.fn(),
    updatePromptTemplate: vi.fn(),
    updatePromptVersion: vi.fn(),
}));

function renderPage(initialEntry = "/ai-studio") {
    const queryClient = new QueryClient({
        defaultOptions: {
            queries: { retry: false },
            mutations: { retry: false },
        },
    });

    return render(
        <QueryClientProvider client={queryClient}>
            <ThemeProvider theme={lightTheme}>
                <MemoryRouter initialEntries={[initialEntry]}>
                    <AiStudioPage />
                </MemoryRouter>
            </ThemeProvider>
        </QueryClientProvider>,
    );
}

describe("AiStudioPage", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.mocked(getAiOverview).mockResolvedValue({
            providers: [],
            prompt_templates: [{
                id: "tmpl-1",
                key: "demo",
                name: "Demo prompt",
                description: "",
                is_active: true,
                active_version_id: null,
                created_at: "",
                updated_at: "",
            }],
            recent_runs: [],
            documents: [],
            datasets: [],
        });
        vi.mocked(listAiReviews).mockResolvedValue([]);
        vi.mocked(listAiEvaluationRuns).mockResolvedValue([]);
    });

    it("renders overview and prompt templates tab by default", async () => {
        renderPage();
        expect(await screen.findByText("AI Studio")).toBeInTheDocument();
        expect(await screen.findByText("Demo prompt")).toBeInTheDocument();
    });

    it("honors studio query param for tab selection", async () => {
        renderPage("/ai-studio?studio=documents");
        expect(await screen.findByText("AI Studio")).toBeInTheDocument();
        expect(screen.getByRole("tab", { name: /retrieval/i })).toHaveAttribute("aria-selected", "true");
    });

    it("renders reviews tab when studio query param is reviews", async () => {
        vi.mocked(listAiReviews).mockResolvedValue([
            {
                id: "review-1",
                run_id: "run-1",
                requested_by_user_id: "user-1",
                assigned_to_user_id: null,
                reviewed_by_user_id: null,
                status: "pending",
                reviewer_notes: null,
                corrected_output: null,
                created_at: "2026-01-01T00:00:00Z",
                updated_at: "2026-01-01T00:00:00Z",
            },
        ]);
        renderPage("/ai-studio?studio=reviews");
        expect(await screen.findByText("AI Studio")).toBeInTheDocument();
        expect(screen.getByRole("tab", { name: /reviews/i })).toHaveAttribute("aria-selected", "true");
        expect(await screen.findByText("Review queue")).toBeInTheDocument();
    });

    it("creates a prompt template from the prompts panel", async () => {
        const user = userEvent.setup();
        vi.mocked(createPromptTemplate).mockResolvedValue({
            id: "tmpl-new",
            key: "support-reply",
            name: "Support reply",
            description: "",
            is_active: true,
            active_version_id: null,
            created_at: "",
            updated_at: "",
        });

        renderPage();
        expect(await screen.findByText("AI Studio")).toBeInTheDocument();

        await user.type(screen.getByLabelText("Template key"), "support-reply");
        await user.type(screen.getByLabelText("Name"), "Support reply");
        await user.click(screen.getByRole("button", { name: "Create prompt template" }));

        await waitFor(() => {
            expect(createPromptTemplate).toHaveBeenCalled();
            expect(vi.mocked(createPromptTemplate).mock.calls[0][0]).toEqual({
                key: "support-reply",
                name: "Support reply",
                description: "",
            });
        });
    });

    it("creates a text document from the documents panel", async () => {
        const user = userEvent.setup();
        vi.mocked(createAiDocument).mockResolvedValue({
            document: {
                id: "doc-new",
                title: "Return policy",
                description: "",
                filename: null,
                content_type: "text/plain",
                size_bytes: 38,
                ingestion_status: "completed",
                metadata: {},
                chunk_count: 2,
                created_at: "",
                updated_at: "",
            },
            ingest_job_id: null,
            queued: false,
        });

        renderPage("/ai-studio?studio=documents");
        expect(await screen.findByText("Retrieval documents")).toBeInTheDocument();

        await user.type(screen.getByLabelText("Document title"), "Return policy");
        await user.type(screen.getByLabelText("Document content"), "Returns accepted within 30 days.");
        await user.click(screen.getByRole("button", { name: "Create text document" }));

        await waitFor(() => {
            expect(createAiDocument).toHaveBeenCalled();
            expect(vi.mocked(createAiDocument).mock.calls[0][0]).toEqual({
                title: "Return policy",
                description: "",
                content: "Returns accepted within 30 days.",
                content_type: "text/plain",
            });
        });
    });
});
