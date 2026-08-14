import { beforeEach, describe, expect, it, vi } from "vitest";

import {
    listAgents,
    listAgentTemplates,
    listModelCapabilities,
    listOrchestrationProjects,
    listProviders,
    listRuns,
    listSkillCatalog,
    listTeamProfiles,
    listTeamTemplates,
} from "../../api/orchestration";

import { hierarchyApi } from "./api";

vi.mock("../../api/orchestration", () => ({
    listAgents: vi.fn(),
    listAgentTemplates: vi.fn(),
    listModelCapabilities: vi.fn(),
    listOrchestrationProjects: vi.fn(),
    listProviders: vi.fn(),
    listRuns: vi.fn(),
    listSkillCatalog: vi.fn(),
    listTeamProfiles: vi.fn(),
    listTeamTemplates: vi.fn(),
}));

describe("hierarchy api façade", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.mocked(listAgents).mockResolvedValue([]);
        vi.mocked(listAgentTemplates).mockResolvedValue([]);
        vi.mocked(listModelCapabilities).mockResolvedValue([]);
        vi.mocked(listOrchestrationProjects).mockResolvedValue([]);
        vi.mocked(listProviders).mockResolvedValue([]);
        vi.mocked(listRuns).mockResolvedValue([]);
        vi.mocked(listSkillCatalog).mockResolvedValue([]);
        vi.mocked(listTeamProfiles).mockResolvedValue([]);
        vi.mocked(listTeamTemplates).mockResolvedValue([]);
    });

    it("delegates list reads to the legacy orchestration client", async () => {
        await hierarchyApi.listAgents("project-1");
        await hierarchyApi.listRuns("project-1");
        await hierarchyApi.listOrchestrationProjects();

        expect(listAgents).toHaveBeenCalledWith("project-1");
        expect(listRuns).toHaveBeenCalledWith("project-1");
        expect(listOrchestrationProjects).toHaveBeenCalled();
    });

    it("supports global agent reads without a project id", async () => {
        await hierarchyApi.listAgents();
        expect(listAgents).toHaveBeenCalledWith(undefined);
    });
});
