import type { SkillPack } from "../../api/orchestration";
import type {
    SkillImportIssue,
    SkillImportTargetField,
    SkillTemplateImportDraft,
    SkillTemplateImportParsed,
    SkillUnmatchedSection,
} from "./types";

type ParseSkillTemplateMarkdownOptions = {
    markdown: string;
    fileName?: string;
    toolCatalog?: string[];
};

type SkillTemplateFormStateLike = Pick<
    SkillPack,
    "name" | "slug" | "description" | "capabilities" | "allowed_tools" | "tags" | "rules_markdown"
>;

type MarkdownSection = {
    id: string;
    heading?: string;
    level: number;
    normalizedHeading: string;
    content: string;
    listItems: string[];
};

const SECTION_TARGETS: Array<{ patterns: string[]; field: SkillImportTargetField }> = [
    { patterns: ["description", "overview", "summary"], field: "description" },
    { patterns: ["capabilities", "capability", "use this skill when", "when to use"], field: "capabilities" },
    { patterns: ["tools", "required tools", "allowed tools"], field: "allowed_tools" },
    { patterns: ["tags"], field: "tags" },
    { patterns: ["rules", "instructions", "injected rules", "behavior rules"], field: "rules_markdown" },
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

function splitInlineList(value: string) {
    return value
        .split(/[,\n]/g)
        .map((item) => item.replace(/^(?:[-*+]|\d+\.)\s+/, "").trim())
        .filter(Boolean);
}

function dedupe(items: string[]) {
    return Array.from(new Set(items.map((item) => item.trim()).filter(Boolean)));
}

function normalizeHeading(value?: string) {
    return value
        ?.toLowerCase()
        .replace(/[`*_]/g, "")
        .replace(/[^a-z0-9]+/g, " ")
        .trim() ?? "";
}

function appendText(currentValue: string | undefined, nextValue: string) {
    const left = normalizeWhitespace(currentValue ?? "");
    const right = normalizeWhitespace(nextValue);
    if (!right) {
        return left;
    }
    if (!left) {
        return right;
    }
    return `${left}\n\n${right}`;
}

function parseFrontmatter(markdown: string) {
    const issues: SkillImportIssue[] = [];
    const normalizedMarkdown = markdown.replace(/\r/g, "");
    if (!normalizedMarkdown.startsWith("---\n")) {
        return { data: {} as Record<string, unknown>, body: normalizedMarkdown, issues };
    }

    const closingIndex = normalizedMarkdown.indexOf("\n---\n", 4);
    if (closingIndex === -1) {
        issues.push({
            id: "frontmatter-malformed",
            severity: "warning",
            message: "Frontmatter block could not be closed. Parsed the Markdown body anyway.",
            sourceExcerpt: normalizedMarkdown.slice(0, 180),
        });
        return { data: {}, body: normalizedMarkdown, issues };
    }

    const frontmatterText = normalizedMarkdown.slice(4, closingIndex);
    const body = normalizedMarkdown.slice(closingIndex + 5);
    const data: Record<string, unknown> = {};

    frontmatterText.split("\n").forEach((line) => {
        const match = line.match(/^([A-Za-z0-9_-]+):\s*(.+)$/);
        if (!match) {
            return;
        }
        const [, key, rawValue] = match;
        const value = rawValue.trim();
        data[key] = value.startsWith("[") && value.endsWith("]")
            ? splitInlineList(value.slice(1, -1))
            : value;
    });

    return { data, body, issues };
}

function parseMarkdownDocument(markdownBody: string) {
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
        sections.push({
            id: `section-${sections.length + 1}`,
            heading: currentHeading,
            level: currentHeadingLevel,
            normalizedHeading: normalizeHeading(currentHeading),
            content,
            listItems: Array.from(content.matchAll(/^(?:[-*+]|\d+\.)\s+(.+)$/gm)).map((match) => match[1].trim()),
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

    return {
        title: sections.find((section) => section.level === 1)?.heading,
        preamble: preamble.join("\n\n"),
        sections,
    };
}

function resolveSectionTarget(section: MarkdownSection): SkillImportTargetField | null {
    for (const candidate of SECTION_TARGETS) {
        if (candidate.patterns.some((pattern) => section.normalizedHeading.includes(pattern))) {
            return candidate.field;
        }
    }
    return null;
}

function canonicalizeToolName(tool: string, toolCatalog: string[]) {
    const direct = toolCatalog.find((candidate) => candidate.toLowerCase() === tool.toLowerCase());
    if (direct) {
        return direct;
    }
    const bySlug = toolCatalog.find((candidate) => slugify(candidate) === slugify(tool));
    return bySlug ?? null;
}

function buildIssues(
    parsed: SkillTemplateImportParsed,
    unmatchedSections: SkillUnmatchedSection[],
    baseIssues: SkillImportIssue[],
    toolCatalog: string[],
) {
    const issues = [...baseIssues];

    if (!parsed.name?.trim() && parsed.slug?.trim()) {
        issues.push({
            id: "missing-name-inferred",
            field: "name",
            severity: "warning",
            message: "Name was missing. Review the inferred skill name before continuing.",
            sourceExcerpt: parsed.slug,
            candidateTargets: ["name", "slug", "ignore"],
        });
    }

    if (!parsed.slug?.trim() && parsed.name?.trim()) {
        issues.push({
            id: "missing-slug-inferred",
            field: "slug",
            severity: "info",
            message: "Slug will be generated from the skill name unless you override it.",
            sourceExcerpt: parsed.name,
            candidateTargets: ["slug", "ignore"],
        });
    }

    if (!parsed.rules_markdown?.trim()) {
        issues.push({
            id: "missing-rules",
            field: "rules_markdown",
            severity: "warning",
            message: "No injected rules were found. A skill should usually contribute behavior, not only labels.",
            candidateTargets: ["rules_markdown", "description", "ignore"],
        });
    }

    parsed.allowed_tools.forEach((tool) => {
        if (toolCatalog.length > 0 && !canonicalizeToolName(tool, toolCatalog)) {
            issues.push({
                id: `unknown-tool-${slugify(tool)}`,
                field: "allowed_tools",
                severity: "warning",
                message: `Tool "${tool}" is not in the current catalog. Map it or keep it explicitly.`,
                sourceExcerpt: tool,
                candidateTargets: ["allowed_tools", "ignore"],
            });
        }
    });

    unmatchedSections.forEach((section) => {
        issues.push({
            id: `unmatched-${section.id}`,
            severity: "info",
            message: "Section was preserved but not mapped automatically.",
            sourceHeading: section.heading,
            sourceExcerpt: section.content.slice(0, 180),
            candidateTargets: ["description", "rules_markdown", "tags", "ignore"],
        });
    });

    return issues;
}

function inferConfidence(parsed: SkillTemplateImportParsed, issues: SkillImportIssue[], unmatchedSections: SkillUnmatchedSection[]) {
    let confidence = 1;
    confidence -= issues.filter((issue) => issue.severity === "error").length * 0.2;
    confidence -= issues.filter((issue) => issue.severity === "warning").length * 0.08;
    confidence -= unmatchedSections.length * 0.05;
    if (!parsed.rules_markdown?.trim()) {
        confidence -= 0.08;
    }
    return Math.max(0.1, Math.min(1, Number(confidence.toFixed(2))));
}

function rebuildDraft(
    parsed: SkillTemplateImportParsed,
    unmatchedSections: SkillUnmatchedSection[],
    markdown: string,
    fileName?: string,
    baseIssues: SkillImportIssue[] = [],
    toolCatalog: string[] = [],
): SkillTemplateImportDraft {
    const issues = buildIssues(parsed, unmatchedSections, baseIssues, toolCatalog);
    return {
        parsed,
        issues,
        unmatched_sections: unmatchedSections,
        confidence: inferConfidence(parsed, issues, unmatchedSections),
        raw_markdown: markdown,
        source_filename: fileName,
    };
}

export function parseSkillTemplateMarkdown(options: ParseSkillTemplateMarkdownOptions): SkillTemplateImportDraft {
    const frontmatter = parseFrontmatter(options.markdown);
    const document = parseMarkdownDocument(frontmatter.body);
    const frontmatterData = frontmatter.data;
    const parseIssues = [...frontmatter.issues];
    const unmatchedSections: SkillUnmatchedSection[] = [];

    const parsed: SkillTemplateImportParsed = {
        name: typeof frontmatterData.name === "string" ? normalizeWhitespace(frontmatterData.name) : undefined,
        slug: typeof frontmatterData.slug === "string" ? normalizeWhitespace(frontmatterData.slug) : undefined,
        description: typeof frontmatterData.description === "string" ? normalizeWhitespace(frontmatterData.description) : undefined,
        capabilities: Array.isArray(frontmatterData.capabilities) ? dedupe(frontmatterData.capabilities as string[]) : [],
        allowed_tools: Array.isArray(frontmatterData.allowed_tools) ? dedupe(frontmatterData.allowed_tools as string[]) : [],
        tags: Array.isArray(frontmatterData.tags) ? dedupe(frontmatterData.tags as string[]) : [],
        rules_markdown: typeof frontmatterData.rules_markdown === "string" ? normalizeWhitespace(frontmatterData.rules_markdown) : undefined,
    };

    if (!parsed.name && document.title) {
        parsed.name = document.title;
    }
    if (!parsed.description && document.preamble) {
        parsed.description = document.preamble.split("\n\n")[0];
    }

    document.sections.forEach((section) => {
        const target = resolveSectionTarget(section);
        const content = normalizeWhitespace(section.content);
        if (!content) {
            return;
        }

        if (target === "allowed_tools") {
            parsed.allowed_tools = dedupe([...parsed.allowed_tools, ...(section.listItems.length > 0 ? section.listItems : splitInlineList(content))]);
            return;
        }
        if (target === "capabilities") {
            parsed.capabilities = dedupe([...parsed.capabilities, ...(section.listItems.length > 0 ? section.listItems : splitInlineList(content))]);
            return;
        }
        if (target === "tags") {
            parsed.tags = dedupe([...parsed.tags, ...(section.listItems.length > 0 ? section.listItems : splitInlineList(content))]);
            return;
        }
        if (target === "description") {
            parsed.description = appendText(parsed.description, content);
            return;
        }
        if (target === "rules_markdown") {
            parsed.rules_markdown = appendText(parsed.rules_markdown, content);
            return;
        }

        unmatchedSections.push({
            id: section.id,
            heading: section.heading,
            content,
            reason: "No deterministic field mapping for heading.",
        });
    });

    if (!parsed.slug?.trim()) {
        const slugSource = parsed.name || options.fileName?.replace(/\.(md|markdown)$/i, "");
        parsed.slug = slugSource ? slugify(slugSource) : undefined;
        if (parsed.slug) {
            parseIssues.push({
                id: "missing-slug-inferred",
                field: "slug",
                severity: "info",
                message: "Slug was inferred from the skill name or filename.",
                sourceExcerpt: slugSource,
                candidateTargets: ["slug", "ignore"],
            });
        }
    }
    if (!parsed.name?.trim() && parsed.slug?.trim()) {
        parsed.name = titleFromSlug(parsed.slug);
        parseIssues.push({
            id: "missing-name-inferred",
            field: "name",
            severity: "warning",
            message: "Name was missing. Review the inferred skill name before continuing.",
            sourceExcerpt: parsed.slug,
            candidateTargets: ["name", "slug", "ignore"],
        });
    }

    parsed.allowed_tools = dedupe(parsed.allowed_tools.map((tool) => canonicalizeToolName(tool, options.toolCatalog ?? []) ?? tool));

    return rebuildDraft(parsed, unmatchedSections, options.markdown, options.fileName, parseIssues, options.toolCatalog ?? []);
}

export function updateSkillImportDraftField(
    draft: SkillTemplateImportDraft,
    field: keyof SkillTemplateImportParsed,
    value: string | string[],
    toolCatalog: string[] = [],
) {
    const parsed: SkillTemplateImportParsed = {
        ...draft.parsed,
        [field]: Array.isArray(value) ? dedupe(value) : value,
    };
    return rebuildDraft(parsed, draft.unmatched_sections, draft.raw_markdown, draft.source_filename, [], toolCatalog);
}

export function applySkillUnmatchedSectionMapping(
    draft: SkillTemplateImportDraft,
    sectionId: string,
    target: SkillImportTargetField,
    toolCatalog: string[] = [],
) {
    const section = draft.unmatched_sections.find((item) => item.id === sectionId);
    if (!section) {
        return draft;
    }

    const nextUnmatched = draft.unmatched_sections.filter((item) => item.id !== sectionId);
    const nextParsed: SkillTemplateImportParsed = { ...draft.parsed };

    if (target !== "ignore") {
        if (target === "description") {
            nextParsed.description = appendText(nextParsed.description, section.content);
        } else if (target === "rules_markdown") {
            nextParsed.rules_markdown = appendText(nextParsed.rules_markdown, section.content);
        } else if (target === "tags") {
            nextParsed.tags = dedupe([...nextParsed.tags, ...splitInlineList(section.content)]);
        }
    }

    return rebuildDraft(nextParsed, nextUnmatched, draft.raw_markdown, draft.source_filename, [], toolCatalog);
}

export function getSkillUnknownTools(draft: SkillTemplateImportDraft, toolCatalog: string[] = []) {
    if (toolCatalog.length === 0) {
        return [];
    }
    return draft.parsed.allowed_tools.filter((tool) => !canonicalizeToolName(tool, toolCatalog));
}

export function mapSkillUnknownTool(
    draft: SkillTemplateImportDraft,
    sourceTool: string,
    resolvedTool: string,
    toolCatalog: string[] = [],
) {
    const parsed: SkillTemplateImportParsed = {
        ...draft.parsed,
        allowed_tools: dedupe(draft.parsed.allowed_tools.map((tool) => (tool === sourceTool ? resolvedTool : tool))),
    };
    return rebuildDraft(parsed, draft.unmatched_sections, draft.raw_markdown, draft.source_filename, [], toolCatalog);
}

export function getSkillImportConfidenceLabel(confidence: number) {
    if (confidence >= 0.8) return "high";
    if (confidence >= 0.55) return "medium";
    return "low";
}

export function draftToSkillTemplateFormState(draft: SkillTemplateImportDraft): SkillTemplateFormStateLike {
    return {
        name: draft.parsed.name ?? "",
        slug: draft.parsed.slug ?? "",
        description: draft.parsed.description ?? "",
        capabilities: draft.parsed.capabilities,
        allowed_tools: draft.parsed.allowed_tools,
        tags: draft.parsed.tags,
        rules_markdown: draft.parsed.rules_markdown ?? "",
    };
}

export function createSkillImportedSourceSummary(draft: SkillTemplateImportDraft) {
    const warningCount = draft.issues.filter((issue) => issue.severity === "warning").length;
    return {
        fileName: draft.source_filename ?? "Markdown file",
        rawMarkdown: draft.raw_markdown,
        bannerText: warningCount > 0
            ? `Imported from Markdown — ${warningCount} warning${warningCount === 1 ? "" : "s"}`
            : "Imported from Markdown",
        warningCount,
    };
}
