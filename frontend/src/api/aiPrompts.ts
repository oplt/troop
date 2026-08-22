import { apiFetch } from "./client";
import type { AiOverview, AiPromptTemplate, AiPromptVersion, AiVariableDefinition } from "./aiTypes";

export async function getAiOverview(): Promise<AiOverview> {
    return apiFetch("/ai/overview");
}

export async function listPromptTemplates(): Promise<AiPromptTemplate[]> {
    return apiFetch("/ai/prompts");
}

export async function listPromptVersions(templateId: string): Promise<AiPromptVersion[]> {
    return apiFetch(`/ai/prompts/${templateId}/versions`);
}

export async function createPromptTemplate(payload: {
    key: string;
    name: string;
    description?: string;
}): Promise<AiPromptTemplate> {
    return apiFetch("/ai/prompts", { method: "POST", body: JSON.stringify(payload) });
}

export async function updatePromptTemplate(
    templateId: string,
    payload: Partial<{
        name: string;
        description: string | null;
        is_active: boolean;
        active_version_id: string | null;
    }>,
): Promise<AiPromptTemplate> {
    return apiFetch(`/ai/prompts/${templateId}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export async function createPromptVersion(
    templateId: string,
    payload: {
        provider_key: string;
        model_name: string;
        system_prompt: string;
        user_prompt_template: string;
        variable_definitions: AiVariableDefinition[];
        response_format: "text" | "json";
        temperature: number;
        rollout_percentage: number;
        is_published: boolean;
        input_cost_per_million: number;
        output_cost_per_million: number;
    },
): Promise<AiPromptVersion> {
    return apiFetch(`/ai/prompts/${templateId}/versions`, { method: "POST", body: JSON.stringify(payload) });
}

export async function updatePromptVersion(
    templateId: string,
    versionId: string,
    payload: Partial<{ is_published: boolean; rollout_percentage: number }>,
): Promise<AiPromptVersion> {
    return apiFetch(`/ai/prompts/${templateId}/versions/${versionId}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
    });
}
