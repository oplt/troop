import { useMutation } from "@tanstack/react-query";
import type { QueryClient } from "@tanstack/react-query";
import type { NavigateFunction } from "react-router-dom";

import {
    addProjectAgent,
    createAgentFromTemplate,
    createBrainstorm,
    createProjectDecision,
    createProjectMemory,
    createProjectMilestone,
    decideApproval,
    deleteAgent,
    deleteProjectDocument,
    deleteProjectMemoryEntry,
    isPendingSemanticWrite,
    patchProjectMemorySettings,
    queueProjectRepositoryIndex,
    removeProjectAgent,
    startBrainstorm,
    startDagParallelReady,
    startMergeResolutionRun,
    startTaskRun,
    updateAgent,
    updateGateConfig,
    updateLocalRepoWorkspace,
    updateOrchestrationProject,
    updateOrchestrationTask,
    updateProjectAgent,
    updateProjectMilestone,
    updateProjectRepository,
    uploadProjectDocument,
} from "../../../api/orchestration";
import type { DagParallelStartResult, GateConfig, TaskRun } from "../../../api/orchestration";
import type { ToastOptions } from "../../../app/snackbarContext";
import { queryKeys } from "../../../config/queryKeys";
import { projectDetailApi, type ProjectTaskPayload } from "./api";
import { invalidateProjectMutation } from "./mutations";
import type { ExecutionMode, LocalRepoDraft } from "./workspaceShared";
import {
    splitCsv,
    toastQueuedRunWithOptionalWarnings,
} from "./workspaceShared";
import { extractApiErrorMessage } from "../../../utils/apiErrors";

export type ProjectDetailBrainstormForm = {
    topic: string;
    task_id: string;
    moderator_agent_id: string;
    participant_agent_ids: string[];
    mode: string;
    output_type: string;
    max_rounds: string;
    max_cost_usd: string;
    max_repetition_score: string;
    soft_consensus_min_similarity: string;
    conflict_pairwise_max_similarity: string;
    stop_on_consensus: boolean;
    accept_soft_consensus: boolean;
    escalate_on_no_consensus: boolean;
};

export type ProjectDetailAgentMemoryForm = {
    agent_id: string;
    key: string;
    value_text: string;
    scope: "project-only" | "long-term";
    ttl_days: string;
};

export type ProjectDetailMutationActions = {
    clearSelectedAgentId: () => void;
    resetTaskCreateForm: () => void;
    resetBrainstormForm: () => void;
    resetMilestoneForm: () => void;
    resetDecisionForm: () => void;
    resetAgentMemoryFields: () => void;
    clearLocalRepoDraft: () => void;
    clearMergeResolution: () => void;
    clearDagDependencyDraft: (taskId: string) => void;
};

export type UseProjectDetailMutationsOptions = {
    projectId: string;
    queryClient: QueryClient;
    showToast: (opts: ToastOptions) => void;
    navigate: NavigateFunction;
    actions: ProjectDetailMutationActions;
    agentMemoryForm: ProjectDetailAgentMemoryForm;
    documentTtlDays: string;
    resolvedLocalRepoForm: LocalRepoDraft;
};

const EMPTY_BRAINSTORM_FORM: ProjectDetailBrainstormForm = {
    topic: "",
    task_id: "",
    moderator_agent_id: "",
    participant_agent_ids: [],
    mode: "exploration",
    output_type: "implementation_plan",
    max_rounds: "3",
    max_cost_usd: "10",
    max_repetition_score: "0.92",
    soft_consensus_min_similarity: "0.72",
    conflict_pairwise_max_similarity: "0.38",
    stop_on_consensus: true,
    accept_soft_consensus: true,
    escalate_on_no_consensus: true,
};

