export type AiSection =
    | "prompts"
    | "playground"
    | "versions"
    | "documents"
    | "reviews"
    | "datasets";

export const AI_SECTIONS: AiSection[] = [
    "prompts",
    "playground",
    "versions",
    "documents",
    "reviews",
    "datasets",
];

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
