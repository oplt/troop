import { describe, expect, it } from "vitest";

import {
    parseProjectDetailTab,
    projectDetailTabSideEffects,
    syncProjectDetailTabFromSearchParam,
    withProjectDetailTab,
} from "./routing";

describe("project detail routing", () => {
    it("defaults unknown tab params to overview", () => {
        expect(parseProjectDetailTab(null)).toBe("overview");
        expect(parseProjectDetailTab("invalid")).toBe("overview");
    });

    it("preserves supported tab params", () => {
        expect(parseProjectDetailTab("board")).toBe("board");
        expect(parseProjectDetailTab("memory")).toBe("memory");
    });

    it("writes tab params without dropping existing search params", () => {
        const params = new URLSearchParams("task=task-1&tab=overview");
        expect(withProjectDetailTab(params, "runs").toString()).toBe("task=task-1&tab=runs");
    });

    it("ignores invalid URL sync values", () => {
        expect(syncProjectDetailTabFromSearchParam("bogus")).toBeNull();
        expect(syncProjectDetailTabFromSearchParam("agents")).toBe("agents");
    });

    it("maps tab changes to sub-view side effects", () => {
        expect(projectDetailTabSideEffects("board")).toEqual({ workView: "board" });
        expect(projectDetailTabSideEffects("settings")).toEqual({
            teamView: "settings",
            knowledgeView: "sources",
        });
        expect(projectDetailTabSideEffects("overview")).toEqual({});
    });
});
