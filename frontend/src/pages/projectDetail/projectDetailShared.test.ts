import { describe, expect, it } from "vitest";

import type { OrchestrationTask } from "../../api/orchestration";

import { buildOrchestrationTaskFixture } from "../../features/orchestration/project/viewModel.fixtures";
import {
    buildTransitionOptions,
    readWorkspaceOverview,
    TASK_TRANSITION_MAP,
} from "./projectDetailShared";

function task(overrides: Partial<OrchestrationTask> = {}): OrchestrationTask {
    return buildOrchestrationTaskFixture(overrides);
}

describe("project detail shared view-model helpers", () => {
    it("reads workspace overview fields from project settings", () => {
        expect(
            readWorkspaceOverview({
                workspace_overview: {
                    executive_summary: "Summary",
                    current_focus: "Focus",
                    decision_focus: "Decision",
                },
            }),
        ).toEqual({
            executive_summary: "Summary",
            current_focus: "Focus",
            decision_focus: "Decision",
        });
    });

    it("blocks approval transitions until acceptance passes", () => {
        const options = buildTransitionOptions({
            task: task({ status: "needs_review" }),
            acceptancePassed: false,
            evidenceReadyForSync: true,
            evidenceReadyForArchive: true,
            hasIncompleteDependencies: false,
        });

        expect(options.find((option) => option.status === "approved")).toEqual({
            status: "approved",
            blocked: true,
            reason: "Acceptance gate must pass first.",
        });
    });

    it("keeps the task transition map aligned with backend statuses", () => {
        expect(Object.keys(TASK_TRANSITION_MAP)).toEqual(
            expect.arrayContaining(["backlog", "in_progress", "needs_review", "completed"]),
        );
    });
});
