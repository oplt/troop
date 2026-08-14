import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "@mui/material/styles";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { lightTheme } from "../app/theme";
import { expectNoA11yViolations } from "../test/a11y";
import VerifyEmailPage from "./VerifyEmailPage";
import { getPlatformMetadata } from "../api/platform";

vi.mock("../api/platform", () => ({
    getPlatformMetadata: vi.fn(),
}));

vi.mock("../api/auth", () => ({
    verifyEmail: vi.fn(),
    resendVerification: vi.fn(),
}));

function renderPage() {
    const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    return render(
        <QueryClientProvider client={queryClient}>
            <ThemeProvider theme={lightTheme}>
                <MemoryRouter>
                    <VerifyEmailPage />
                </MemoryRouter>
            </ThemeProvider>
        </QueryClientProvider>,
    );
}

describe("Verify email accessibility", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.mocked(getPlatformMetadata).mockResolvedValue({
            app_name: "Troop",
            core_domain_singular: "project",
            core_domain_plural: "projects",
            module_pack: "default",
            enabled_modules: [],
            module_catalog: [],
            available_module_packs: [],
            mfa_enabled: false,
        });
    });

    it("has no serious axe violations on inbox state", async () => {
        const { container } = renderPage();
        expect(await screen.findByText("Check your inbox")).toBeInTheDocument();
        await expectNoA11yViolations(container);
    });
});
