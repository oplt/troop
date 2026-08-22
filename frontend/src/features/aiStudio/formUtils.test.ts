import { describe, expect, it } from "vitest";

import {
    AI_SECTIONS,
    defaultSectionForWorkspace,
    parseJsonObject,
    parseStudioSection,
    workspaceForSection,
} from "./formUtils";

describe("aiStudio formUtils", () => {
    it("parseStudioSection defaults to prompts and accepts valid tabs", () => {
        expect(parseStudioSection(null)).toBe("prompts");
        expect(parseStudioSection("datasets")).toBe("datasets");
        expect(parseStudioSection("unknown")).toBe("prompts");
        expect(AI_SECTIONS).toContain("playground");
        expect(parseStudioSection("retrieval")).toBe("retrieval");
        expect(workspaceForSection("datasets")).toBe("test");
        expect(workspaceForSection("documents")).toBe("knowledge");
        expect(defaultSectionForWorkspace("build")).toBe("prompts");
    });

    it("parseJsonObject returns fallback for empty input", () => {
        expect(parseJsonObject("", { ok: true })).toEqual({ ok: true });
    });

    it("parseJsonObject parses objects and rejects arrays", () => {
        expect(parseJsonObject('{"name":"demo"}')).toEqual({ name: "demo" });
        expect(() => parseJsonObject("[]")).toThrow("JSON payload must be an object.");
    });
});
