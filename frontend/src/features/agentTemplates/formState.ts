import type { AgentTemplate } from "../../api/orchestration";

export type AgentTemplateFormState = {
    name: string;
    slug: string;
    description: string;
    role: string;
    system_prompt: string;
    mission_markdown: string;
    rules_markdown: string;
    output_contract_markdown: string;
    parent_template_slug: string;
    capabilities: string;
    allowed_tools: string;
    skills: string[];
    tags: string;
    task_filters: string;
    model: string;
    fallback_model: string;
    escalation_path: string;
    permission: string;
    memory_scope: string;
    output_format: string;
    token_budget: string;
    time_budget_seconds: string;
    retry_budget: string;
};

export const EMPTY_AGENT_TEMPLATE_FORM: AgentTemplateFormState = {
    name: "",
    slug: "",
    description: "",
    role: "specialist",
    system_prompt: "",
    mission_markdown: "",
    rules_markdown: "",
    output_contract_markdown: "",
    parent_template_slug: "",
    capabilities: "",
    allowed_tools: "",
    skills: [],
    tags: "",
    task_filters: "",
    model: "",
    fallback_model: "",
    escalation_path: "",
    permission: "read-only",
    memory_scope: "project-only",
    output_format: "json",
    token_budget: "8000",
    time_budget_seconds: "300",
    retry_budget: "1",
};

export function parseAgentTemplateCsv(value: string): string[] {
    return value
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
}

export function parseAgentTemplateLooseList(value: string): string[] {
    return value
        .split(/[\n,]/g)
        .map((item) => item.trim())
        .filter(Boolean);
}

export function stringifyAgentTemplateList(items: readonly string[]): string {
    return items
        .map((item) => item.trim())
        .filter(Boolean)
        .join(", ");
}

export function slugifyAgentTemplateValue(value: string) {
    return value
        .toLowerCase()
        .trim()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/(^-|-$)/g, "");
}

export function createUniqueAgentTemplateSlug(value: string, existingSlugs: string[]) {
    const base = slugifyAgentTemplateValue(value) || "untitled-template";
    if (!existingSlugs.includes(base)) {
        return base;
    }
    let index = 2;
    while (existingSlugs.includes(`${base}-${index}`)) {
        index += 1;
    }
    return `${base}-${index}`;
}

export function buildAgentTemplateFormFromTemplate(template: AgentTemplate): AgentTemplateFormState {
    const taskFilters = Array.isArray(template.metadata?.task_filters)
        ? template.metadata.task_filters.filter((item): item is string => typeof item === "string")
        : [];

    return {
        name: template.name,
        slug: template.slug,
        description: template.description ?? "",
        role: template.role,
        system_prompt: template.system_prompt ?? "",
        mission_markdown: template.mission_markdown ?? "",
        rules_markdown: template.rules_markdown ?? "",
        output_contract_markdown: template.output_contract_markdown ?? "",
        parent_template_slug: template.parent_template_slug ?? "",
        capabilities: template.capabilities.join(", "),
        allowed_tools: template.allowed_tools.join(", "),
        skills: template.skills,
        tags: template.tags.join(", "),
        task_filters: taskFilters.join("\n"),
        model: String((template.model_policy?.model as string | undefined) || ""),
        fallback_model: String((template.model_policy?.fallback_model as string | undefined) || ""),
        escalation_path: String((template.model_policy?.escalation_path as string | undefined) || ""),
        permission: String((template.model_policy?.permissions as string | undefined) || "read-only"),
        memory_scope: String((template.memory_policy?.scope as string | undefined) || "project-only"),
        output_format: String((template.output_schema?.format as string | undefined) || "json"),
        token_budget: String((template.budget?.token_budget as number | undefined) || 8000),
        time_budget_seconds: String((template.budget?.time_budget_seconds as number | undefined) || 300),
        retry_budget: String((template.budget?.retry_budget as number | undefined) || 1),
    };
}

export function buildAgentTemplatePayloadFromForm(
    form: AgentTemplateFormState,
    existingTemplate: AgentTemplate | null,
    existingSlugs: string[],
): Omit<AgentTemplate, "id"> {
    const nextSlug = existingTemplate?.slug
        ?? (form.slug.trim() || createUniqueAgentTemplateSlug(form.name || "Untitled agent template", existingSlugs));

    return {
        slug: nextSlug,
        name: form.name.trim() || existingTemplate?.name || "Untitled agent template",
        role: form.role,
        description: form.description.trim(),
        system_prompt: form.system_prompt.trim(),
        parent_template_slug: form.parent_template_slug.trim() || null,
        mission_markdown: form.mission_markdown.trim(),
        rules_markdown: form.rules_markdown.trim(),
        output_contract_markdown: form.output_contract_markdown.trim(),
        capabilities: parseAgentTemplateCsv(form.capabilities),
        allowed_tools: parseAgentTemplateCsv(form.allowed_tools),
        skills: form.skills,
        tags: parseAgentTemplateCsv(form.tags),
        model_policy: {
            ...(existingTemplate?.model_policy ?? {}),
            model: form.model || null,
            fallback_model: form.fallback_model || null,
            escalation_path: form.escalation_path || null,
            permissions: form.permission,
        },
        budget: {
            ...(existingTemplate?.budget ?? {}),
            token_budget: Number(form.token_budget || 0),
            time_budget_seconds: Number(form.time_budget_seconds || 0),
            retry_budget: Number(form.retry_budget || 0),
        },
        memory_policy: {
            ...(existingTemplate?.memory_policy ?? {}),
            scope: form.memory_scope,
        },
        output_schema: {
            ...(existingTemplate?.output_schema ?? {}),
            format: form.output_format,
        },
        metadata: {
            ...(existingTemplate?.metadata ?? {}),
            task_filters: parseAgentTemplateLooseList(form.task_filters),
        },
    };
}
