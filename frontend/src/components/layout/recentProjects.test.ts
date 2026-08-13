import { describe, expect, it, beforeEach, afterEach, vi } from "vitest";
import { readRecentProjects, recordRecentProject } from "./recentProjects";

describe("recentProjects", () => {
    beforeEach(() => {
        localStorage.clear();
    });

    afterEach(() => {
        localStorage.clear();
        vi.restoreAllMocks();
    });

    it("records and dedupes recent projects with newest first", () => {
        recordRecentProject({ id: "a", name: "Alpha" });
        recordRecentProject({ id: "b", name: "Beta" });
        recordRecentProject({ id: "a", name: "Alpha Renamed" });
        const recent = readRecentProjects();
        expect(recent.map((item) => item.id)).toEqual(["a", "b"]);
        expect(recent[0].name).toBe("Alpha Renamed");
    });
});
