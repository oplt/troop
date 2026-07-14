import { useQuery } from "@tanstack/react-query";

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
import { queryKeys } from "../../config/queryKeys";

/** All server-state reads owned by the hierarchy library/editor feature. */
export function useHierarchyQueries(projectId: string) {
    return {
        agents: useQuery({
            queryKey: queryKeys.orchestration.agents(),
            queryFn: () => listAgents(),
        }),
        runs: useQuery({
            queryKey: queryKeys.orchestration.hierarchyRuns,
            queryFn: () => listRuns(),
        }),
        templates: useQuery({
            queryKey: queryKeys.orchestration.agentTemplates,
            queryFn: listAgentTemplates,
        }),
        skills: useQuery({
            queryKey: queryKeys.orchestration.skillCatalog,
            queryFn: listSkillCatalog,
        }),
        teamTemplates: useQuery({
            queryKey: queryKeys.orchestration.teamTemplates,
            queryFn: listTeamTemplates,
        }),
        teamProfiles: useQuery({
            queryKey: queryKeys.orchestration.teamProfiles,
            queryFn: listTeamProfiles,
        }),
        orchestrationProjects: useQuery({
            queryKey: queryKeys.orchestration.projects,
            queryFn: listOrchestrationProjects,
        }),
        hierarchyAgents: useQuery({
            queryKey: queryKeys.orchestration.hierarchyAgents(projectId || "global"),
            queryFn: () => listAgents(projectId || undefined),
        }),
        providerConfigs: useQuery({
            queryKey: queryKeys.orchestration.providers,
            queryFn: () => listProviders(),
        }),
        modelCapabilities: useQuery({
            queryKey: queryKeys.orchestration.providerModelCapabilities,
            queryFn: listModelCapabilities,
        }),
    };
}
