import type {
    AgentInheritancePreview,
    AgentTemplate,
    SkillPack,
} from "../../api/orchestration";
import type { SkillBuilderFormState, TemplateBuilderFormState } from "./types";

export const EMPTY_TEMPLATE_BUILDER_FORM: TemplateBuilderFormState = {
    name: "",
    slug: "",
    description: "",
    role: "specialist",
    system_prompt: "",
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

export function parseCsv(value: string) {
    return value
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
}

export function mergeUnique(...items: string[][]) {
    const merged: string[] = [];
    items.flat().forEach((item) => {
        if (item && !merged.includes(item)) {
            merged.push(item);
        }
    });
    return merged;
}

export function getTemplateBySlug(templates: AgentTemplate[], slug: string) {
    return templates.find((item) => item.slug === slug) ?? null;
}

export function buildTemplateBuilderForm(template: AgentTemplate): TemplateBuilderFormState {
    return {
        name: template.name,
        slug: template.slug,
        description: template.description,
        role: template.role,
        system_prompt: template.system_prompt,
        parent_template_slug: template.parent_template_slug ?? "",
        capabilities: template.capabilities.join(", "),
        allowed_tools: template.allowed_tools.join(", "),
        skills: template.skills,
        tags: template.tags.join(", "),
        task_filters: Array.isArray(template.metadata?.task_filters) ? template.metadata.task_filters.join(", ") : "",
        model: String((template.model_policy?.model as string | undefined) ?? ""),
        fallback_model: String((template.model_policy?.fallback_model as string | undefined) ?? ""),
        escalation_path: String((template.model_policy?.escalation_path as string | undefined) ?? ""),
        permission: String((template.model_policy?.permissions as string | undefined) ?? "read-only"),
        memory_scope: String((template.memory_policy?.scope as string | undefined) ?? "project-only"),
        output_format: String((template.output_schema?.format as string | undefined) ?? "json"),
        token_budget: String((template.budget?.token_budget as number | undefined) ?? 8000),
        time_budget_seconds: String((template.budget?.time_budget_seconds as number | undefined) ?? 300),
        retry_budget: String((template.budget?.retry_budget as number | undefined) ?? 1),
    };
}

export function slugifyValue(value: string) {
    return value
        .toLowerCase()
        .trim()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-+|-+$/g, "");
}

export function createUniqueSlug(value: string, existingSlugs: string[]) {
    const base = slugifyValue(value) || "untitled";
    let candidate = base;
    let index = 2;
    while (existingSlugs.includes(candidate)) {
        candidate = `${base}-${index}`;
        index += 1;
    }
    return candidate;
}

export function buildAgentTemplateFromForm(
    form: TemplateBuilderFormState,
    existingTemplate?: AgentTemplate | null,
): AgentTemplate {
    return {
        id: existingTemplate?.id,
        slug: form.slug.trim() || slugifyValue(form.name) || existingTemplate?.slug || "untitled-template",
        name: form.name.trim() || existingTemplate?.name || "Untitled template",
        description: form.description.trim(),
        role: form.role,
        parent_template_slug: form.parent_template_slug || null,
        system_prompt: form.system_prompt.trim(),
        mission_markdown: existingTemplate?.mission_markdown ?? form.description.trim(),
        rules_markdown: existingTemplate?.rules_markdown ?? "",
        output_contract_markdown: existingTemplate?.output_contract_markdown ?? "",
        capabilities: parseCsv(form.capabilities),
        allowed_tools: parseCsv(form.allowed_tools),
        tags: parseCsv(form.tags),
        skills: form.skills,
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
            task_filters: parseCsv(form.task_filters),
        },
    };
}

