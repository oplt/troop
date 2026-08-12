import type { ProjectTaskPayload } from "./api";

export type ProjectTaskDraft = {
    title: string;
    description: string;
    source: string;
    task_type: string;
    priority: string;
    status: string;
    acceptance_criteria: string;
    assigned_agent_id: string;
    reviewer_agent_id: string;
    dependency_ids: string[];
    due_date: string;
    response_sla_hours: string;
    required_tools: string;
};

export function createProjectTaskDraft(): ProjectTaskDraft {
    return {
        title: "",
        description: "",
        source: "manual",
        task_type: "general",
        priority: "normal",
        status: "queued",
        acceptance_criteria: "",
        assigned_agent_id: "",
        reviewer_agent_id: "",
        dependency_ids: [],
        due_date: "",
        response_sla_hours: "",
        required_tools: "",
    };
}

export function normalizeProjectTaskDraft(draft: ProjectTaskDraft): ProjectTaskPayload {
    const responseSla = Number(draft.response_sla_hours);
    return {
        title: draft.title.trim(),
        description: draft.description.trim(),
        source: draft.source,
        task_type: draft.task_type,
        status: draft.status,
        priority: draft.priority,
        acceptance_criteria: draft.acceptance_criteria.trim() || null,
        assigned_agent_id: draft.assigned_agent_id || null,
        reviewer_agent_id: draft.reviewer_agent_id || null,
        dependency_ids: draft.dependency_ids,
        due_date: draft.due_date.trim() || null,
        response_sla_hours: draft.response_sla_hours.trim() && !Number.isNaN(responseSla) && responseSla > 0 ? responseSla : null,
        required_tools: draft.required_tools.split(/[\n,]/).map((item) => item.trim()).filter(Boolean),
    };
}