/** Typed mutation hooks for the project detail workspace. */
export function useProjectDetailMutations({
    projectId,
    queryClient,
    showToast,
    navigate,
    actions,
    agentMemoryForm,
    documentTtlDays,
    resolvedLocalRepoForm,
}: UseProjectDetailMutationsOptions) {
    const addAgentMutation = useMutation({
        mutationFn: async ({ selection }: { selection: string }) => {
            if (selection.startsWith("agent:")) {
                const agentId = selection.slice("agent:".length);
                const membership = await addProjectAgent(projectId, { agent_id: agentId, role: "member" });
                return { kind: "existing" as const, membership };
            }
            if (selection.startsWith("template:")) {
                const templateSlug = selection.slice("template:".length);
                const nextAgent = await createAgentFromTemplate(templateSlug, {
                    project_id: projectId,
                    slug: `${templateSlug}-${Date.now()}`,
                });
                const membership = await addProjectAgent(projectId, { agent_id: nextAgent.id, role: "member" });
                return { kind: "from_template" as const, membership, createdAgent: nextAgent };
            }
            throw new Error("Pick an agent or template first.");
        },
        onSuccess: async (data) => {
            actions.clearSelectedAgentId();
            await Promise.all([
                queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.projectAgents(projectId) }),
                queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.agents(projectId) }),
            ]);
            const lintWarnings =
                data.kind === "from_template"
                    ? (data.createdAgent.lint?.warnings ?? []).filter((line: string | undefined): line is string => Boolean(line))
                    : [];
            if (lintWarnings.length > 0) {
                showToast({
                    message: `Agent assigned to project. ${lintWarnings.join(" ")}`,
                    severity: "warning",
                });
            } else {
                showToast({ message: "Agent assigned to project.", severity: "success" });
            }
        },
    });

    const deleteAgentMutation = useMutation({
        mutationFn: (selection: string) => {
            const agentId = selection.startsWith("agent:") ? selection.slice("agent:".length) : selection;
            return deleteAgent(agentId);
        },
        onSuccess: async () => {
            actions.clearSelectedAgentId();
            await Promise.all([
                queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.agents() }),
                queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.projectAgents(projectId) }),
            ]);
            showToast({ message: "Agent deleted from database.", severity: "success" });
        },
    });

    const createTaskMutation = useMutation({
        mutationFn: (payload: ProjectTaskPayload) => projectDetailApi.createTask(projectId, payload),
        onSuccess: async () => {
            actions.resetTaskCreateForm();
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.projectTasks(projectId) });
            showToast({ message: "Task created.", severity: "success" });
        },
    });

    const runMutation = useMutation({
        mutationFn: ({ taskId, runMode, createPr }: { taskId: string; runMode: ExecutionMode; createPr: boolean }) =>
            startTaskRun(projectId, taskId, { run_mode: runMode, input_payload: { create_pr: createPr, draft_pr: true } }),
        onSuccess: async (run: TaskRun) => {
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.projectRuns(projectId) });
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.projectTasks(projectId) });
            toastQueuedRunWithOptionalWarnings(showToast, run, "Run queued.");
            navigate(`/runs/${run.id}`);
        },
        onError: (error) => {
            showToast({ message: extractApiErrorMessage(error, "Couldn't start run. Try again."), severity: "error" });
        },
    });

    const dagParallelMutation = useMutation({
        mutationFn: () =>
            startDagParallelReady(projectId, {
                run_mode: "single_agent",
                limit: 12,
                input_payload: { dag_parallel_wave: true },
            }),
        onSuccess: async (res: DagParallelStartResult) => {
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.projectRuns(projectId) });
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.projectTasks(projectId) });
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.projectDagReady(projectId) });
            showToast({
                message: `Started ${res.started_run_ids.length} parallel run(s).${res.skipped_task_ids.length ? ` ${res.skipped_task_ids.length} skipped (see messages).` : ""}`,
                severity: res.started_run_ids.length ? "success" : "warning",
            });
        },
    });

    const mergeResolutionMutation = useMutation({
        mutationFn: ({ parentTaskId, notes }: { parentTaskId: string; notes: string }) =>
            startMergeResolutionRun(projectId, parentTaskId, {
                notes,
                input_payload: {
                    merge_resolution: {
                        checklist_confirmed: true,
                        notes,
                    },
                },
            }),
        onSuccess: async (run: TaskRun) => {
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.projectRuns(projectId) });
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.projectTasks(projectId) });
            toastQueuedRunWithOptionalWarnings(showToast, run, "Merge resolution run queued.");
            actions.clearMergeResolution();
            navigate(`/runs/${run.id}`);
        },
    });

    const queueRepositoryIndexMutation = useMutation({
        mutationFn: ({
            repositoryLinkId,
            mode,
            pathPrefixes,
            scheduleLabel,
            autoEnabled,
        }: {
            repositoryLinkId: string;
            mode: "full" | "incremental";
            pathPrefixes: string[];
            scheduleLabel?: string | null;
            autoEnabled?: boolean | null;
        }) =>
            queueProjectRepositoryIndex(projectId, repositoryLinkId, {
                mode,
                path_prefixes: pathPrefixes,
                schedule_label: scheduleLabel,
                auto_enabled: autoEnabled,
            }),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.projectMemoryIngestJobs(projectId) });
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.projectRepositoryIndexStatus(projectId) });
            showToast({ message: "Repository indexing queued.", severity: "success" });
        },
    });

    const updateRepositoryMutation = useMutation({
        mutationFn: ({
            repositoryLinkId,
            defaultBranch,
            metadata,
        }: {
            repositoryLinkId: string;
            defaultBranch?: string | null;
            metadata?: Record<string, unknown>;
        }) =>
            updateProjectRepository(projectId, repositoryLinkId, {
                default_branch: defaultBranch,
                metadata,
            }),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.projectRepositories(projectId) });
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.projectRepositoryIndexStatus(projectId) });
            showToast({ message: "Repository index settings saved.", severity: "success" });
        },
    });

    const updateMembershipMutation = useMutation({
        mutationFn: ({ membershipId, payload }: { membershipId: string; payload: Record<string, unknown> }) =>
            updateProjectAgent(projectId, membershipId, payload),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.projectAgents(projectId) });
            showToast({ message: "Project team updated.", severity: "success" });
        },
    });

    const removeMembershipMutation = useMutation({
        mutationFn: (membershipId: string) => removeProjectAgent(projectId, membershipId),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.projectAgents(projectId) });
            showToast({ message: "Agent removed from project team.", severity: "success" });
        },
    });

    const updateHierarchyAgentMutation = useMutation({
        mutationFn: ({ agentId, payload }: { agentId: string; payload: Record<string, unknown> }) =>
            updateAgent(agentId, payload),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.agents() });
            showToast({ message: "Reporting line updated.", severity: "success" });
        },
    });

    const saveProjectSettingsMutation = useMutation({
        mutationFn: (payload: Record<string, unknown>) => updateOrchestrationProject(projectId, payload),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.project(projectId) });
            showToast({ message: "Project execution settings saved.", severity: "success" });
        },
    });

    const updateGateConfigMutation = useMutation({
        mutationFn: (payload: Partial<GateConfig>) => updateGateConfig(projectId, payload),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.projectGateConfig(projectId) });
            showToast({ message: "Gate configuration saved.", severity: "success" });
        },
    });

    const brainstormMutation = useMutation({
        mutationFn: (payload: Record<string, unknown>) => createBrainstorm(payload),
        onSuccess: async (brainstorm: { id: string }) => {
            actions.resetBrainstormForm();
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.projectBrainstorms(projectId) });
            showToast({ message: "Brainstorm created.", severity: "success" });
            await startBrainstorm(brainstorm.id);
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.projectRuns(projectId) });
        },
        onError: (error) => {
            showToast({ message: extractApiErrorMessage(error, "Couldn't start brainstorm. Try again."), severity: "error" });
        },
    });

    const milestoneMutation = useMutation({
        mutationFn: (payload: Record<string, unknown>) => createProjectMilestone(projectId, payload),
        onSuccess: async () => {
            actions.resetMilestoneForm();
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.projectMilestones(projectId) });
            showToast({ message: "Milestone created.", severity: "success" });
        },
    });

    const toggleMilestoneMutation = useMutation({
        mutationFn: ({ id, status }: { id: string; status: string }) =>
            updateProjectMilestone(projectId, id, { status }),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.projectMilestones(projectId) });
        },
    });

    const updateDagTaskMutation = useMutation({
        mutationFn: ({ taskId, payload }: { taskId: string; payload: Record<string, unknown> }) =>
            updateOrchestrationTask(projectId, taskId, payload),
        onSuccess: async (_, variables) => {
            actions.clearDagDependencyDraft(variables.taskId);
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.projectTasks(projectId) });
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.projectDagReady(projectId) });
            showToast({ message: "Task graph updated.", severity: "success" });
        },
        onError: (error) => {
            showToast({ message: extractApiErrorMessage(error, "Couldn't save task graph. Refresh and retry."), severity: "error" });
        },
    });

    const decisionMutation = useMutation({
        mutationFn: (payload: Record<string, unknown>) => createProjectDecision(projectId, payload),
        onSuccess: async () => {
            actions.resetDecisionForm();
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.projectDecisions(projectId) });
            showToast({ message: "Decision recorded.", severity: "success" });
        },
    });

    const uploadDocumentMutation = useMutation({
        mutationFn: (file: File) =>
            uploadProjectDocument(
                projectId,
                file,
                undefined,
                Number(documentTtlDays || 0) || undefined,
            ),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.projectDocuments(projectId) });
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.projectKnowledge(projectId) });
            showToast({ message: "Knowledge document uploaded.", severity: "success" });
        },
    });

    const deleteDocumentMutation = useMutation({
        mutationFn: (documentId: string) => deleteProjectDocument(projectId, documentId),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.projectDocuments(projectId) });
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.projectKnowledge(projectId) });
            showToast({ message: "Knowledge document removed.", severity: "success" });
        },
    });

    const deleteMemoryMutation = useMutation({
        mutationFn: (memoryId: string) => deleteProjectMemoryEntry(projectId, memoryId),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.projectMemory(projectId) });
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.approvals });
            showToast({ message: "Memory entry removed.", severity: "success" });
        },
    });

    const createMemoryMutation = useMutation({
        mutationFn: () =>
            createProjectMemory(projectId, {
                agent_id: agentMemoryForm.agent_id,
                key: agentMemoryForm.key.trim(),
                value_text: agentMemoryForm.value_text.trim(),
                scope: agentMemoryForm.scope,
                ttl_days: Number(agentMemoryForm.ttl_days || 0) || undefined,
            }),
        onSuccess: async (result) => {
            actions.resetAgentMemoryFields();
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.projectMemory(projectId) });
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.approvals });
            showToast({
                message: isPendingSemanticWrite(result)
                    ? "Long-term memory submitted for approval."
                    : "Agent memory saved.",
                severity: isPendingSemanticWrite(result) ? "info" : "success",
            });
        },
        onError: (error) => {
            showToast({ message: extractApiErrorMessage(error, "Couldn't save agent memory."), severity: "error" });
        },
    });

    const memoryApprovalMutation = useMutation({
        mutationFn: ({ approvalId, status, reason }: { approvalId: string; status: "approved" | "rejected"; reason?: string }) =>
            decideApproval(approvalId, { status, reason }),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.projectMemory(projectId) });
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.approvals });
            showToast({ message: "Memory review updated.", severity: "success" });
        },
    });

    const memorySettingsMutation = useMutation({
        mutationFn: (payload: Record<string, unknown>) => patchProjectMemorySettings(projectId, payload),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.projectMemorySettings(projectId) });
            showToast({ message: "Memory rules updated.", severity: "success" });
        },
    });

    const saveLocalRepoSettingsMutation = useMutation({
        mutationFn: () =>
            updateLocalRepoWorkspace(projectId, {
                enabled: resolvedLocalRepoForm.enabled && Boolean(resolvedLocalRepoForm.repo_path.trim()),
                repo_path: resolvedLocalRepoForm.repo_path.trim(),
                dirty_worktree_policy: resolvedLocalRepoForm.dirty_worktree_policy || "block",
                allowed_branches: splitCsv(resolvedLocalRepoForm.allowed_branches),
                file_allowlist: splitCsv(resolvedLocalRepoForm.file_allowlist),
                file_denylist: splitCsv(resolvedLocalRepoForm.file_denylist),
                command_allowlist: splitCsv(resolvedLocalRepoForm.command_allowlist),
                max_diff_bytes: Math.max(
                    1_000,
                    Math.min(5_000_000, Math.floor(Number(resolvedLocalRepoForm.max_diff_bytes) || 200_000)),
                ),
            }),
        onSuccess: async () => {
            actions.clearLocalRepoDraft();
            await invalidateProjectMutation(queryClient, projectId, "project", "repositories");
            showToast({ message: "Local repo settings saved.", severity: "success" });
        },
        onError: (error) => {
            showToast({ message: extractApiErrorMessage(error, "Could not save local repo settings."), severity: "error" });
        },
    });

    return {
        addAgentMutation,
        deleteAgentMutation,
        createTaskMutation,
        runMutation,
        dagParallelMutation,
        mergeResolutionMutation,
        queueRepositoryIndexMutation,
        updateRepositoryMutation,
        updateMembershipMutation,
        removeMembershipMutation,
        updateHierarchyAgentMutation,
        saveProjectSettingsMutation,
        updateGateConfigMutation,
        brainstormMutation,
        milestoneMutation,
        toggleMilestoneMutation,
        updateDagTaskMutation,
        decisionMutation,
        uploadDocumentMutation,
        deleteDocumentMutation,
        deleteMemoryMutation,
        createMemoryMutation,
        memoryApprovalMutation,
        memorySettingsMutation,
        saveLocalRepoSettingsMutation,
    };
}

export { EMPTY_BRAINSTORM_FORM };
