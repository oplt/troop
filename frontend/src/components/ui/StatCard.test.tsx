import { render, screen } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";
import { describe, expect, it } from "vitest";
import { lightTheme } from "../../app/theme";
import { StatCard } from "./StatCard";

describe("StatCard", () => {
    it("exposes contextual details to keyboard and assistive-technology users", () => {
        render(
            <ThemeProvider theme={lightTheme}>
                <StatCard label="Active runs" value={3} info="Runs currently in progress." icon={<span aria-hidden="true">•</span>} />
            </ThemeProvider>,
        );

        expect(screen.getByRole("img", { name: "Active runs details" })).toBeInTheDocument();
    });
});
