import { describe, expect, it } from "vitest";

import { buildHierarchyValidationIssues } from "./validation";

describe("hierarchy validation", () => {
    it("requires a reviewer and a parent for non-manager nodes", () => {
        const issues = buildHierarchyValidationIssues([
            { id: "manager", data: { name: "Manager", role: "manager" } },
            { id: "worker", data: { name: "Worker", role: "specialist" } },
        ], []);

        expect(issues.map((issue) => issue.id)).toEqual(expect.arrayContaining(["reviewer-role-required", "orphan-worker"]));
    });

    it("detects self-loops and missing escalation targets", () => {
        const issues = buildHierarchyValidationIssues([
            { id: "manager", data: { name: "Manager", role: "manager", escalationPath: "missing" } },
        ], [{ id: "loop", source: "manager", target: "manager" }]);

        expect(issues.map((issue) => issue.id)).toEqual(expect.arrayContaining(["self-loop-loop", "invalid-escalation-manager"]));
    });
});
