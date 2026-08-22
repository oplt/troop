import { useQuery } from "@tanstack/react-query";

import {
    getGateConfig,
    getMergeResolutionPreview,
    getProjectMemorySettings,
    getProjectRepositoryIndexStatus,
    listAgents,
    listAgentTemplates,
    listApprovals,
    listBrainstorms,
    listGithubIssueLinks,
    listGithubSyncEvents,
    listDagReadyTasks,
    listProjectAgents,
    listProjectDecisions,
    listProjectDocuments,
    listProjectMemory,
    listProjectMemoryIngestJobs,
    listProjectRepositories,
    listProviders,
    listRuns,
    searchProjectKnowledge,
    listSemanticMemory,
} from "../../../api/orchestration";
import { queryKeys } from "../../../config/queryKeys";
import { projectDetailApi } from "./api";

export type DetailTab = "overview" | "board" | "runs" | "agents" | "memory" | "settings";
export type WorkView = "board" | "dependencies" | "brainstorms";
export type KnowledgeView = "ask" | "search" | "sources" | "decisions" | "integrations" | "memory";
export type TeamView = "agents" | "settings";

export type ProjectDetailQueryState = {
    tab: DetailTab;
    workView: WorkView;
    teamView: TeamView;
    knowledgeView: KnowledgeView;
    knowledgeQuery: string;
    includeDecisionRecall: boolean;
    mergeTaskId: string | null;
};

export function isProjectDetailSectionActive(
    state: ProjectDetailQueryState,
    ...sections: Array<DetailTab | WorkView | KnowledgeView | "agents" | "activity" | "execution" | "knowledge" | "team" | "work">
): boolean {
    return sections.some((section) => {
        if (section === state.tab) return true;
        if (state.tab === "board") {
            return (
                section === "work" ||
                section === "board" ||
                section === state.workView ||
                section === "dependencies" ||
                section === "brainstorms"
            );
        }
        if (state.tab === "runs") {
            return section === "runs" || section === "activity";
        }
        if (state.tab === "agents") {
            return section === "agents" || section === "team";
        }
        if (state.tab === "memory") {
            return (
                section === "memory" ||
                section === "knowledge" ||
                section === "search" ||
                section === "ask" ||
                section === "sources" ||
                section === "decisions" ||
                section === state.knowledgeView
            );
        }
        if (state.tab === "settings") {
            if (section === "settings") return true;
            if (state.knowledgeView === "integrations") {
                return section === "integrations" || section === "sources";
            }
            if (state.teamView === "agents") {
                return section === "team" || section === "agents";
            }
            return section === "execution";
        }
        if (state.tab === "overview") {
            return section === "overview";
        }
        return false;
    });
}

