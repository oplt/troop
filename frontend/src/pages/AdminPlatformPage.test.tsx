import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "@mui/material/styles";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { lightTheme } from "../app/theme";
import AdminPlatformPage from "./AdminPlatformPage";
import {
    getPlatformConfig,
    listAdminEmailTemplates,
    listAdminFeatureFlags,
    listAdminPlans,
} from "../api/platform";

vi.mock("../api/platform", () => ({
    getPlatformConfig: vi.fn(),
    listAdminPlans: vi.fn(),
    listAdminFeatureFlags: vi.fn(),
    listAdminEmailTemplates: vi.fn(),
    updatePlatformConfig: vi.fn(),
    createAdminPlan: vi.fn(),
    updateAdminPlan: vi.fn(),
    createAdminFeatureFlag: vi.fn(),
    updateAdminFeatureFlag: vi.fn(),
    createAdminEmailTemplate: vi.fn(),
    updateAdminEmailTemplate: vi.fn(),
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
            <ThemeProvider theme={lightTheme}>
                <MemoryRouter>
                    <AdminPlatformPage />
                </MemoryRouter>
            </ThemeProvider>
        </QueryClientProvider>,
    );
}

describe("AdminPlatformPage", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.mocked(getPlatformConfig).mockResolvedValue({
            app_name: "Troop",
            core_domain_singular: "Project",
            core_domain_plural: "Projects",
            module_pack: "full_platform",
            enabled_modules: ["orchestration"],
            module_catalog: [
                {
                    key: "orchestration",
                    label: "Orchestration",
                    description: "Runs",
                    user_visible: true,
                    enabled: true,
                },
            ],
            available_module_packs: [
                {
                    key: "full_platform",
                    label: "Full platform",
                    description: "All modules",
                    modules: ["orchestration"],
                },
            ],
            mfa_enabled: false,
            module_overrides: {},
        });
        vi.mocked(listAdminPlans).mockResolvedValue([]);
        vi.mocked(listAdminFeatureFlags).mockResolvedValue([]);
        vi.mocked(listAdminEmailTemplates).mockResolvedValue([]);
    });

    it("renders platform configuration from mock API data", async () => {
        renderPage();
        expect(await screen.findByText("Platform")).toBeInTheDocument();
        expect(await screen.findByDisplayValue("Troop")).toBeInTheDocument();
        expect(screen.getByRole("heading", { name: "Subscription plans" })).toBeInTheDocument();
        expect(screen.getByRole("heading", { name: "Feature flags" })).toBeInTheDocument();
    });
});
