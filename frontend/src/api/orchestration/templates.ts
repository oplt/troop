import { apiFetch } from "../client";

export type WorkflowTemplate = {
    id: string;
    name: string;
    description: string;
    suggested_execution: Record<string, unknown>;
};

export type WorkflowTemplateApplyResult = {
    project_id: string;
    template: WorkflowTemplate;
    applied_execution: Record<string, unknown>;
    applied_at: string;
};

export async function listWorkflowTemplates(): Promise<WorkflowTemplate[]> {
    return apiFetch("/orchestration/workflow-templates");
}

export async function applyWorkflowTemplate(
    projectId: string,
    templateId: string,
): Promise<WorkflowTemplateApplyResult> {
    return apiFetch(`/orchestration/projects/${projectId}/workflow-templates/${encodeURIComponent(templateId)}/apply`, {
        method: "POST",
    });
}

export async function listCustomWorkflowTemplates(projectId: string): Promise<Array<Record<string, unknown>>> {
    return apiFetch(`/orchestration/projects/${projectId}/workflow-templates/custom`);
}

export async function saveCustomWorkflowTemplate(
    projectId: string,
    payload: { id?: string; name: string; stages: Array<Record<string, unknown>>; forked_from?: string | null },
): Promise<Record<string, unknown>> {
    return apiFetch(`/orchestration/projects/${projectId}/workflow-templates/custom`, {
        method: "POST",
        body: JSON.stringify(payload),
    });
}
