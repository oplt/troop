import {
    EMPTY_AGENT_TEMPLATE_FORM,
    createUniqueAgentTemplateSlug,
    parseAgentTemplateLooseList,
    stringifyAgentTemplateList,
    type AgentTemplateFormState,
} from "../agentTemplates/formState";
import { validateAgentTemplateImportParts } from "./schema";
import type {
    AgentTemplateImportDraft,
    AgentTemplateImportParsed,
    ImportIssue,
    ImportTargetField,
    ToolResolution,
    UnmatchedSection,
} from "./types";

type ParseAgentTemplateMarkdownOptions = {
    markdown: string;
    fileName?: string;
    toolCatalog?: string[];
};

type FrontmatterParseResult = {
    data: Record<string, unknown>;
    body: string;
    issues: ImportIssue[];
};

type MarkdownSection = {
    id: string;
    heading?: string;
    level: number;
    normalizedHeading: string;
    content: string;
    listItems: string[];
    codeBlocks: string[];
};

type ParsedMarkdownDocument = {
    title?: string;
    preamble: string;
    sections: MarkdownSection[];
};

type RebuildDraftOptions = {
    rawMarkdown: string;
    sourceFilename?: string;
    baseIssues?: ImportIssue[];
    frontmatterData?: Record<string, unknown>;
    toolCatalog?: string[];
};

const ROLE_FALLBACK = "specialist";

const SECTION_TARGETS: Array<{ patterns: string[]; field: ImportTargetField }> = [
    { patterns: ["mission", "purpose", "scope"], field: "mission_markdown" },
    { patterns: ["rules", "guardrails", "constraints", "policy"], field: "rules_markdown" },
    { patterns: ["output", "output contract", "deliverables", "acceptance"], field: "output_contract_markdown" },
    { patterns: ["system prompt", "operating instructions", "instructions", "prompt"], field: "system_prompt" },
    { patterns: ["description", "overview", "summary"], field: "description" },
    { patterns: ["tools", "tool access", "allowed tools"], field: "allowed_tools" },
    { patterns: ["capabilities", "work surface"], field: "capabilities" },
    { patterns: ["tags"], field: "tags" },
    { patterns: ["task filters", "routing", "route"], field: "task_filters" },
    { patterns: ["model"], field: "model" },
];

const APPROVAL_FIELDS: ImportTargetField[] = [
    "system_prompt",
    "mission_markdown",
    "rules_markdown",
    "output_contract_markdown",
];

function normalizeWhitespace(value: string) {
    return value.replace(/\r/g, "").trim();
}

function slugify(value: string) {
    return value
        .toLowerCase()
        .trim()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/(^-|-$)/g, "");
}

function titleFromSlug(value: string) {
    return value
        .split("-")
        .filter(Boolean)
        .map((part) => part[0]?.toUpperCase() + part.slice(1))
        .join(" ");
}

function dedupe(items: string[]) {
    return Array.from(new Set(items.map((item) => item.trim()).filter(Boolean)));
}

function splitInlineList(value: string) {
    return value
        .split(/[,\n]/g)
        .map((item) => item.replace(/^(?:[-*+]|\d+\.)\s+/, "").trim())
        .filter(Boolean);
}

function parseNumericValue(value: unknown): number | undefined {
    if (typeof value === "number" && Number.isFinite(value)) {
        return value;
    }
    if (typeof value === "string" && value.trim()) {
        const parsed = Number(value.trim());
        if (Number.isFinite(parsed)) {
            return parsed;
        }
    }
    return undefined;
}

