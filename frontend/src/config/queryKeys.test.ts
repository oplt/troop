import { describe, expect, it } from "vitest";
import { queryKeys } from "./queryKeys";

describe("queryKeys", () => {
    it("builds stable orchestration project keys", () => {
        expect(queryKeys.orchestration.project("abc")).toEqual(["orchestration", "project", "abc"]);
        expect(queryKeys.orchestration.projectTasks("abc")).toEqual(["orchestration", "project", "abc", "tasks"]);
        expect(queryKeys.orchestration.projectRuns("abc")).toEqual(["orchestration", "project", "abc", "runs"]);
    });

    it("includes search terms in semantic keys", () => {
        expect(queryKeys.orchestration.semantic("p1", "auth", "jwt")).toEqual([
            "orchestration",
            "semantic",
            "p1",
            "auth",
            "jwt",
        ]);
    });

    it("builds semantic conflict and episodic archive keys", () => {
        expect(queryKeys.orchestration.semanticConflicts("p1")).toEqual([
            "orchestration",
            "semantic-conflicts",
            "p1",
        ]);
        expect(queryKeys.orchestration.episodicArchives("p1")).toEqual([
            "orchestration",
            "episodic-archives",
            "p1",
        ]);
    });

    it("uses root keys for broad invalidation", () => {
        expect(queryKeys.orchestration.semanticRoot("p1")).toEqual(["orchestration", "semantic", "p1"]);
        expect(queryKeys.orchestration.episodicRoot("p1")).toEqual(["orchestration", "episodic", "p1"]);
    });

    it("centralizes dashboard keys", () => {
        expect(queryKeys.orchestration.projects).toEqual(["orchestration", "projects"]);
        expect(queryKeys.orchestration.overview).toEqual(["orchestration", "overview"]);
        expect(queryKeys.orchestration.executionInsights(14)).toEqual([
            "orchestration",
            "execution-insights",
            14,
        ]);
    });

    it("centralizes project-detail dependent keys", () => {
        expect(queryKeys.orchestration.projectKnowledge("p1", "auth", true)).toEqual([
            "orchestration",
            "project",
            "p1",
            "knowledge",
            "auth",
            true,
        ]);
        expect(queryKeys.orchestration.projectKnowledge("p1")).toEqual([
            "orchestration",
            "project",
            "p1",
            "knowledge",
        ]);
        expect(queryKeys.orchestration.projectTaskExecution("p1", "t1")).toEqual([
            "orchestration",
            "project",
            "p1",
            "task-exec",
            "t1",
        ]);
    });
});
