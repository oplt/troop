import { describe, expect, it } from "vitest";

import { buildAgentTemplatePayloadFromForm } from "../agentTemplates/formState";
import {
    applyUnmatchedSectionMapping,
    buildAgentTemplateImportDraftFromResolvedValues,
    draftToAgentTemplateFormState,
    getUnknownTools,
    parseAgentTemplateMarkdown,
} from "./parser";

describe("agent template markdown import", () => {
    it("parses valid frontmatter and clean markdown into a normalized draft", () => {
        const draft = parseAgentTemplateMarkdown({
            fileName: "backend-builder.md",
            toolCatalog: ["repo_search", "run_tests", "open_pr"],
            markdown: `---
name: Backend Builder
slug: backend-builder
role: specialist
description: Ships backend changes safely.
tools:
  - repo_search
  - run_tests
model: gpt-5-codex
tags: [backend, api]
---

# Backend Builder

## Mission
Own API and data-layer implementation.

## System Prompt
Think through tradeoffs, write tests, and escalate schema risk.

## Capabilities
- api
- database

## Output Contract
Return a patch summary and test evidence.
`,
        });

        expect(draft.parsed.name).toBe("Backend Builder");
        expect(draft.parsed.slug).toBe("backend-builder");
        expect(draft.parsed.allowed_tools).toEqual(["repo_search", "run_tests"]);
        expect(draft.parsed.capabilities).toEqual(expect.arrayContaining(["api", "database"]));
        expect(draft.parsed.mission_markdown).toContain("Own API");
        expect(draft.parsed.output_contract_markdown).toContain("patch summary");
        expect(draft.issues.filter((issue) => issue.severity === "error")).toHaveLength(0);
    });

    it("surfaces malformed frontmatter but still parses the body", () => {
        const draft = parseAgentTemplateMarkdown({
            fileName: "reviewer.md",
            markdown: `---
name: Reviewer

# Reviewer

## Mission
Catch regressions before release.

## System Prompt
Demand evidence for approval.
`,
        });

        expect(draft.parsed.name).toBe("Reviewer");
        expect(draft.parsed.mission_markdown).toContain("Catch regressions");
        expect(draft.issues.some((issue) => issue.id === "frontmatter-malformed")).toBe(true);
    });

    it("infers a slug and display name when name is missing", () => {
        const draft = parseAgentTemplateMarkdown({
            fileName: "incident-triage.md",
            markdown: `## Mission
Triage incidents fast.

## System Prompt
Escalate customer-impacting incidents immediately.
`,
        });

        expect(draft.parsed.slug).toBe("incident-triage");
        expect(draft.parsed.name).toBe("Incident Triage");
        expect(draft.issues.some((issue) => issue.id === "missing-name-inferred")).toBe(true);
    });

    it("flags unknown tools against the current catalog", () => {
        const draft = parseAgentTemplateMarkdown({
            fileName: "planner.md",
            toolCatalog: ["repo_search", "open_pr"],
            markdown: `# Planner

## Tools
- repo_search
- shell_exec
`,
        });

        expect(getUnknownTools(draft, ["repo_search", "open_pr"])).toEqual(["shell_exec"]);
        expect(draft.issues.some((issue) => issue.id === "unknown-tool-shell-exec")).toBe(true);
    });

    it("maps unmatched sections into a target field instead of dropping them", () => {
        const draft = parseAgentTemplateMarkdown({
            fileName: "builder.md",
            markdown: `# Builder

## Weird Notes
Always attach migration notes.
`,
        });

        expect(draft.unmatched_sections).toHaveLength(1);

        const mapped = applyUnmatchedSectionMapping(draft, draft.unmatched_sections[0].id, "rules_markdown");
        expect(mapped.unmatched_sections).toHaveLength(0);
        expect(mapped.parsed.rules_markdown).toContain("migration notes");
    });

    it("pushes resolved import values into final drawer form state", () => {
        const draft = buildAgentTemplateImportDraftFromResolvedValues({
            raw_markdown: "# Backend Builder",
            name: "Backend Builder",
            slug: "backend-builder",
            role: "specialist",
            description: "Build backend changes.",
            mission_markdown: "Own API and persistence work.",
            rules_markdown: "Never ship without tests.",
            output_contract_markdown: "Return patch + evidence.",
            allowed_tools: ["repo_search", "run_tests"],
            capabilities: ["api", "database"],
            tags: ["backend"],
            task_filters: ["api work"],
        });

        const form = draftToAgentTemplateFormState(draft);

        expect(form.name).toBe("Backend Builder");
        expect(form.mission_markdown).toContain("Own API");
        expect(form.rules_markdown).toContain("Never ship");
        expect(form.output_contract_markdown).toContain("patch + evidence");
        expect(form.allowed_tools).toBe("repo_search, run_tests");
    });

    it("preserves markdown fields through the save payload builder", () => {
        const payload = buildAgentTemplatePayloadFromForm(
            {
                name: "Backend Builder",
                slug: "backend-builder",
                description: "Build backend changes.",
                role: "specialist",
                system_prompt: "Work carefully.",
                mission_markdown: "Own API and persistence work.",
                rules_markdown: "Never ship without tests.",
                output_contract_markdown: "Return patch + evidence.",
                parent_template_slug: "",
                capabilities: "api, database",
                allowed_tools: "repo_search, run_tests",
                skills: [],
                tags: "backend",
                task_filters: "api work",
                model: "gpt-5-codex",
                fallback_model: "",
                escalation_path: "lead-manager",
                permission: "read-only",
                memory_scope: "project-only",
                output_format: "json",
                token_budget: "8000",
                time_budget_seconds: "300",
                retry_budget: "1",
            },
            null,
            [],
        );

        expect(payload.mission_markdown).toBe("Own API and persistence work.");
        expect(payload.rules_markdown).toBe("Never ship without tests.");
        expect(payload.output_contract_markdown).toBe("Return patch + evidence.");
    });
});
