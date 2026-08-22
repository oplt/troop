import {
    getOrchestrationProject,
    createOrchestrationTask,
    listOrchestrationTasks,
    listProjectMilestones,
    type OrchestrationProject,
    type ProjectMilestone,
    type TaskListItem,
} from "../../../api/orchestration";

export type ProjectDetailResources = {
    project: OrchestrationProject;
    tasks: TaskListItem[];
    milestones: ProjectMilestone[];
};

export type ProjectTaskPayload = {
    title: string;
    description: string;
    source: string;
    task_type: string;
    status: string;
    priority: string;
    acceptance_criteria: string | null;
    assigned_agent_id: string | null;
    reviewer_agent_id: string | null;
    dependency_ids: string[];
    due_date: string | null;
    response_sla_hours: number | null;
    required_tools: string[];
};

/** Normalize the three primary project-detail reads into one view-model bundle. */
export function buildProjectDetailResources(
    project: OrchestrationProject,
    tasks: TaskListItem[],
    milestones: ProjectMilestone[],
): ProjectDetailResources {
    return { project, tasks, milestones };
}

/** Feature-owned typed façade; the legacy client remains the compatibility boundary during migration. */
export const projectDetailApi = {
    getProject: (projectId: string) => getOrchestrationProject(projectId),
    listTasks: (projectId: string) => listOrchestrationTasks(projectId),
    listMilestones: (projectId: string) => listProjectMilestones(projectId),
    createTask: (projectId: string, payload: ProjectTaskPayload) => createOrchestrationTask(projectId, payload),
};
