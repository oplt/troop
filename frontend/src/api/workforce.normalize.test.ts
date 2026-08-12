import { describe, expect, it } from "vitest";
import {
    normalizeSkill,
    normalizeSkillDraft,
    normalizeSkillUsage,
    normalizeSkillVersion,
} from "../api/workforce";

describe("workforce DTO normalizers", () => {
    it("flattens skill current_version fields for SkillsPage", () => {
        const skill = normalizeSkill({
            id: "s1",
            owner_id: "u1",
            name: "Research",
            slug: "research",
            scope: "organization",
            status: "active",
            created_at: "2026-01-01",
            updated_at: "2026-01-01",
            current_version: {
                purpose: "Do research",
                capabilities_json: ["web_research"],
                required_tools_json: ["web_search"],
                instructions_markdown: "Search carefully",
                version_number: 2,
                risk_level: "low",
            },
        });
        expect(skill.purpose).toBe("Do research");
        expect(skill.capabilities).toEqual(["web_research"]);
        expect(skill.tools).toEqual(["web_search"]);
        expect(skill.instructions).toContain("Search");
        expect(skill.version).toBe(2);
    });

    it("normalizes skill draft backend *_json fields", () => {
        const draft = normalizeSkillDraft({
            id: "d1",
            owner_id: "u1",
            name: "Draft",
            slug: "draft",
            scope: "project",
            purpose: "p",
            when_to_use: "w",
            instructions_markdown: "do the thing carefully and completely",
            capabilities_json: ["a"],
            required_tools_json: ["web_search"],
            validation_errors_json: [],
            warnings_json: ["warn"],
            created_at: "2026-01-01",
            updated_at: "2026-01-01",
        });
        expect(draft.capabilities).toEqual(["a"]);
        expect(draft.tools).toEqual(["web_search"]);
        expect(draft.instructions).toContain("do the thing");
        expect(draft.validation_warnings).toEqual(["warn"]);
        expect(draft.is_valid).toBe(true);
    });

    it("normalizes skill version backend *_json fields", () => {
        const version = normalizeSkillVersion({
            id: "v1",
            skill_id: "s1",
            version_number: 3,
            purpose: "Research the web",
            when_to_use: "When gathering sources",
            instructions_markdown: "Search carefully",
            input_schema_json: { query: { type: "string" } },
            output_schema_json: { results: { type: "array" } },
            capabilities_json: ["web_research"],
            required_tools_json: ["web_search"],
            knowledge_requirements_json: ["business_context"],
            constraints_markdown: "Cite sources",
            risk_level: "medium",
            approval_policy_json: { mode: "semi" },
            examples_json: ["Example A"],
            evaluation_criteria_json: ["citation_quality"],
            source_type: "manual",
            is_published: true,
            generated_by_model: "gpt-4",
            created_at: "2026-01-01",
        });
        expect(version.capabilities).toEqual(["web_research"]);
        expect(version.tools).toEqual(["web_search"]);
        expect(version.knowledge).toEqual(["business_context"]);
        expect(version.instructions).toContain("Search");
        expect(version.inputs?.query).toBeDefined();
        expect(version.is_published).toBe(true);
        expect(version.version_number).toBe(3);
    });

    it("normalizes skill usage run stats and legacy aliases", () => {
        const usage = normalizeSkillUsage({
            skill_id: "s1",
            skill_version_id: "v1",
            run_count: 10,
            success_count: 8,
            human_accept_count: 7,
            success_rate: 0.8,
            avg_latency_ms: 1200,
            avg_cost_usd: 0.05,
            retry_rate: 0.1,
            last_used_at: "2026-01-02T00:00:00Z",
            promotion_recommendation: "Ready for organization",
        });
        expect(usage.run_count).toBe(10);
        expect(usage.task_count).toBe(10);
        expect(usage.success_rate).toBe(0.8);
        expect(usage.promotion_recommendation).toContain("organization");
    });

    it("derives success_rate from run stats when omitted", () => {
        const usage = normalizeSkillUsage({
            skill_id: "s1",
            run_count: 4,
            success_count: 3,
        });
        expect(usage.success_rate).toBeCloseTo(0.75);
        expect(usage.avg_latency_ms).toBeNull();
    });
});
