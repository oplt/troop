export const IMPORT_TARGET_FIELDS = [
    "name",
    "slug",
    "role",
    "description",
    "system_prompt",
    "allowed_tools",
    "capabilities",
    "tags",
    "task_filters",
    "model",
    "fallback_model",
    "escalation_path",
    "permission",
    "memory_scope",
    "output_format",
    "mission_markdown",
    "rules_markdown",
    "output_contract_markdown",
    "ignore",
] as const;

export type ImportTargetField = (typeof IMPORT_TARGET_FIELDS)[number];

export type ImportIssue = {
    id: string;
    field?: Exclude<ImportTargetField, "ignore">;
    severity: "info" | "warning" | "error";
    message: string;
    sourceHeading?: string;
    sourceExcerpt?: string;
    candidateTargets?: ImportTargetField[];
};

export type UnmatchedSection = {
    id: string;
    heading?: string;
    content: string;
    reason: string;
};

export type AgentTemplateImportParsed = {
    name?: string;
    slug?: string;
    role?: string;
    description?: string;
    system_prompt?: string;
    mission_markdown?: string;
    rules_markdown?: string;
    output_contract_markdown?: string;
    allowed_tools: string[];
    capabilities: string[];
    tags: string[];
    task_filters: string[];
    model?: string;
    fallback_model?: string;
    escalation_path?: string;
    permission?: string;
    memory_scope?: string;
    output_format?: string;
    token_budget?: number;
    time_budget_seconds?: number;
    retry_budget?: number;
    parent_template_slug?: string | null;
};

export type AgentTemplateImportDraft = {
    parsed: AgentTemplateImportParsed;
    issues: ImportIssue[];
    unmatched_sections: UnmatchedSection[];
    confidence: number;
    raw_markdown: string;
    source_filename?: string;
};

export type ToolResolution = {
    sourceTool: string;
    resolvedTool: string;
};