export function buildInheritancePreview(
    form: TemplateBuilderFormState,
    templates: AgentTemplate[],
    skills: SkillPack[],
): AgentInheritancePreview | null {
    const template = form.parent_template_slug ? getTemplateBySlug(templates, form.parent_template_slug) : null;
    if (!template) {
        return null;
    }

    const selectedSkills = skills.filter((item) => form.skills.includes(item.slug));
    const inheritedCapabilities = mergeUnique(
        template.capabilities,
        selectedSkills.flatMap((item) => item.capabilities),
    );
    const inheritedTools = mergeUnique(
        template.allowed_tools,
        selectedSkills.flatMap((item) => item.allowed_tools),
    );
    const inheritedTags = mergeUnique(template.tags, selectedSkills.flatMap((item) => item.tags));
    const overriddenFields: Record<string, unknown> = {};
    const explicitCapabilities = parseCsv(form.capabilities);
    const explicitTools = parseCsv(form.allowed_tools);
    const explicitTags = parseCsv(form.tags);

    if (explicitCapabilities.length > 0) {
        overriddenFields.capabilities = explicitCapabilities;
    }
    if (explicitTools.length > 0) {
        overriddenFields.allowed_tools = explicitTools;
    }
    if (explicitTags.length > 0) {
        overriddenFields.tags = explicitTags;
    }
    if (form.system_prompt.trim()) {
        overriddenFields.system_prompt = form.system_prompt.trim();
    }

    return {
        parent_template_slug: template.slug,
        inherited_fields: {
            capabilities: inheritedCapabilities,
            allowed_tools: inheritedTools,
            skills: template.skills,
            tags: inheritedTags,
            rules_markdown: template.rules_markdown,
            budget: template.budget,
            memory_policy: template.memory_policy,
            output_schema: template.output_schema,
            model_policy: template.model_policy,
        },
        overridden_fields: overriddenFields,
        effective: {
            capabilities: mergeUnique(inheritedCapabilities, explicitCapabilities),
            allowed_tools: mergeUnique(inheritedTools, explicitTools),
            skills: mergeUnique(template.skills, form.skills),
            tags: mergeUnique(inheritedTags, explicitTags),
            rules_markdown: template.rules_markdown,
            budget: {
                ...template.budget,
                token_budget: Number(form.token_budget || 0),
                time_budget_seconds: Number(form.time_budget_seconds || 0),
                retry_budget: Number(form.retry_budget || 0),
            },
            memory_policy: { scope: form.memory_scope },
            output_schema: { format: form.output_format },
            model_policy: {
                ...template.model_policy,
                model: form.model || null,
                fallback_model: form.fallback_model || null,
                escalation_path: form.escalation_path || null,
                permissions: form.permission,
            },
        },
    };
}

function normalizeText(value: string) {
    return value
        .trim()
        .replace(/\r/g, "")
        .replace(/\n+/g, " ")
        .replace(/\s+/g, " ");
}

function parseFrontmatterBlock(frontmatter: string, key: string) {
    const blockMatch = frontmatter.match(new RegExp(`^${key}:\\s*[>|-]\\s*\\n((?:[ \\t].*\\n?)*)`, "m"));
    if (blockMatch?.[1]) {
        return normalizeText(blockMatch[1].replace(/^[ \t]+/gm, ""));
    }

    const lineMatch = frontmatter.match(new RegExp(`^${key}:\\s*(.+)$`, "m"));
    return lineMatch?.[1] ? normalizeText(lineMatch[1]) : "";
}

function parseMarkdownSection(content: string, headings: string[]) {
    const pattern = headings.map((heading) => heading.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|");
    const match = content.match(new RegExp(`(?:^|\\n)#{1,6}\\s*(?:${pattern})\\s*\\n([\\s\\S]*?)(?=\\n#{1,6}\\s|$)`, "i"));
    return match?.[1]?.trim() ?? "";
}

export function parseSkillMarkdownDocument(content: string, fileName: string): SkillBuilderFormState {
    const trimmedContent = content.trim();
    const frontmatterMatch = trimmedContent.match(/^---\s*\n([\s\S]*?)\n---\s*/);
    const frontmatter = frontmatterMatch?.[1] ?? "";
    const body = frontmatterMatch ? trimmedContent.slice(frontmatterMatch[0].length) : trimmedContent;

    const frontmatterName = parseFrontmatterBlock(frontmatter, "name");
    const headingName = body.match(/^\s*#\s+(.+)$/m)?.[1]?.trim() ?? "";
    const name = frontmatterName || headingName || fileName.replace(/\.md$/i, "");

    const frontmatterDescription = parseFrontmatterBlock(frontmatter, "description");
    const descriptionSection = parseMarkdownSection(body, ["Description", "Overview"]);
    const firstParagraph = body
        .split(/\n\s*\n/)
        .map((block) => block.trim())
        .find((block) => block && !block.startsWith("#") && !block.startsWith("-") && !block.startsWith("*")) ?? "";
    const description = frontmatterDescription || normalizeText(descriptionSection) || normalizeText(firstParagraph);

    const capabilitiesSection = parseMarkdownSection(body, [
        "Capabilities",
        "Capability",
        "Use this skill when",
        "Use when",
        "When to Use",
    ]);
    const capabilityLines = capabilitiesSection
        .split("\n")
        .map((line) => line.replace(/^[-*]\s*/, "").trim())
        .filter(Boolean);

    return {
        name,
        description,
        capabilities: capabilityLines.join(", "),
    };
}
