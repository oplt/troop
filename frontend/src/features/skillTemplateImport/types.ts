export const SKILL_IMPORT_TARGET_FIELDS = [
    "name",
    "slug",
    "description",
    "capabilities",
    "allowed_tools",
    "tags",
    "rules_markdown",
    "ignore",
] as const;

export type SkillImportTargetField = (typeof SKILL_IMPORT_TARGET_FIELDS)[number];

export type SkillImportIssue = {
    id: string;
    field?: Exclude<SkillImportTargetField, "ignore">;
    severity: "info" | "warning" | "error";
    message: string;
    sourceHeading?: string;
    sourceExcerpt?: string;
    candidateTargets?: SkillImportTargetField[];
};

export type SkillUnmatchedSection = {
    id: string;
    heading?: string;
    content: string;
    reason: string;
};

export type SkillTemplateImportParsed = {
    name?: string;
    slug?: string;
    description?: string;
    capabilities: string[];
    allowed_tools: string[];
    tags: string[];
    rules_markdown?: string;
};

export type SkillTemplateImportDraft = {
    parsed: SkillTemplateImportParsed;
    issues: SkillImportIssue[];
    unmatched_sections: SkillUnmatchedSection[];
    confidence: number;
    raw_markdown: string;
    source_filename?: string;
};
