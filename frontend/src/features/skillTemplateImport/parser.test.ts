import { describe, expect, it } from "vitest";

import {
    applySkillUnmatchedSectionMapping,
    draftToSkillTemplateFormState,
    getSkillUnknownTools,
    parseSkillTemplateMarkdown,
} from "./parser";

describe("skill template markdown import", () => {
    it("parses clean markdown into a normalized skill draft", () => {
        const draft = parseSkillTemplateMarkdown({
            fileName: "pr-review.md",
            toolCatalog: ["repo_search", "open_pr"],
            markdown: `---
name: PR Review Discipline
slug: pr-review-discipline
description: Adds a disciplined review loop.
---

# PR Review Discipline

## Capabilities
- code-review
- qa

## Tools
- repo_search

## Rules
Demand evidence before approval.
`,
        });

        expect(draft.parsed.name).toBe("PR Review Discipline");
        expect(draft.parsed.allowed_tools).toEqual(["repo_search"]);
        expect(draft.parsed.capabilities).toEqual(expect.arrayContaining(["code-review", "qa"]));
        expect(draft.parsed.rules_markdown).toContain("Demand evidence");
    });

    it("keeps unknown tools visible as issues", () => {
        const draft = parseSkillTemplateMarkdown({
            fileName: "ops.md",
            toolCatalog: ["repo_search"],
            markdown: `# Ops

## Tools
- repo_search
- shell_exec
`,
        });

        expect(getSkillUnknownTools(draft, ["repo_search"])).toEqual(["shell_exec"]);
        expect(draft.issues.some((issue) => issue.id === "unknown-tool-shell-exec")).toBe(true);
    });

    it("keeps unmatched sections and lets them map into rules", () => {
        const draft = parseSkillTemplateMarkdown({
            fileName: "triage.md",
            markdown: `# Triage

## Weird Notes
Escalate customer-facing outages immediately.
`,
        });

        expect(draft.unmatched_sections).toHaveLength(1);
        const mapped = applySkillUnmatchedSectionMapping(draft, draft.unmatched_sections[0].id, "rules_markdown");
        expect(mapped.unmatched_sections).toHaveLength(0);
        expect(mapped.parsed.rules_markdown).toContain("customer-facing outages");
    });

    it("pushes resolved draft values into the final skill drawer state", () => {
        const draft = parseSkillTemplateMarkdown({
            fileName: "qa-gate.md",
            markdown: `# QA Gate

## Description
Adds QA validation discipline.

## Capabilities
- qa

## Rules
Block approval without test evidence.
`,
        });

        const form = draftToSkillTemplateFormState(draft);
        expect(form.name).toBe("QA Gate");
        expect(form.description).toContain("QA validation");
        expect(form.capabilities).toEqual(["qa"]);
        expect(form.rules_markdown).toContain("test evidence");
    });
});
