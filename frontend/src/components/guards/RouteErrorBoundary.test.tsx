import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
import { RouteErrorBoundary } from "./RouteErrorBoundary";

function RouteContent({ shouldFail }: { shouldFail: boolean }) {
    if (shouldFail) {
        throw new Error("route exploded");
    }
    return <div>Healthy route</div>;
}

describe("RouteErrorBoundary", () => {
    it("clears a previous route error when navigation changes the reset key", () => {
        const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
        const view = render(
            <RouteErrorBoundary resetKey="first-route">
                <RouteContent shouldFail />
            </RouteErrorBoundary>,
        );

        expect(screen.getByText("Page failed to load")).toBeInTheDocument();

        view.rerender(
            <RouteErrorBoundary resetKey="second-route">
                <RouteContent shouldFail={false} />
            </RouteErrorBoundary>,
        );

        expect(screen.getByText("Healthy route")).toBeInTheDocument();
        consoleError.mockRestore();
    });
});
