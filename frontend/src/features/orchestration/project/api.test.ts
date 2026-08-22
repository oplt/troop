import { beforeEach, describe, expect, it, vi } from "vitest";

import {
    createOrchestrationTask,
    getOrchestrationProject,
    listOrchestrationTasks,
    listProjectMilestones,
} from "../../../api/orchestration";

import { buildProjectDetailResources, projectDetailApi } from "./api";
import {
    PROJECT_DETAIL_MILESTONE_FIXTURE,
    PROJECT_DETAIL_PROJECT_FIXTURE,
    PROJECT_DETAIL_RESOURCES_FIXTURE,
    PROJECT_DETAIL_TASK_FIXTURE,
    PROJECT_DETAIL_TASK_LIST_FIXTURE,
    PROJECT_TASK_PAYLOAD_FIXTURE,
} from "./viewModel.fixtures";

vi.mock("../../../api/orchestration", () => ({
    getOrchestrationProject: vi.fn(),
    listOrchestrationTasks: vi.fn(),
    listProjectMilestones: vi.fn(),
    createOrchestrationTask: vi.fn(),
}));

describe("project detail api façade", () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it("freezes the bundled project-detail resource shape", () => {
        expect(
            buildProjectDetailResources(
                PROJECT_DETAIL_PROJECT_FIXTURE,
                [PROJECT_DETAIL_TASK_LIST_FIXTURE],
                [PROJECT_DETAIL_MILESTONE_FIXTURE],
            ),
        ).toEqual(PROJECT_DETAIL_RESOURCES_FIXTURE);
    });

    it("delegates reads and writes to the legacy orchestration client", async () => {
        vi.mocked(getOrchestrationProject).mockResolvedValue(PROJECT_DETAIL_PROJECT_FIXTURE);
        vi.mocked(listOrchestrationTasks).mockResolvedValue([PROJECT_DETAIL_TASK_LIST_FIXTURE]);
        vi.mocked(listProjectMilestones).mockResolvedValue([PROJECT_DETAIL_MILESTONE_FIXTURE]);
        vi.mocked(createOrchestrationTask).mockResolvedValue(PROJECT_DETAIL_TASK_FIXTURE);

        await expect(projectDetailApi.getProject("project-1")).resolves.toEqual(PROJECT_DETAIL_PROJECT_FIXTURE);
        await expect(projectDetailApi.listTasks("project-1")).resolves.toEqual([PROJECT_DETAIL_TASK_LIST_FIXTURE]);
        await expect(projectDetailApi.listMilestones("project-1")).resolves.toEqual([PROJECT_DETAIL_MILESTONE_FIXTURE]);
        await expect(projectDetailApi.createTask("project-1", PROJECT_TASK_PAYLOAD_FIXTURE)).resolves.toEqual(
            PROJECT_DETAIL_TASK_FIXTURE,
        );

        expect(getOrchestrationProject).toHaveBeenCalledWith("project-1");
        expect(listOrchestrationTasks).toHaveBeenCalledWith("project-1");
        expect(listProjectMilestones).toHaveBeenCalledWith("project-1");
        expect(createOrchestrationTask).toHaveBeenCalledWith("project-1", PROJECT_TASK_PAYLOAD_FIXTURE);
    });
});