function normalizeHeading(value?: string) {
    return value
        ?.toLowerCase()
        .replace(/[`*_]/g, "")
        .replace(/[^a-z0-9]+/g, " ")
        .trim() ?? "";
}

function makeIssue(
    id: string,
    severity: ImportIssue["severity"],
    message: string,
    overrides: Partial<Omit<ImportIssue, "id" | "severity" | "message">> = {},
): ImportIssue {
    return {
        id,
        severity,
        message,
        ...overrides,
    };
}

function safeString(value: unknown) {
    return typeof value === "string" ? normalizeWhitespace(value) : "";
}

function safeStringArray(value: unknown) {
    if (Array.isArray(value)) {
        return dedupe(value.filter((item): item is string => typeof item === "string"));
    }
    if (typeof value === "string") {
        return dedupe(splitInlineList(value));
    }
    return [];
}

function frontmatterKeyCandidates(key: string) {
    return [key, key.toLowerCase(), key.replace(/_/g, "-"), key.replace(/-/g, "_")];
}

function getFrontmatterValue(frontmatterData: Record<string, unknown>, key: string) {
    for (const candidate of frontmatterKeyCandidates(key)) {
        if (candidate in frontmatterData) {
            return frontmatterData[candidate];
        }
    }
    return undefined;
}

function parseYamlScalar(value: string): unknown {
    const trimmed = value.trim();
    if (!trimmed) return "";
    if ((trimmed.startsWith("\"") && trimmed.endsWith("\"")) || (trimmed.startsWith("'") && trimmed.endsWith("'"))) {
        return trimmed.slice(1, -1);
    }
    if (trimmed === "true") return true;
    if (trimmed === "false") return false;
    if (trimmed === "null") return null;
    const numeric = Number(trimmed);
    if (!Number.isNaN(numeric) && trimmed === String(numeric)) {
        return numeric;
    }
    if (trimmed.startsWith("[") && trimmed.endsWith("]")) {
        return splitInlineList(trimmed.slice(1, -1));
    }
    return trimmed;
}

function parseSimpleFrontmatter(frontmatterText: string): Record<string, unknown> {
    const lines = frontmatterText.replace(/\r/g, "").split("\n");
    const data: Record<string, unknown> = {};

    for (let index = 0; index < lines.length; index += 1) {
        const line = lines[index];
        if (!line.trim() || line.trim().startsWith("#")) {
            continue;
        }

        const match = line.match(/^([A-Za-z0-9_-]+):\s*(.*)$/);
        if (!match) {
            continue;
        }

        const [, rawKey, rawValue] = match;
        const key = rawKey.trim();
        const value = rawValue.trim();

        if (value === "|" || value === ">") {
            const block: string[] = [];
            let cursor = index + 1;
            while (cursor < lines.length && (/^\s+/.test(lines[cursor]) || !lines[cursor].trim())) {
                block.push(lines[cursor].replace(/^\s{2}/, ""));
                cursor += 1;
            }
            index = cursor - 1;
            data[key] = normalizeWhitespace(block.join("\n"));
            continue;
        }

        if (!value) {
            const listItems: string[] = [];
            let cursor = index + 1;
            while (cursor < lines.length) {
                const listMatch = lines[cursor].match(/^\s*-\s+(.+)$/);
                if (!listMatch) {
                    break;
                }
                listItems.push(listMatch[1].trim());
                cursor += 1;
            }
            if (listItems.length > 0) {
                data[key] = listItems;
                index = cursor - 1;
                continue;
            }
        }

        data[key] = parseYamlScalar(value);
    }

    return data;
}

function parseFrontmatter(markdown: string): FrontmatterParseResult {
    const issues: ImportIssue[] = [];
    const normalizedMarkdown = markdown.replace(/\r/g, "");
    if (!normalizedMarkdown.startsWith("---\n")) {
        return { data: {}, body: normalizedMarkdown, issues };
    }

    const closingIndex = normalizedMarkdown.indexOf("\n---\n", 4);
    if (closingIndex === -1) {
        issues.push(makeIssue(
            "frontmatter-malformed",
            "warning",
            "Frontmatter block could not be closed. Parsed the Markdown body anyway.",
            { sourceExcerpt: normalizedMarkdown.slice(0, 180) },
        ));
        return { data: {}, body: normalizedMarkdown, issues };
    }

    const frontmatterText = normalizedMarkdown.slice(4, closingIndex);
    const body = normalizedMarkdown.slice(closingIndex + 5);

    try {
        return {
            data: parseSimpleFrontmatter(frontmatterText),
            body,
            issues,
        };
    } catch {
        issues.push(makeIssue(
            "frontmatter-parse-warning",
            "warning",
            "Frontmatter parsing failed. Parsed the Markdown body and preserved raw content for review.",
            { sourceExcerpt: frontmatterText.slice(0, 180) },
        ));
        return { data: {}, body, issues };
    }
}

function parseMarkdownDocument(markdownBody: string): ParsedMarkdownDocument {
    const lines = markdownBody.replace(/\r/g, "").split("\n");
    const sections: MarkdownSection[] = [];
    let currentHeading: string | undefined;
    let currentHeadingLevel = 0;
    let currentLines: string[] = [];
    const preamble: string[] = [];

    const pushSection = () => {
        const content = normalizeWhitespace(currentLines.join("\n"));
        if (!currentHeading && !content) {
            currentLines = [];
            return;
        }
        if (!currentHeading) {
            if (content) {
                preamble.push(content);
            }
            currentLines = [];
            return;
        }

        const listItems = Array.from(content.matchAll(/^(?:[-*+]|\d+\.)\s+(.+)$/gm)).map((match) => match[1].trim());
        const codeBlocks = Array.from(content.matchAll(/```[\w-]*\n([\s\S]*?)```/gm)).map((match) => normalizeWhitespace(match[1]));
        sections.push({
            id: `section-${sections.length + 1}`,
            heading: currentHeading,
            level: currentHeadingLevel,
            normalizedHeading: normalizeHeading(currentHeading),
            content,
            listItems,
            codeBlocks,
        });
        currentLines = [];
    };

    for (const line of lines) {
        const headingMatch = line.match(/^#{1,6}\s+(.+)$/);
        if (headingMatch) {
            pushSection();
            currentHeading = headingMatch[1].trim();
            currentHeadingLevel = line.match(/^#+/)?.[0].length ?? 0;
            continue;
        }
        currentLines.push(line);
    }

    pushSection();

    const title = sections.find((section) => section.level === 1)?.heading;
    return {
        title,
        preamble: preamble.join("\n\n"),
        sections,
    };
}

function resolveSectionTarget(section: MarkdownSection): ImportTargetField | null {
    for (const candidate of SECTION_TARGETS) {
        if (candidate.patterns.some((pattern) => section.normalizedHeading.includes(pattern))) {
            return candidate.field;
        }
    }
    return null;
}

function appendMarkdown(currentValue: string | undefined, nextValue: string) {
    const normalizedCurrent = normalizeWhitespace(currentValue ?? "");
    const normalizedNext = normalizeWhitespace(nextValue);
    if (!normalizedNext) {
        return normalizedCurrent;
    }
    if (!normalizedCurrent) {
        return normalizedNext;
    }
    return `${normalizedCurrent}\n\n${normalizedNext}`;
}

function extractKeyValueLines(section: MarkdownSection) {
    const result: Record<string, string> = {};
    Array.from(section.content.matchAll(/^([A-Za-z _-]+):\s*(.+)$/gm)).forEach((match) => {
        result[normalizeHeading(match[1])] = match[2].trim();
    });
    return result;
}

function canonicalizeToolName(tool: string, toolCatalog: string[]) {
    const normalizedTool = slugify(tool);
    const direct = toolCatalog.find((candidate) => candidate.toLowerCase() === tool.toLowerCase());
    if (direct) {
        return direct;
    }
    const bySlug = toolCatalog.find((candidate) => slugify(candidate) === normalizedTool);
    return bySlug ?? null;
}

function collectUnknownTools(parsed: AgentTemplateImportParsed, toolCatalog: string[]) {
    if (toolCatalog.length === 0) {
        return [];
    }

    return parsed.allowed_tools.filter((tool) => !canonicalizeToolName(tool, toolCatalog));
}

function inferCapabilitiesAndTagsFromSections(
    sections: MarkdownSection[],
    parsed: AgentTemplateImportParsed,
) {
    const inferredCapabilities = [...parsed.capabilities];
    const inferredTags = [...parsed.tags];
    const inferredTaskFilters = [...parsed.task_filters];

    sections.forEach((section) => {
        const heading = section.normalizedHeading;
        if (heading.includes("capabilities") || heading.includes("work surface")) {
            inferredCapabilities.push(...section.listItems);
        }
        if (heading.includes("tags")) {
            inferredTags.push(...section.listItems);
        }
        if (heading.includes("routing") || heading.includes("task filters")) {
            inferredTaskFilters.push(...section.listItems, ...splitInlineList(section.content));
        }
    });

    return {
        capabilities: dedupe(inferredCapabilities),
        tags: dedupe(inferredTags),
        task_filters: dedupe(inferredTaskFilters),
    };
}

function inferConfidence(parsed: AgentTemplateImportParsed, issues: ImportIssue[], unmatchedSections: UnmatchedSection[]) {
    let confidence = 1;
    confidence -= issues.filter((issue) => issue.severity === "error").length * 0.22;
    confidence -= issues.filter((issue) => issue.severity === "warning").length * 0.08;
    confidence -= unmatchedSections.length * 0.05;
    if (!parsed.system_prompt?.trim()) {
        confidence -= 0.05;
    }
    if (!parsed.mission_markdown?.trim()) {
        confidence -= 0.05;
    }
    return Math.max(0.1, Math.min(1, Number(confidence.toFixed(2))));
}

function buildDraftIssues(
    parsed: AgentTemplateImportParsed,
    unmatchedSections: UnmatchedSection[],
    options: RebuildDraftOptions,
): ImportIssue[] {
    const issues = [...(options.baseIssues ?? [])];

    if (!parsed.name?.trim() && parsed.slug?.trim()) {
        issues.push(makeIssue(
            "missing-name-inferred",
            "warning",
            "Name was missing. Review the inferred display name before continuing.",
            {
                field: "name",
                sourceExcerpt: parsed.slug,
                candidateTargets: ["name", "slug", "ignore"],
            },
        ));
    }

    if (!parsed.slug?.trim() && parsed.name?.trim()) {
        issues.push(makeIssue(
            "missing-slug-inferred",
            "info",
            "Slug will be generated from the template name unless you override it.",
            {
                field: "slug",
                sourceExcerpt: parsed.name,
                candidateTargets: ["slug", "ignore"],
            },
        ));
    }

    if (!parsed.system_prompt?.trim()) {
        issues.push(makeIssue(
            "missing-system-prompt",
            "warning",
            "Operating instructions were not found. Review system prompt before continuing.",
            {
                field: "system_prompt",
                candidateTargets: APPROVAL_FIELDS,
            },
        ));
    }

    if (!parsed.mission_markdown?.trim() && !parsed.description?.trim()) {
        issues.push(makeIssue(
            "missing-mission",
            "warning",
            "Mission or scope section is missing. Add ownership guidance before save.",
            {
                field: "mission_markdown",
                candidateTargets: ["mission_markdown", "description", "ignore"],
            },
        ));
    }

    collectUnknownTools(parsed, options.toolCatalog ?? []).forEach((tool) => {
        issues.push(makeIssue(
            `unknown-tool-${slugify(tool)}`,
            "warning",
            `Tool "${tool}" is not in the current catalog. Map it or keep it explicitly.`,
            {
                field: "allowed_tools",
                sourceExcerpt: tool,
                candidateTargets: ["allowed_tools", "ignore"],
            },
        ));
    });

    unmatchedSections.forEach((section) => {
        issues.push(makeIssue(
            `unmatched-${section.id}`,
            "info",
            "Section was preserved but not mapped automatically.",
            {
                sourceHeading: section.heading,
                sourceExcerpt: section.content.slice(0, 180),
                candidateTargets: ["system_prompt", "mission_markdown", "rules_markdown", "output_contract_markdown", "ignore"],
            },
        ));
    });

    return issues.concat(validateAgentTemplateImportParts(parsed, issues, unmatchedSections));
}

function rebuildDraft(
    parsed: AgentTemplateImportParsed,
    unmatchedSections: UnmatchedSection[],
    options: RebuildDraftOptions,
): AgentTemplateImportDraft {
    const issues = buildDraftIssues(parsed, unmatchedSections, options);
    return {
        parsed,
        unmatched_sections: unmatchedSections,
        issues,
        confidence: inferConfidence(parsed, issues, unmatchedSections),
        raw_markdown: options.rawMarkdown,
        source_filename: options.sourceFilename,
    };
}

function collectSectionContent(section: MarkdownSection) {
    return normalizeWhitespace(section.content);
}

function parseRole(value: unknown) {
    const normalized = safeString(value).toLowerCase();
    if (normalized === "manager" || normalized === "reviewer" || normalized === "specialist") {
        return normalized;
    }
    return undefined;
}

function stemFileName(fileName?: string) {
    return fileName?.replace(/\.(md|markdown)$/i, "").trim() ?? "";
}

export function parseAgentTemplateMarkdown(options: ParseAgentTemplateMarkdownOptions): AgentTemplateImportDraft {
    const frontmatter = parseFrontmatter(options.markdown);
    const document = parseMarkdownDocument(frontmatter.body);
    const frontmatterData = frontmatter.data;
    const sourceFilename = options.fileName;
    const parseIssues: ImportIssue[] = [];

    const mappedSections = new Set<string>();
    const unmatchedSections: UnmatchedSection[] = [];

    let parsed: AgentTemplateImportParsed = {
        name: safeString(getFrontmatterValue(frontmatterData, "name")) || undefined,
        slug: safeString(getFrontmatterValue(frontmatterData, "slug")) || undefined,
        role: parseRole(getFrontmatterValue(frontmatterData, "role")) ?? ROLE_FALLBACK,
        description: safeString(getFrontmatterValue(frontmatterData, "description")) || undefined,
        system_prompt: safeString(getFrontmatterValue(frontmatterData, "system_prompt")) || undefined,
        mission_markdown: safeString(getFrontmatterValue(frontmatterData, "mission_markdown")) || undefined,
        rules_markdown: safeString(getFrontmatterValue(frontmatterData, "rules_markdown")) || undefined,
        output_contract_markdown: safeString(getFrontmatterValue(frontmatterData, "output_contract_markdown")) || undefined,
        allowed_tools: safeStringArray(getFrontmatterValue(frontmatterData, "allowed_tools") ?? getFrontmatterValue(frontmatterData, "tools")),
        capabilities: safeStringArray(getFrontmatterValue(frontmatterData, "capabilities")),
        tags: safeStringArray(getFrontmatterValue(frontmatterData, "tags")),
        task_filters: safeStringArray(getFrontmatterValue(frontmatterData, "task_filters")),
        model: safeString(getFrontmatterValue(frontmatterData, "model")) || undefined,
        fallback_model: safeString(getFrontmatterValue(frontmatterData, "fallback_model")) || undefined,
        escalation_path: safeString(getFrontmatterValue(frontmatterData, "escalation_path")) || undefined,
        permission: safeString(getFrontmatterValue(frontmatterData, "permission")) || undefined,
        memory_scope: safeString(getFrontmatterValue(frontmatterData, "memory_scope")) || undefined,
        output_format: safeString(getFrontmatterValue(frontmatterData, "output_format")) || undefined,
        token_budget: parseNumericValue(getFrontmatterValue(frontmatterData, "token_budget")),
        time_budget_seconds: parseNumericValue(getFrontmatterValue(frontmatterData, "time_budget_seconds")),
        retry_budget: parseNumericValue(getFrontmatterValue(frontmatterData, "retry_budget")),
        parent_template_slug: safeString(getFrontmatterValue(frontmatterData, "parent_template_slug")) || null,
    };

    if (!parsed.name && document.title) {
        parsed.name = document.title;
    }
    if (!parsed.description && document.preamble) {
        parsed.description = document.preamble.split("\n\n")[0];
    }

    document.sections.forEach((section) => {
        const target = resolveSectionTarget(section);
        const content = collectSectionContent(section);
        if (!content) {
            return;
        }

        const keyValues = extractKeyValueLines(section);
        if (section.normalizedHeading.includes("runtime") || section.normalizedHeading.includes("model")) {
            parsed = {
                ...parsed,
                model: parsed.model ?? keyValues.model,
                fallback_model: parsed.fallback_model ?? keyValues["fallback model"],
                escalation_path: parsed.escalation_path ?? keyValues["escalation path"],
                permission: parsed.permission ?? keyValues.permission,
                memory_scope: parsed.memory_scope ?? keyValues["memory scope"],
                output_format: parsed.output_format ?? keyValues["output format"],
            };
        }

        if (target === "allowed_tools") {
            parsed.allowed_tools = dedupe([
                ...parsed.allowed_tools,
                ...(section.listItems.length > 0 ? section.listItems : splitInlineList(content)),
            ]);
            mappedSections.add(section.id);
            return;
        }

        if (target === "capabilities") {
            parsed.capabilities = dedupe([
                ...parsed.capabilities,
                ...(section.listItems.length > 0 ? section.listItems : splitInlineList(content)),
            ]);
            mappedSections.add(section.id);
            return;
        }

        if (target === "tags") {
            parsed.tags = dedupe([
                ...parsed.tags,
                ...(section.listItems.length > 0 ? section.listItems : splitInlineList(content)),
            ]);
            mappedSections.add(section.id);
            return;
        }

        if (target === "task_filters") {
            parsed.task_filters = dedupe([
                ...parsed.task_filters,
                ...(section.listItems.length > 0 ? section.listItems : parseAgentTemplateLooseList(content)),
            ]);
            mappedSections.add(section.id);
            return;
        }

        if (target && target in parsed) {
            const currentValue = parsed[target];
            if (typeof currentValue === "string" || typeof currentValue === "undefined" || currentValue === null) {
                parsed = {
                    ...parsed,
                    [target]: appendMarkdown(typeof currentValue === "string" ? currentValue : undefined, content),
                };
                mappedSections.add(section.id);
                return;
            }
        }

        unmatchedSections.push({
            id: section.id,
            heading: section.heading,
            content,
            reason: target ? "Section content could not be normalized into the target field safely." : "No deterministic field mapping for heading.",
        });
    });

    const inferred = inferCapabilitiesAndTagsFromSections(document.sections, parsed);
    parsed = {
        ...parsed,
        capabilities: inferred.capabilities,
        tags: inferred.tags,
        task_filters: inferred.task_filters,
    };

    if (!parsed.slug?.trim()) {
        const slugSource = parsed.name || stemFileName(sourceFilename);
        parsed.slug = slugSource ? slugify(slugSource) : undefined;
        if (parsed.slug) {
            parseIssues.push(makeIssue(
                "missing-slug-inferred",
                "info",
                "Slug was inferred from the template name or filename.",
                {
                    field: "slug",
                    sourceExcerpt: slugSource,
                    candidateTargets: ["slug", "ignore"],
                },
            ));
        }
    }

    if (!parsed.name?.trim() && parsed.slug?.trim()) {
        parsed.name = titleFromSlug(parsed.slug);
        parseIssues.push(makeIssue(
            "missing-name-inferred",
            "warning",
            "Name was missing. Review the inferred display name before continuing.",
            {
                field: "name",
                sourceExcerpt: parsed.slug,
                candidateTargets: ["name", "slug", "ignore"],
            },
        ));
    }

    if (!parsed.description?.trim() && parsed.mission_markdown?.trim()) {
        parsed.description = parsed.mission_markdown.split("\n")[0]?.trim() || undefined;
    }

    parsed.allowed_tools = dedupe(parsed.allowed_tools.map((tool) => canonicalizeToolName(tool, options.toolCatalog ?? []) ?? tool));

    return rebuildDraft(parsed, unmatchedSections, {
        rawMarkdown: options.markdown,
        sourceFilename,
        baseIssues: [...frontmatter.issues, ...parseIssues],
        frontmatterData,
        toolCatalog: options.toolCatalog,
    });
}

export function updateImportDraftParsedField(
    draft: AgentTemplateImportDraft,
    field: keyof AgentTemplateImportParsed,
    value: string | string[] | number | null | undefined,
    toolCatalog: string[] = [],
) {
    const parsed: AgentTemplateImportParsed = {
        ...draft.parsed,
        [field]: Array.isArray(value) ? dedupe(value) : value ?? undefined,
    };

    return rebuildDraft(parsed, draft.unmatched_sections, {
        rawMarkdown: draft.raw_markdown,
        sourceFilename: draft.source_filename,
        toolCatalog,
    });
}

export function mapUnknownTool(
    draft: AgentTemplateImportDraft,
    resolution: ToolResolution,
    toolCatalog: string[] = [],
) {
    const parsed: AgentTemplateImportParsed = {
        ...draft.parsed,
        allowed_tools: dedupe(
            draft.parsed.allowed_tools.map((tool) => (tool === resolution.sourceTool ? resolution.resolvedTool : tool)),
        ),
    };

    return rebuildDraft(parsed, draft.unmatched_sections, {
        rawMarkdown: draft.raw_markdown,
        sourceFilename: draft.source_filename,
        toolCatalog,
    });
}

export function applyUnmatchedSectionMapping(
    draft: AgentTemplateImportDraft,
    sectionId: string,
    target: ImportTargetField,
    toolCatalog: string[] = [],
) {
    const section = draft.unmatched_sections.find((item) => item.id === sectionId);
    if (!section) {
        return draft;
    }

    const nextUnmatched = draft.unmatched_sections.filter((item) => item.id !== sectionId);
    let nextParsed = { ...draft.parsed };

    if (target !== "ignore") {
        if (target === "allowed_tools") {
            nextParsed.allowed_tools = dedupe([...nextParsed.allowed_tools, ...splitInlineList(section.content)]);
        } else if (target === "capabilities") {
            nextParsed.capabilities = dedupe([...nextParsed.capabilities, ...splitInlineList(section.content)]);
        } else if (target === "tags") {
            nextParsed.tags = dedupe([...nextParsed.tags, ...splitInlineList(section.content)]);
        } else if (target === "task_filters") {
            nextParsed.task_filters = dedupe([...nextParsed.task_filters, ...parseAgentTemplateLooseList(section.content)]);
        } else if (target in nextParsed) {
            const currentValue = nextParsed[target as keyof AgentTemplateImportParsed];
            if (typeof currentValue === "string" || typeof currentValue === "undefined" || currentValue === null) {
                nextParsed = {
                    ...nextParsed,
                    [target]: appendMarkdown(typeof currentValue === "string" ? currentValue : undefined, section.content),
                };
            }
        }
    }

    return rebuildDraft(nextParsed, nextUnmatched, {
        rawMarkdown: draft.raw_markdown,
        sourceFilename: draft.source_filename,
        toolCatalog,
    });
}

export function getUnknownTools(draft: AgentTemplateImportDraft, toolCatalog: string[] = []) {
    return collectUnknownTools(draft.parsed, toolCatalog);
}

export function getImportConfidenceLabel(confidence: number) {
    if (confidence >= 0.8) return "high";
    if (confidence >= 0.55) return "medium";
    return "low";
}

export function draftToAgentTemplateFormState(draft: AgentTemplateImportDraft): AgentTemplateFormState {
    return {
        ...EMPTY_AGENT_TEMPLATE_FORM,
        name: draft.parsed.name ?? "",
        slug: draft.parsed.slug ?? "",
        description: draft.parsed.description ?? "",
        role: draft.parsed.role ?? ROLE_FALLBACK,
        system_prompt: draft.parsed.system_prompt ?? "",
        mission_markdown: draft.parsed.mission_markdown ?? draft.parsed.description ?? "",
        rules_markdown: draft.parsed.rules_markdown ?? "",
        output_contract_markdown: draft.parsed.output_contract_markdown ?? "",
        parent_template_slug: draft.parsed.parent_template_slug ?? "",
        capabilities: stringifyAgentTemplateList(draft.parsed.capabilities),
        allowed_tools: stringifyAgentTemplateList(draft.parsed.allowed_tools),
        tags: stringifyAgentTemplateList(draft.parsed.tags),
        task_filters: draft.parsed.task_filters.join("\n"),
        model: draft.parsed.model ?? "",
        fallback_model: draft.parsed.fallback_model ?? "",
        escalation_path: draft.parsed.escalation_path ?? "",
        permission: draft.parsed.permission ?? EMPTY_AGENT_TEMPLATE_FORM.permission,
        memory_scope: draft.parsed.memory_scope ?? EMPTY_AGENT_TEMPLATE_FORM.memory_scope,
        output_format: draft.parsed.output_format ?? EMPTY_AGENT_TEMPLATE_FORM.output_format,
        token_budget: draft.parsed.token_budget ? String(draft.parsed.token_budget) : EMPTY_AGENT_TEMPLATE_FORM.token_budget,
        time_budget_seconds: draft.parsed.time_budget_seconds ? String(draft.parsed.time_budget_seconds) : EMPTY_AGENT_TEMPLATE_FORM.time_budget_seconds,
        retry_budget: draft.parsed.retry_budget ? String(draft.parsed.retry_budget) : EMPTY_AGENT_TEMPLATE_FORM.retry_budget,
    };
}

export function buildImportBannerText(draft: AgentTemplateImportDraft) {
    const warningCount = draft.issues.filter((issue) => issue.severity === "warning").length;
    if (warningCount > 0) {
        return `Imported from Markdown — ${warningCount} warning${warningCount === 1 ? "" : "s"}`;
    }
    return "Imported from Markdown";
}

export function createImportedSourceSummary(draft: AgentTemplateImportDraft) {
    return {
        fileName: draft.source_filename ?? "Markdown file",
        rawMarkdown: draft.raw_markdown,
        bannerText: buildImportBannerText(draft),
        warningCount: draft.issues.filter((issue) => issue.severity === "warning").length,
    };
}

export function buildAgentTemplateImportDraftFromResolvedValues(
    values: Partial<AgentTemplateImportParsed> & Pick<AgentTemplateImportDraft, "raw_markdown">,
) {
    const parsed: AgentTemplateImportParsed = {
        role: ROLE_FALLBACK,
        allowed_tools: [],
        capabilities: [],
        tags: [],
        task_filters: [],
        ...values,
    };

    if (!parsed.slug?.trim() && parsed.name?.trim()) {
        parsed.slug = createUniqueAgentTemplateSlug(parsed.name, []);
    }

    return rebuildDraft(parsed, [], {
        rawMarkdown: values.raw_markdown,
        toolCatalog: [],
    });
}

// TODO: add optional LLM-assisted repair hook here when local orchestration support exists.
