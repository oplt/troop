import { z } from "zod";

import type { AgentTemplateImportDraft, AgentTemplateImportParsed, ImportIssue, UnmatchedSection } from "./types";

export const agentTemplateImportParsedSchema = z.object({
    name: z.string().trim().min(1).optional(),
    slug: z.string().trim().min(1).optional(),
    role: z.string().trim().min(1).optional(),
    description: z.string().trim().min(1).optional(),
    system_prompt: z.string().trim().min(1).optional(),
    mission_markdown: z.string().trim().min(1).optional(),
    rules_markdown: z.string().trim().min(1).optional(),
    output_contract_markdown: z.string().trim().min(1).optional(),
    allowed_tools: z.array(z.string().trim().min(1)).default([]),
    capabilities: z.array(z.string().trim().min(1)).default([]),
    tags: z.array(z.string().trim().min(1)).default([]),
    task_filters: z.array(z.string().trim().min(1)).default([]),
    model: z.string().trim().min(1).optional(),
    fallback_model: z.string().trim().min(1).optional(),
    escalation_path: z.string().trim().min(1).optional(),
    permission: z.string().trim().min(1).optional(),
    memory_scope: z.string().trim().min(1).optional(),
    output_format: z.string().trim().min(1).optional(),
    token_budget: z.number().int().nonnegative().optional(),
    time_budget_seconds: z.number().int().nonnegative().optional(),
    retry_budget: z.number().int().nonnegative().optional(),
    parent_template_slug: z.string().trim().min(1).nullable().optional(),
});

export const importIssueSchema = z.object({
    id: z.string().min(1),
    field: z.string().optional(),
    severity: z.enum(["info", "warning", "error"]),
    message: z.string().min(1),
    sourceHeading: z.string().optional(),
    sourceExcerpt: z.string().optional(),
    candidateTargets: z.array(z.string()).optional(),
});

export const unmatchedSectionSchema = z.object({
    id: z.string().min(1),
    heading: z.string().optional(),
    content: z.string().min(1),
    reason: z.string().min(1),
});

export const agentTemplateImportDraftSchema = z.object({
    parsed: agentTemplateImportParsedSchema,
    issues: z.array(importIssueSchema),
    unmatched_sections: z.array(unmatchedSectionSchema),
    confidence: z.number().min(0).max(1),
    raw_markdown: z.string(),
    source_filename: z.string().optional(),
});

export function validateAgentTemplateImportParts(
    parsed: AgentTemplateImportParsed,
    issues: ImportIssue[],
    unmatchedSections: UnmatchedSection[],
) {
    const validationIssues: ImportIssue[] = [];
    const parsedResult = agentTemplateImportParsedSchema.safeParse(parsed);
    if (!parsedResult.success) {
        parsedResult.error.issues.forEach((issue, index) => {
            validationIssues.push({
                id: `schema-parsed-${index}`,
                field: issue.path[0] as ImportIssue["field"],
                severity: "error",
                message: issue.message,
            });
        });
    }

    const issueResult = z.array(importIssueSchema).safeParse(issues);
    if (!issueResult.success) {
        issueResult.error.issues.forEach((issue, index) => {
            validationIssues.push({
                id: `schema-issues-${index}`,
                severity: "error",
                message: issue.message,
            });
        });
    }

    const unmatchedResult = z.array(unmatchedSectionSchema).safeParse(unmatchedSections);
    if (!unmatchedResult.success) {
        unmatchedResult.error.issues.forEach((issue, index) => {
            validationIssues.push({
                id: `schema-unmatched-${index}`,
                severity: "error",
                message: issue.message,
            });
        });
    }

    return validationIssues;
}

export function validateAgentTemplateImportDraft(draft: AgentTemplateImportDraft) {
    return agentTemplateImportDraftSchema.safeParse(draft);
}
