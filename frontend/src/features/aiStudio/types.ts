import type { AiPromptTemplate, AiProvider } from "../../api/ai";

export type TemplateFormState = {
    key: string;
    name: string;
    description: string;
};

export type VersionFormState = {
    provider_key: string;
    model_name: string;
    system_prompt: string;
    user_prompt_template: string;
    variable_names: string;
    response_format: "text" | "json";
    temperature: string;
    rollout_percentage: string;
    is_published: boolean;
    input_cost_per_million: string;
    output_cost_per_million: string;
};

export type TextDocumentFormState = {
    title: string;
    description: string;
    content: string;
    content_type: string;
};

export type RunFormState = {
    prompt_template_key: string;
    prompt_version_id: string;
    variables_json: string;
    retrieval_query: string;
    top_k: string;
    review_required: boolean;
};

export type DatasetFormState = {
    name: string;
    description: string;
};

export type DatasetCaseFormState = {
    input_variables_json: string;
    expected_output_text: string;
    expected_output_json: string;
    notes: string;
};

export type TemplateKeyOption = {
    id: string;
    key: string;
    name: string;
};

export function templateKeyOptions(templates: AiPromptTemplate[]): TemplateKeyOption[] {
    return templates.map((template) => ({
        id: template.id,
        key: template.key,
        name: template.name,
    }));
}

export type { AiProvider };
