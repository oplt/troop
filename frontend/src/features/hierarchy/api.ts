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

/** Read-only hierarchy API façade. Writes stay behind the legacy client until payload DTOs are migrated. */
export const hierarchyApi = {
    listAgents: (projectId?: string) => listAgents(projectId),
    listAgentTemplates: () => listAgentTemplates(),
    listModelCapabilities: () => listModelCapabilities(),
    listOrchestrationProjects: () => listOrchestrationProjects(),
    listProviders: () => listProviders(),
    listRuns: (projectId?: string) => listRuns(projectId),
    listSkillCatalog: () => listSkillCatalog(),
    listTeamProfiles: () => listTeamProfiles(),
    listTeamTemplates: () => listTeamTemplates(),
};
