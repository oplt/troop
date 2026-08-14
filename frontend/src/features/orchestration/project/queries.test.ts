import { describe, expect, it } from "vitest";

import { isProjectDetailSectionActive } from "./queries";

describe("project detail query ownership", () => {
    it("activates memory sections on memory tab", () => {
        const state = {
            tab: "memory" as const,
            workView: "board" as const,
            knowledgeView: "memory" as const,
            knowledgeQuery: "retention",
            includeDecisionRecall: true,
            mergeTaskId: null,
        };
        expect(isProjectDetailSectionActive(state, "memory")).toBe(true);
        expect(isProjectDetailSectionActive(state, "knowledge")).toBe(true);
        expect(isProjectDetailSectionActive(state, "board")).toBe(false);
        expect(isProjectDetailSectionActive(state, "agents")).toBe(false);
    });

    it("activates board work views", () => {
        const state = {
            tab: "board" as const,
            workView: "dependencies" as const,
            knowledgeView: "search" as const,
            knowledgeQuery: "",
            includeDecisionRecall: false,
            mergeTaskId: null,
        };
        expect(isProjectDetailSectionActive(state, "board")).toBe(true);
        expect(isProjectDetailSectionActive(state, "dependencies")).toBe(true);
        expect(isProjectDetailSectionActive(state, "work")).toBe(true);
        expect(isProjectDetailSectionActive(state, "runs")).toBe(false);
    });

    it("activates settings integrations and team sections", () => {
        const state = {
            tab: "settings" as const,
            workView: "board" as const,
            knowledgeView: "integrations" as const,
            knowledgeQuery: "",
            includeDecisionRecall: false,
            mergeTaskId: null,
        };
        expect(isProjectDetailSectionActive(state, "settings")).toBe(true);
        expect(isProjectDetailSectionActive(state, "integrations")).toBe(true);
        expect(isProjectDetailSectionActive(state, "team")).toBe(true);
        expect(isProjectDetailSectionActive(state, "runs")).toBe(false);
    });

    it("activates runs and activity on the runs tab", () => {
        const state = {
            tab: "runs" as const,
            workView: "board" as const,
            knowledgeView: "memory" as const,
            knowledgeQuery: "",
            includeDecisionRecall: false,
            mergeTaskId: null,
        };
        expect(isProjectDetailSectionActive(state, "runs")).toBe(true);
        expect(isProjectDetailSectionActive(state, "activity")).toBe(true);
        expect(isProjectDetailSectionActive(state, "board")).toBe(false);
    });
});
