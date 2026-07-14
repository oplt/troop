import { describe, expect, it } from "vitest";

import { projectMutationQueryKeys } from "./mutations";

describe("project mutation invalidation policy", () => {
    it("returns stable, scoped keys without raw orchestration literals", () => {
        const keys = projectMutationQueryKeys("project-1", "tasks", "runs", "tasks");
        expect(keys).toEqual(expect.arrayContaining([
            ["orchestration", "project", "project-1", "tasks"],
            ["orchestration", "project", "project-1", "dag-ready"],
            ["orchestration", "project", "project-1", "runs"],
        ]));
        expect(keys).toHaveLength(4);
    });
});
