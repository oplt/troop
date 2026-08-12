import { describe, expect, it } from "vitest";
import { normalizeSkill, normalizeSkillDraft } from "../api/workforce";

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
});
