import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import NotificationsPage from "./NotificationsPage";
import { getNotifications, getPreferences } from "../api/notifications";

vi.mock("../api/notifications", () => ({
    getNotifications: vi.fn(),
    getPreferences: vi.fn(),
    markRead: vi.fn(),
    updatePreferences: vi.fn(),
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
                <NotificationsPage />
            </MemoryRouter>
        </QueryClientProvider>,
    );
}

describe("NotificationsPage", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.mocked(getPreferences).mockResolvedValue({
            email_enabled: true,
            push_enabled: true,
            marketing_enabled: false,
        });
        vi.mocked(getNotifications).mockResolvedValue([
            {
                id: "n1",
                type: "test",
                title: "Hello",
                body_preview: "Preview body",
                is_read: false,
                created_at: "2026-08-14T10:00:00Z",
            },
            {
                id: "n2",
                type: "ops",
                title: "Quiet update",
                body_preview: "Already processed",
                is_read: true,
                created_at: "2026-08-13T10:00:00Z",
            },
        ]);
    });

    it("filters notifications and shows body_preview", async () => {
        const user = userEvent.setup();
        renderPage();

        expect(await screen.findByText("Hello")).toBeInTheDocument();
        expect(screen.getByText("Preview body")).toBeInTheDocument();
        expect(screen.getByText("Quiet update")).toBeInTheDocument();

        await user.type(screen.getByLabelText("Search"), "preview");
        expect(screen.getByText("Hello")).toBeInTheDocument();
        expect(screen.queryByText("Quiet update")).not.toBeInTheDocument();
    });
});
