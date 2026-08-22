import type {
    OrchestrationProject,
    OrchestrationTask,
    ProjectMilestone,
    TaskListItem,
} from "../../../api/orchestration";

import type { ProjectDetailResources, ProjectTaskPayload } from "./api";

/** Minimal OrchestrationTask for tests and characterization fixtures. */
export function buildOrchestrationTaskFixture(
    overrides: Partial<OrchestrationTask> = {},
): OrchestrationTask {
    return {
        id: "task-1",
        project_id: "project-1",
        created_by_user_id: "user-1",
        assigned_agent_id: null,
        reviewer_agent_id: null,
        github_issue_link_id: null,
        title: "Verify rollout checklist",
        description: "Confirm launch gates",
        source: "manual",
        task_type: "general",
        priority: "normal",
        status: "backlog",
        acceptance_criteria: "All gates green",
        due_date: null,
        response_sla_hours: null,
        labels: [],
        required_tools: [],
        external_links: [],
        result_summary: null,
        result_payload: {},
        position: 0,
        metadata: {},
        dependency_ids: [],
        created_at: "2026-06-18T00:00:00.000Z",
        updated_at: "2026-06-18T00:00:00.000Z",
        ...overrides,
    };
}

/** Frozen project-detail API shapes for characterization tests and future splits. */
export const PROJECT_DETAIL_PROJECT_FIXTURE: OrchestrationProject = {
    id: "project-1",
    name: "Launch Ops",
    slug: "launch-ops",
    description: "Coordinate launch work",
    status: "active",
    goals_markdown: "Ship safely",
    settings: {
        workspace_overview: {
            executive_summary: "Launch control summary",
            current_focus: "Readiness",
            decision_focus: "Cutover",
        },
    },
    memory_scope: "project",
    knowledge_summary: null,
    company_id: null,
    created_at: "2026-06-18T00:00:00.000Z",
    updated_at: "2026-06-18T00:00:00.000Z",
};

export const PROJECT_DETAIL_TASK_FIXTURE = buildOrchestrationTaskFixture();

export function buildTaskListItemFixture(
    overrides: Partial<TaskListItem> = {},
): TaskListItem {
    return {
        id: "task-1",
        project_id: "project-1",
        title: "Verify rollout checklist",
        status: "backlog",
        priority: "normal",
        task_type: "general",
        position: 0,
        assigned_agent_id: null,
        human_assignee_id: null,
        parent_task_id: null,
        github_issue_number: null,
        github_issue_url: null,
        github_repository_full_name: null,
        due_date: null,
        labels: [],
        dependency_ids: [],
        has_result: false,
        created_at: "2026-06-18T00:00:00.000Z",
        updated_at: "2026-06-18T00:00:00.000Z",
        ...overrides,
    };
}

export const PROJECT_DETAIL_TASK_LIST_FIXTURE = buildTaskListItemFixture();

export const PROJECT_DETAIL_MILESTONE_FIXTURE: ProjectMilestone = {
    id: "milestone-1",
    project_id: "project-1",
    title: "Launch readiness",
    description: "Complete pre-launch checklist",
    status: "planned",
    due_date: "2026-07-01",
    position: 0,
    created_at: "2026-06-18T00:00:00.000Z",
    updated_at: "2026-06-18T00:00:00.000Z",
};

export const PROJECT_DETAIL_RESOURCES_FIXTURE: ProjectDetailResources = {
    project: PROJECT_DETAIL_PROJECT_FIXTURE,
    tasks: [PROJECT_DETAIL_TASK_LIST_FIXTURE],
    milestones: [PROJECT_DETAIL_MILESTONE_FIXTURE],
};

export const PROJECT_TASK_PAYLOAD_FIXTURE: ProjectTaskPayload = {
    title: "Verify rollout checklist",
    description: "Confirm launch gates",
    source: "manual",
    task_type: "general",
    status: "backlog",
    priority: "normal",
    acceptance_criteria: "All gates green",
    assigned_agent_id: null,
    reviewer_agent_id: null,
    dependency_ids: [],
    due_date: null,
    response_sla_hours: null,
    required_tools: [],
};
