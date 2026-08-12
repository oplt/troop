import type { SkillPack, TeamTemplate } from "../../../api/orchestration";

export type SkillTemplateFormState = {
    name: string;
    slug: string;
    description: string;
    capabilities: string[];
    allowed_tools: string[];
    tags: string[];
    rules_markdown: string;
};

export type TeamTemplateFormState = {
    name: string;
    slug: string;
    description: string;
    outcome: string;
    roles: string[];
    tools: string[];
    autonomy: string;
    visibility: string;
    agent_template_slugs: string[];
    canvas_layout: Record<string, unknown>;
};

export function buildSkillForm(skill?: SkillPack): SkillTemplateFormState {
    return {
        name: skill?.name ?? "",
        slug: skill?.slug ?? "",
        description: skill?.description ?? "",
        capabilities: skill?.capabilities ?? [],
        allowed_tools: skill?.allowed_tools ?? [],
        tags: skill?.tags ?? [],
        rules_markdown: skill?.rules_markdown ?? "",
    };
}

export function buildTeamTemplateForm(template?: TeamTemplate): TeamTemplateFormState {
    return {
        name: template?.name ?? "",
        slug: template?.slug ?? "",
        description: template?.description ?? "",
        outcome: template?.outcome ?? "",
        roles: template?.roles ?? [],
        tools: template?.tools ?? [],
        autonomy: template?.autonomy ?? "custom",
        visibility: template?.visibility ?? "private",
        agent_template_slugs: template?.agent_template_slugs ?? [],
        canvas_layout: template?.canvas_layout ?? {},
    };
}

export function uniqueStrings(items: string[]): string[] {
    return Array.from(new Set(items.map((item) => item.trim()).filter(Boolean)));
}
