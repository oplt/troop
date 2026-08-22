import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "@mui/material/styles";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { lightTheme } from "../app/theme";
import { AdminSettingsContent } from "../features/settings/AdminSettingsContent";
import type { DatabaseSetting } from "../api/settings";
import { listGithubConnections, listProviders } from "../api/orchestration";

vi.mock("../api/orchestration", () => ({
    listProviders: vi.fn(),
    listGithubConnections: vi.fn(),
}));

vi.mock("../features/settings/database/DatabaseSettingsPanel", () => ({
    DatabaseSettingsPanel: ({
        onDirtyChange,
    }: {
        settings: DatabaseSetting[];
        onDirtyChange: (dirty: boolean) => void;
    }) => (
        <button type="button" onClick={() => onDirtyChange(true)}>
            Mark parameters dirty
        </button>
    ),
}));

vi.mock("../pages/AdminPlatformPage", () => ({ default: () => <div>Platform panel</div> }));
vi.mock("../pages/AdminUsersPage", () => ({ default: () => <div>Users panel</div> }));
vi.mock("../pages/CompaniesPage", () => ({ CompaniesPanel: () => <div>Companies panel</div> }));
vi.mock("../features/settings/github/GithubSyncPanel", () => ({ GithubSyncPanel: () => <div>GitHub panel</div> }));
vi.mock("../pages/ProviderSettingsPanel", () => ({ ProviderSettingsPanel: () => <div>Providers panel</div> }));
vi.mock("../pages/ProfilePage", () => ({ ProfileContent: () => <div>Profile panel</div> }));

const databaseSettings: DatabaseSetting[] = [
    {
        id: "setting-1",
        key: "MAX_RETRIES",
        value: "3",
        description: "Retry cap",
        updated_at: "2026-01-01T00:00:00Z",
    },
];

function renderSettings(activeTab: "database" | "providers" = "database", onTabChange = vi.fn()) {
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
                    <AdminSettingsContent
                        databaseSettings={databaseSettings}
                        databaseErrorMessage=""
                        hasDatabaseError={false}
                        activeTab={activeTab}
                        onTabChange={onTabChange}
                    />
                </MemoryRouter>
            </ThemeProvider>
        </QueryClientProvider>,
    );
}

describe("AdminSettingsContent dirty-tab guard", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.mocked(listProviders).mockResolvedValue([]);
        vi.mocked(listGithubConnections).mockResolvedValue([]);
    });

    it("blocks tab changes when database parameters are dirty", async () => {
        const user = userEvent.setup();
        const onTabChange = vi.fn();
        renderSettings("database", onTabChange);

        await user.click(screen.getByRole("button", { name: "Mark parameters dirty" }));
        expect(screen.getByText(/unsaved parameter edits/i)).toBeInTheDocument();

        await user.click(screen.getByRole("tab", { name: /AI providers/i }));
        expect(onTabChange).not.toHaveBeenCalled();
        expect(await screen.findByText("Leave without saving?")).toBeInTheDocument();
    });

    it("allows leaving database tab after confirming discard", async () => {
        const user = userEvent.setup();
        const onTabChange = vi.fn();
        renderSettings("database", onTabChange);

        await user.click(screen.getByRole("button", { name: "Mark parameters dirty" }));
        await user.click(screen.getByRole("tab", { name: /AI providers/i }));
        await user.click(screen.getByRole("button", { name: "Leave" }));

        await waitFor(() => {
            expect(onTabChange).toHaveBeenCalledWith("providers");
        });
    });
});
