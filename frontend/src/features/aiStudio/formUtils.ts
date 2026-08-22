export type AiSection =
    | "prompts"
    | "playground"
    | "versions"
    | "documents"
    | "retrieval"
    | "reviews"
    | "datasets";

export type AiWorkspace = "build" | "test" | "knowledge";

export const AI_SECTIONS: AiSection[] = [
    "prompts",
    "playground",
    "versions",
    "documents",
    "retrieval",
    "reviews",
    "datasets",
];

export const AI_WORKSPACE_SECTIONS: Record<AiWorkspace, AiSection[]> = {
    build: ["prompts", "versions"],
    test: ["playground", "datasets", "reviews"],
    knowledge: ["documents", "retrieval"],
};

export function workspaceForSection(section: AiSection): AiWorkspace {
    if (AI_WORKSPACE_SECTIONS.test.includes(section)) return "test";
    if (AI_WORKSPACE_SECTIONS.knowledge.includes(section)) return "knowledge";
    return "build";
}

export function defaultSectionForWorkspace(workspace: AiWorkspace): AiSection {
    return AI_WORKSPACE_SECTIONS[workspace][0];
}

export function parseJsonObject(value: string, fallback: Record<string, unknown> = {}) {
    if (!value.trim()) {
        return fallback;
    }
    const parsed = JSON.parse(value);
    if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
        throw new Error("JSON payload must be an object.");
    }
    return parsed as Record<string, unknown>;
}

export function parseStudioSection(value: string | null): AiSection {
    if (value && AI_SECTIONS.includes(value as AiSection)) {
        return value as AiSection;
    }
    return "prompts";
}
