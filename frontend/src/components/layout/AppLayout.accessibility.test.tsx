import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ThemeProvider } from "@mui/material/styles";
import { lightTheme } from "../../app/theme";
import { ColorModeContext } from "../../app/colorModeContext";
import { ThemeToggle } from "./AppLayout";

describe("AppLayout icon controls", () => {
    it("gives the theme cycle a stable keyboard-accessible name", () => {
        render(
            <ThemeProvider theme={lightTheme}>
                <ColorModeContext.Provider value={{ colorMode: "light", setColorMode: vi.fn() }}>
                    <ThemeToggle />
                </ColorModeContext.Provider>
            </ThemeProvider>,
        );

        expect(screen.getByRole("button", { name: "Switch theme to dark" })).toBeInTheDocument();
    });
});
