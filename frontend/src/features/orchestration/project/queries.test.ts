import { describe, expect, it } from "vitest";

import { isProjectDetailSectionActive } from "./queries";

describe("project detail query ownership", () => {
    const state = {
        tab: "knowledge" as const,
        workView: "board" as const,
        knowledgeView: "memory" as const,
        knowledgeQuery: "retention",
        includeDecisionRecall: true,
        mergeTaskId: null,
    };

    it("activates only the owning feature sections", () => {
        expect(isProjectDetailSectionActive(state, "knowledge")).toBe(true);
        expect(isProjectDetailSectionActive(state, "memory")).toBe(true);
        expect(isProjectDetailSectionActive(state, "integrations")).toBe(false);
        expect(isProjectDetailSectionActive(state, "board")).toBe(false);
        expect(isProjectDetailSectionActive(state, "agents")).toBe(false);
    });
});
