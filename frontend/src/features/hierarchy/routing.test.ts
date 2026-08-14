import { describe, expect, it } from "vitest";

import { resolveHierarchyActiveTab, resolveHierarchyBuilderTab } from "./routing";

describe("hierarchy routing", () => {
    it("maps canvas routes to the hierarchy tab", () => {
        expect(resolveHierarchyBuilderTab("/hierarchy")).toBe("hierarchy");
        expect(resolveHierarchyBuilderTab("/hierarchy-builder")).toBe("hierarchy");
        expect(resolveHierarchyBuilderTab("/agent-hierarchy")).toBe("hierarchy");
    });

    it("defaults non-canvas routes to the library tab", () => {
        expect(resolveHierarchyBuilderTab("/skills")).toBe("library");
        expect(resolveHierarchyBuilderTab("/projects/project-1")).toBe("library");
    });

    it("prefers manual tab selection over route defaults", () => {
        expect(resolveHierarchyActiveTab("hierarchy", "library")).toBe("library");
        expect(resolveHierarchyActiveTab("library", null)).toBe("library");
    });
});
