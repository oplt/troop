import { expect } from "vitest";
import { configureAxe, toHaveNoViolations } from "jest-axe";
import type { AxeResults } from "axe-core";

expect.extend(toHaveNoViolations);

/** Shared axe config: WCAG 2.1 AA, skip color-contrast in jsdom (unreliable). */
export const axe = configureAxe({
    rules: {
        // jsdom lacks layout/paint; contrast checks are flaky / false-positive there.
        "color-contrast": { enabled: false },
    },
});

export async function expectNoA11yViolations(container: Element) {
    const results = (await axe(container)) as AxeResults;
    expect(results).toHaveNoViolations();
}
