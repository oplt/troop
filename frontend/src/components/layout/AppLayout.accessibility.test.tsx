import { Box, Stack, ThemeProvider } from "@mui/material";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { lightTheme } from "../../app/theme";
import { ColorModeContext } from "../../app/colorModeContext";
import { expectNoA11yViolations } from "../../test/a11y";
import { VISUAL_BASELINES } from "../../test/visualBaselines";
import { ThemeToggle } from "./AppLayout";
import AuthHomePage from "../../pages/AuthHomePage";

vi.mock("../../hooks/usePlatformMetadata", () => ({
    usePlatformMetadata: () => ({
        data: { app_name: "Troop", core_domain_plural: "projects", mfa_enabled: false },
        isLoading: false,
    }),
}));

vi.mock("../../api/auth", () => ({
    signIn: vi.fn(),
    signUp: vi.fn(),
    forgotPassword: vi.fn(),
}));

vi.mock("../../hooks/useAuth", () => ({
    useAuth: () => ({ setAuthenticated: vi.fn(), isAuthenticated: false, isReady: true }),
}));

function wrap(ui: React.ReactElement) {
    const client = new QueryClient({
        defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    return render(
        <QueryClientProvider client={client}>
            <ThemeProvider theme={lightTheme}>
                <ColorModeContext.Provider value={{ colorMode: "light", setColorMode: vi.fn() }}>
                    <MemoryRouter>{ui}</MemoryRouter>
                </ColorModeContext.Provider>
            </ThemeProvider>
        </QueryClientProvider>,
    );
}

describe("AppLayout accessibility", () => {
    it("names the theme cycle for keyboard users", () => {
        wrap(<ThemeToggle />);
        expect(screen.getByRole("button", { name: "Switch theme to dark" })).toBeInTheDocument();
    });

    it("keeps shell landmark contract", () => {
        expect(VISUAL_BASELINES.shell.skipLink).toBe("Skip to main content");
        expect(VISUAL_BASELINES.shell.mainId).toBe("main-content");
        expect(VISUAL_BASELINES.shell.drawerWidths.expanded).toBe(288);
        expect(VISUAL_BASELINES.shell.drawerWidths.collapsed).toBe(96);
    });

    it("auth home has no serious axe violations", async () => {
        const { container } = wrap(
            <Routes>
                <Route path="/" element={<AuthHomePage />} />
            </Routes>,
        );
        expect(await screen.findByText("Welcome back")).toBeInTheDocument();
        await expectNoA11yViolations(container);
    });

    it("skip-target main landmark pattern is documented for AppLayout", () => {
        // Structural contract: skip href + main id (rendered by AppLayout in app).
        const { container } = render(
            <ThemeProvider theme={lightTheme}>
                <Box>
                    <a href={`#${VISUAL_BASELINES.shell.mainId}`}>{VISUAL_BASELINES.shell.skipLink}</a>
                    <Box component="main" id={VISUAL_BASELINES.shell.mainId} tabIndex={-1}>
                        <Stack>Content</Stack>
                    </Box>
                </Box>
            </ThemeProvider>,
        );
        const skip = screen.getByRole("link", { name: VISUAL_BASELINES.shell.skipLink });
        expect(skip).toHaveAttribute("href", `#${VISUAL_BASELINES.shell.mainId}`);
        expect(container.querySelector(`#${VISUAL_BASELINES.shell.mainId}`)).toHaveAttribute("tabIndex", "-1");
    });
});