export function useProjectDetailQueries(projectId: string, state: ProjectDetailQueryState) {
    const enabled = Boolean(projectId);
    const active = (...sections: Parameters<typeof isProjectDetailSectionActive>[1][]) =>
        isProjectDetailSectionActive(state, ...sections);

    const project = useQuery({
        queryKey: queryKeys.orchestration.project(projectId),
        queryFn: () => projectDetailApi.getProject(projectId),
        enabled,
    });
    const tasks = useQuery({
        queryKey: queryKeys.orchestration.projectTasks(projectId),
        queryFn: () => projectDetailApi.listTasks(projectId),
        enabled: enabled && active("board", "dependencies", "brainstorms"),
    });
    const allAgents = useQuery({
        queryKey: queryKeys.orchestration.agents(projectId),
        queryFn: () => listAgents(projectId),
        enabled: enabled && active("overview", "board", "dependencies", "brainstorms", "agents", "knowledge", "execution"),
    });
    const agentTemplates = useQuery({
        queryKey: queryKeys.orchestration.agentTemplates,
        queryFn: listAgentTemplates,
        enabled: active("agents", "execution"),
    });
    const providers = useQuery({
        queryKey: queryKeys.orchestration.providers,
        queryFn: () => listProviders(),
        enabled: active("agents"),
    });
    const projectAgents = useQuery({
        queryKey: queryKeys.orchestration.projectAgents(projectId),
        queryFn: () => listProjectAgents(projectId),
        enabled: enabled && active("board", "agents", "execution"),
    });
    const brainstorms = useQuery({
        queryKey: queryKeys.orchestration.projectBrainstorms(projectId),
        queryFn: () => listBrainstorms(projectId),
        enabled: enabled && active("brainstorms"),
    });
    const runs = useQuery({
        queryKey: queryKeys.orchestration.projectRuns(projectId),
        queryFn: () => listRuns(projectId),
        enabled: enabled && active("overview", "board", "dependencies", "brainstorms", "runs", "activity"),
    });
    const docs = useQuery({
        queryKey: queryKeys.orchestration.projectDocuments(projectId),
        queryFn: () => listProjectDocuments(projectId),
        enabled: enabled && active("sources", "memory"),
    });
    const projectRepositories = useQuery({
        queryKey: queryKeys.orchestration.projectRepositories(projectId),
        queryFn: () => listProjectRepositories(projectId),
        enabled: enabled && active("sources", "memory"),
    });
    const repositoryIndexStatus = useQuery({
        queryKey: queryKeys.orchestration.projectRepositoryIndexStatus(projectId),
        queryFn: () => getProjectRepositoryIndexStatus(projectId),
        enabled: enabled && active("sources"),
    });
    const knowledgeResults = useQuery({
        queryKey: queryKeys.orchestration.projectKnowledge(projectId, state.knowledgeQuery, state.includeDecisionRecall),
        queryFn: () => searchProjectKnowledge(projectId, state.knowledgeQuery, undefined, { includeDecisions: state.includeDecisionRecall }),
        enabled: enabled && active("memory", "knowledge") && state.knowledgeQuery.length >= 3,
    });
    const semanticEntries = useQuery({
        queryKey: queryKeys.orchestration.projectSemanticMemory(projectId, state.knowledgeQuery),
        queryFn: () => listSemanticMemory(
            projectId,
            state.knowledgeQuery
                ? { q: state.knowledgeQuery, limit: 25 }
                : { limit: 25 },
        ),
        enabled: enabled && active("memory", "knowledge"),
    });
    const projectMemorySettings = useQuery({
        queryKey: queryKeys.orchestration.projectMemorySettings(projectId),
        queryFn: () => getProjectMemorySettings(projectId),
        enabled: enabled && active("memory", "knowledge"),
    });
    const memoryIngestJobs = useQuery({
        queryKey: queryKeys.orchestration.projectMemoryIngestJobs(projectId),
        queryFn: () => listProjectMemoryIngestJobs(projectId, 80),
        enabled: enabled && active("memory", "knowledge"),
    });
    const memoryEntries = useQuery({
        queryKey: queryKeys.orchestration.projectMemory(projectId),
        queryFn: () => listProjectMemory(projectId),
        enabled: enabled && active("memory", "runs", "activity"),
    });
    const approvals = useQuery({
        queryKey: queryKeys.orchestration.approvals,
        queryFn: () => listApprovals(),
        enabled: active("overview", "runs", "activity", "board"),
    });
    const issueLinks = useQuery({
        queryKey: queryKeys.orchestration.projectIssues(projectId),
        queryFn: () => listGithubIssueLinks(projectId),
        enabled: enabled && active("integrations"),
    });
    const syncEvents = useQuery({
        queryKey: queryKeys.orchestration.projectSyncEvents(projectId),
        queryFn: () => listGithubSyncEvents(projectId),
        enabled: enabled && active("integrations", "runs"),
    });
    const milestones = useQuery({
        queryKey: queryKeys.orchestration.projectMilestones(projectId),
        queryFn: () => projectDetailApi.listMilestones(projectId),
        enabled: enabled && active("overview"),
    });
    const decisions = useQuery({
        queryKey: queryKeys.orchestration.projectDecisions(projectId),
        queryFn: () => listProjectDecisions(projectId),
        enabled: enabled && active("decisions", "memory"),
    });
    const gateConfig = useQuery({
        queryKey: queryKeys.orchestration.projectGateConfig(projectId),
        queryFn: () => getGateConfig(projectId),
        enabled: enabled && active("overview", "agents", "execution"),
    });
    const dagReadyList = useQuery({
        queryKey: queryKeys.orchestration.projectDagReady(projectId),
        queryFn: () => listDagReadyTasks(projectId),
        enabled: enabled && state.tab === "board" && state.workView === "dependencies",
    });
    const mergePreview = useQuery({
        queryKey: queryKeys.orchestration.projectMergePreview(projectId, state.mergeTaskId),
        queryFn: () => getMergeResolutionPreview(projectId, state.mergeTaskId as string),
        enabled: enabled && Boolean(state.mergeTaskId),
    });

    return {
        project,
        tasks,
        allAgents,
        agentTemplates,
        providers,
        projectAgents,
        brainstorms,
        runs,
        docs,
        projectRepositories,
        repositoryIndexStatus,
        knowledgeResults,
        semanticEntries,
        projectMemorySettings,
        memoryIngestJobs,
        memoryEntries,
        approvals,
        issueLinks,
        syncEvents,
        milestones,
        decisions,
        gateConfig,
        dagReadyList,
        mergePreview,
    };
}
