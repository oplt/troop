import { useEffect, useRef } from "react";
import { useQueryClient, type QueryClient, type QueryKey } from "@tanstack/react-query";

import type { ProjectLiveSnapshot } from "../api/orchestration";
import { queryKeys } from "../config/queryKeys";
import { useLiveSnapshotStream } from "./useLiveSnapshotStream";

export type ProjectLiveSnapshotSyncOptions = {
    expandedTaskId?: string | null;
};

function stableValue(value: unknown): string {
    return JSON.stringify(value ?? null);
}

function sectionChanged(previous: unknown, next: unknown): boolean {
    return stableValue(previous) !== stableValue(next);
}

export function isProjectLiveSnapshot(payload: Record<string, unknown>): payload is ProjectLiveSnapshot {
    return (
        typeof payload.project_id === "string" &&
        typeof payload.task_counts === "object" &&
        payload.task_counts !== null &&
        typeof payload.run_counts === "object" &&
        payload.run_counts !== null
    );
}

/** Returns deduplicated query keys that should refetch given snapshot delta. */
export function collectProjectLiveSnapshotInvalidationKeys(
    projectId: string,
    snapshot: ProjectLiveSnapshot,
    previous: ProjectLiveSnapshot | null,
    options: ProjectLiveSnapshotSyncOptions = {},
): QueryKey[] {
    if (!previous) {
        return [];
    }

    const keys: QueryKey[] = [];
    const push = (key: QueryKey) => keys.push(key);

    const taskChanged =
        sectionChanged(previous.task_counts, snapshot.task_counts) ||
        previous.latest?.task_updated_at !== snapshot.latest?.task_updated_at;
    const runChanged =
        sectionChanged(previous.run_counts, snapshot.run_counts) ||
        previous.latest?.run_created_at !== snapshot.latest?.run_created_at;
    const syncChanged =
        sectionChanged(previous.sync_counts, snapshot.sync_counts) ||
        previous.latest?.sync_created_at !== snapshot.latest?.sync_created_at;
    const ingestChanged = sectionChanged(previous.ingest_counts, snapshot.ingest_counts);
    const agentsChanged = sectionChanged(previous.agent_counts, snapshot.agent_counts);
    const approvalsChanged = sectionChanged(previous.approval_counts, snapshot.approval_counts);
    const resourcesChanged = sectionChanged(previous.resource_counts, snapshot.resource_counts);

    if (agentsChanged) {
        push(queryKeys.orchestration.projectAgents(projectId));
        push(queryKeys.orchestration.agents(projectId));
    }

    if (taskChanged) {
        push(queryKeys.orchestration.projectTasks(projectId));
        push(queryKeys.orchestration.projectDagReady(projectId));
        push(queryKeys.orchestration.projectTaskExecution(projectId));
        push(queryKeys.orchestration.projectTaskArtifacts(projectId));
        push(queryKeys.orchestration.taskCoord(projectId));
        push(queryKeys.orchestration.taskEpisodic(projectId));
        push(queryKeys.orchestration.taskSemantic(projectId));
        push(queryKeys.orchestration.subtasks());
        push(queryKeys.orchestration.artifacts());
        if (options.expandedTaskId) {
            push(queryKeys.orchestration.projectTaskTimeline(projectId, options.expandedTaskId));
        }
    }

    if (runChanged) {
        push(queryKeys.orchestration.projectRuns(projectId));
        push(queryKeys.orchestration.projectTaskExecution(projectId));
        push(queryKeys.orchestration.runWorkingMemoryRoot);
    }

    if (resourcesChanged) {
        push(queryKeys.orchestration.project(projectId));
    }

    if (
        resourcesChanged &&
        previous.resource_counts?.repositories !== snapshot.resource_counts?.repositories
    ) {
        push(queryKeys.orchestration.projectRepositories(projectId));
        push(queryKeys.orchestration.projectRepositoryIndexStatus(projectId));
    }

    if (
        resourcesChanged &&
        previous.resource_counts?.documents !== snapshot.resource_counts?.documents
    ) {
        push(queryKeys.orchestration.projectDocuments(projectId));
        push(queryKeys.orchestration.projectKnowledge(projectId));
    }

    if (
        resourcesChanged &&
        previous.resource_counts?.decisions !== snapshot.resource_counts?.decisions
    ) {
        push(queryKeys.orchestration.projectDecisions(projectId));
        push(queryKeys.orchestration.projectKnowledge(projectId));
    }

    if (
        resourcesChanged &&
        previous.resource_counts?.memory_entries !== snapshot.resource_counts?.memory_entries
    ) {
        push(queryKeys.orchestration.projectMemory(projectId));
        push(queryKeys.orchestration.projectSemanticMemory(projectId));
    }

    if (approvalsChanged) {
        push(queryKeys.orchestration.approvals);
    }

    if (syncChanged) {
        push(queryKeys.orchestration.projectSyncEvents(projectId));
        push(queryKeys.orchestration.projectIssues(projectId));
    }

    if (ingestChanged) {
        push(queryKeys.orchestration.projectMemoryIngestJobs(projectId));
        push(queryKeys.orchestration.projectRepositoryIndexStatus(projectId));
    }

    const seen = new Set<string>();
    return keys.filter((key) => {
        const serialized = stableValue(key);
        if (seen.has(serialized)) return false;
        seen.add(serialized);
        return true;
    });
}

export function applyProjectLiveSnapshotSync(
    queryClient: QueryClient,
    projectId: string,
    payload: Record<string, unknown>,
    previousRef: { current: ProjectLiveSnapshot | null },
    options: ProjectLiveSnapshotSyncOptions = {},
): void {
    if (!isProjectLiveSnapshot(payload)) return;

    const snapshot = payload;
    queryClient.setQueryData(queryKeys.orchestration.projectLiveSnapshot(projectId), snapshot);

    const keys = collectProjectLiveSnapshotInvalidationKeys(
        projectId,
        snapshot,
        previousRef.current,
        options,
    );
    for (const queryKey of keys) {
        void queryClient.invalidateQueries({ queryKey });
    }

    previousRef.current = snapshot;
}

export function useProjectLiveSnapshotSync(
    projectId: string | null | undefined,
    options: { enabled?: boolean; expandedTaskId?: string | null } = {},
) {
    const queryClient = useQueryClient();
    const { enabled = Boolean(projectId), expandedTaskId = null } = options;
    const previousRef = useRef<ProjectLiveSnapshot | null>(null);
    const expandedTaskRef = useRef(expandedTaskId);

    useEffect(() => {
        expandedTaskRef.current = expandedTaskId;
    }, [expandedTaskId]);

    useEffect(() => {
        previousRef.current = null;
    }, [projectId]);

    return useLiveSnapshotStream(projectId ? `/orchestration/projects/${projectId}/stream` : null, {
        enabled,
        coalesceMs: 120,
        onSnapshot: (payload) => {
            if (!projectId) return;
            applyProjectLiveSnapshotSync(queryClient, projectId, payload, previousRef, {
                expandedTaskId: expandedTaskRef.current,
            });
        },
    });
}
