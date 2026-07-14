import type { QueryClient, QueryKey } from "@tanstack/react-query";

import { queryKeys } from "../../../config/queryKeys";

export type ProjectMutationScope =
    | "project"
    | "tasks"
    | "runs"
    | "agents"
    | "memory"
    | "knowledge"
    | "documents"
    | "repositories"
    | "approvals"
    | "brainstorms"
    | "milestones"
    | "decisions"
    | "integrations";

const scopeKeys = (projectId: string, scope: ProjectMutationScope): QueryKey[] => {
    switch (scope) {
        case "project": return [queryKeys.orchestration.project(projectId)];
        case "tasks": return [queryKeys.orchestration.projectTasks(projectId), queryKeys.orchestration.projectDagReady(projectId)];
        case "runs": return [queryKeys.orchestration.projectRuns(projectId), queryKeys.orchestration.hierarchyRuns];
        case "agents": return [queryKeys.orchestration.projectAgents(projectId), queryKeys.orchestration.agents(projectId), queryKeys.orchestration.agents()];
        case "memory": return [queryKeys.orchestration.projectMemory(projectId), queryKeys.orchestration.projectSemanticMemory(projectId)];
        case "knowledge": return [queryKeys.orchestration.projectKnowledge(projectId), queryKeys.orchestration.projectDecisions(projectId)];
        case "documents": return [queryKeys.orchestration.projectDocuments(projectId), queryKeys.orchestration.projectKnowledge(projectId)];
        case "repositories": return [queryKeys.orchestration.projectRepositories(projectId), queryKeys.orchestration.projectRepositoryIndexStatus(projectId)];
        case "approvals": return [queryKeys.orchestration.approvals, queryKeys.orchestration.approvalsPendingCount];
        case "brainstorms": return [queryKeys.orchestration.projectBrainstorms(projectId), queryKeys.orchestration.projectRuns(projectId)];
        case "milestones": return [queryKeys.orchestration.projectMilestones(projectId)];
        case "decisions": return [queryKeys.orchestration.projectDecisions(projectId), queryKeys.orchestration.projectKnowledge(projectId)];
        case "integrations": return [queryKeys.orchestration.projectIssues(projectId), queryKeys.orchestration.projectSyncEvents(projectId)];
    }
};

/** Central invalidation policy for project mutations; callers never hand-write raw key arrays. */
export async function invalidateProjectMutation(
    queryClient: QueryClient,
    projectId: string,
    ...scopes: ProjectMutationScope[]
): Promise<void> {
    const keys = scopes.flatMap((scope) => scopeKeys(projectId, scope));
    const unique = new Map(keys.map((key) => [JSON.stringify(key), key]));
    await Promise.all([...unique.values()].map((queryKey) => queryClient.invalidateQueries({ queryKey })));
}

export function projectMutationQueryKeys(projectId: string, ...scopes: ProjectMutationScope[]): QueryKey[] {
    const keys = scopes.flatMap((scope) => scopeKeys(projectId, scope));
    return [...new Map(keys.map((key) => [JSON.stringify(key), key])).values()];
}
