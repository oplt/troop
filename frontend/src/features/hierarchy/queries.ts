import { useQuery } from "@tanstack/react-query";

import { queryKeys } from "../../config/queryKeys";
import { hierarchyApi } from "./api";

/** All server-state reads owned by the hierarchy library/editor feature. */
export function useHierarchyQueries(projectId: string) {
    return {
        agents: useQuery({
            queryKey: queryKeys.orchestration.agents(),
            queryFn: () => hierarchyApi.listAgents(),
        }),
        runs: useQuery({
            queryKey: queryKeys.orchestration.hierarchyRuns,
            queryFn: () => hierarchyApi.listRuns(),
        }),
        templates: useQuery({
            queryKey: queryKeys.orchestration.agentTemplates,
            queryFn: hierarchyApi.listAgentTemplates,
        }),
        skills: useQuery({
            queryKey: queryKeys.orchestration.skillCatalog,
            queryFn: hierarchyApi.listSkillCatalog,
        }),
        teamTemplates: useQuery({
            queryKey: queryKeys.orchestration.teamTemplates,
            queryFn: hierarchyApi.listTeamTemplates,
        }),
        teamProfiles: useQuery({
            queryKey: queryKeys.orchestration.teamProfiles,
            queryFn: hierarchyApi.listTeamProfiles,
        }),
        orchestrationProjects: useQuery({
            queryKey: queryKeys.orchestration.projects,
            queryFn: hierarchyApi.listOrchestrationProjects,
        }),
        hierarchyAgents: useQuery({
            queryKey: queryKeys.orchestration.hierarchyAgents(projectId || "global"),
            queryFn: () => hierarchyApi.listAgents(projectId || undefined),
        }),
        providerConfigs: useQuery({
            queryKey: queryKeys.orchestration.providers,
            queryFn: () => hierarchyApi.listProviders(),
        }),
        modelCapabilities: useQuery({
            queryKey: queryKeys.orchestration.providerModelCapabilities,
            queryFn: hierarchyApi.listModelCapabilities,
        }),
    };
}
