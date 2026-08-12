import { describe, expect, it } from "vitest";
import { buildSkillForm, buildTeamTemplateForm, uniqueStrings } from "./templateState";

describe("hierarchy template state", () => {
    it("creates safe empty drafts without sharing mutable arrays", () => {
        const first = buildSkillForm();
        const second = buildSkillForm();
        first.capabilities.push("planning");
        expect(second.capabilities).toEqual([]);
        expect(buildTeamTemplateForm().visibility).toBe("private");
    });

    it("deduplicates and trims derived template metadata", () => {
        expect(uniqueStrings([" manager ", "manager", "", "reviewer"])).toEqual(["manager", "reviewer"]);
    });
});
