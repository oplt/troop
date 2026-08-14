import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "@mui/material/styles";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { lightTheme } from "../app/theme";
import { BrainstormDetailContent } from "../features/brainstorms/detail/BrainstormDetailContent";
import {
    getBrainstormDiscourseInsights,
    listAgents,
    listBrainstormMessages,
    listBrainstormParticipants,
    listProjectAgents,
    promoteBrainstorm,
    promoteBrainstormAdr,
    promoteBrainstormDocument,
    type Brainstorm,
} from "../api/orchestration";

vi.mock("../app/snackbarContext", () => ({
    useSnackbar: () => ({ showToast: vi.fn() }),
}));

vi.mock("../api/orchestration", () => ({
    listBrainstormParticipants: vi.fn(),
    listBrainstormMessages: vi.fn(),
    getBrainstormDiscourseInsights: vi.fn(),
    listAgents: vi.fn(),
    listProjectAgents: vi.fn(),
    promoteBrainstorm: vi.fn(),
    promoteBrainstormAdr: vi.fn(),
    promoteBrainstormDocument: vi.fn(),
    exportBrainstormArtifact: vi.fn(),
    startBrainstorm: vi.fn(),
    startBrainstormNextRound: vi.fn(),
    forceBrainstormSummary: vi.fn(),
    addBrainstormParticipant: vi.fn(),
    removeBrainstormParticipant: vi.fn(),
    updateBrainstormParticipant: vi.fn(),
}));

const brainstorm: Brainstorm = {
    id: "brain-1",
    project_id: "proj-1",
    task_id: null,
    initiator_user_id: "user-1",
    moderator_agent_id: null,
    topic: "Launch plan",
    status: "completed",
    mode: "debate",
    output_type: "recommendation",
    max_rounds: 4,
    stop_conditions: {},
    participant_count: 0,
    current_round: 2,
    consensus_status: "soft_consensus",
    latest_round_summary: null,
    summary: null,
    decision_log: [],
    final_recommendation: "Ship in phases",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-02T00:00:00Z",
};

function renderRoom() {
    const queryClient = new QueryClient({
        defaultOptions: {
            queries: { retry: false },
            mutations: { retry: false },
        },
    });

    return render(
        <QueryClientProvider client={queryClient}>
            <ThemeProvider theme={lightTheme}>
                <MemoryRouter>
                    <BrainstormDetailContent brainstormId="brain-1" brainstorm={brainstorm} />
                </MemoryRouter>
            </ThemeProvider>
        </QueryClientProvider>,
    );
}

describe("BrainstormDetailContent promotion flows", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.mocked(listBrainstormParticipants).mockResolvedValue([]);
        vi.mocked(listBrainstormMessages).mockResolvedValue([]);
        vi.mocked(getBrainstormDiscourseInsights).mockResolvedValue({
            message_count: 0,
            same_agent_streak_ratio: 0,
            top_repeated_terms: [],
            rounds_with_messages: 0,
            last_round_repetition_score: null,
            last_round_pairwise_min_similarity: null,
            consensus_kind: null,
            conflict_signal: null,
        });
        vi.mocked(listAgents).mockResolvedValue([]);
        vi.mocked(listProjectAgents).mockResolvedValue([]);
        vi.mocked(promoteBrainstorm).mockResolvedValue([{ id: "task-1" } as never]);
        vi.mocked(promoteBrainstormAdr).mockResolvedValue({ id: "adr-1" } as never);
        vi.mocked(promoteBrainstormDocument).mockResolvedValue({ id: "doc-1" } as never);
    });

    it("promotes brainstorm output to tasks", async () => {
        const user = userEvent.setup();
        renderRoom();

        await user.click(await screen.findByRole("button", { name: "Promote to task" }));

        await waitFor(() => {
            expect(promoteBrainstorm).toHaveBeenCalledWith("brain-1");
        });
    });

    it("promotes brainstorm output to ADR", async () => {
        const user = userEvent.setup();
        renderRoom();

        await user.click(await screen.findByRole("button", { name: "Promote to ADR" }));

        await waitFor(() => {
            expect(promoteBrainstormAdr).toHaveBeenCalledWith("brain-1");
        });
    });

    it("promotes brainstorm output to project document", async () => {
        const user = userEvent.setup();
        renderRoom();

        await user.click(await screen.findByRole("button", { name: "Promote to project document" }));

        await waitFor(() => {
            expect(promoteBrainstormDocument).toHaveBeenCalledWith("brain-1");
        });
    });
});
