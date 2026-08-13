import { describe, expect, it, beforeEach, afterEach, vi } from "vitest";
import {
    DEFAULT_EXPANDED_GROUPS,
    NAV_GROUPS_STORAGE_KEY,
    pathMatchesNavItem,
    readExpandedNavGroups,
    writeExpandedNavGroups,
} from "./navConfig";

describe("navConfig", () => {
    beforeEach(() => {
        localStorage.clear();
    });

    afterEach(() => {
        localStorage.clear();
        vi.restoreAllMocks();
    });

    it("defaults expanded groups to Work only", () => {
        expect(readExpandedNavGroups()).toEqual(DEFAULT_EXPANDED_GROUPS);
        expect(DEFAULT_EXPANDED_GROUPS).toEqual(["work"]);
    });

    it("persists and reads expanded groups", () => {
        writeExpandedNavGroups(["work", "agents"]);
        expect(localStorage.getItem(NAV_GROUPS_STORAGE_KEY)).toBe(JSON.stringify(["work", "agents"]));
        expect(readExpandedNavGroups()).toEqual(["work", "agents"]);
    });

    it("ignores unknown group ids from storage", () => {
        localStorage.setItem(NAV_GROUPS_STORAGE_KEY, JSON.stringify(["work", "nope", "org"]));
        expect(readExpandedNavGroups()).toEqual(["work", "org"]);
    });

    it("falls back when storage is corrupt", () => {
        localStorage.setItem(NAV_GROUPS_STORAGE_KEY, "{not-json");
        expect(readExpandedNavGroups()).toEqual(DEFAULT_EXPANDED_GROUPS);
    });

    it("matches nav paths without prefix collisions", () => {
        expect(pathMatchesNavItem("/dashboard", "/dashboard")).toBe(true);
        expect(pathMatchesNavItem("/dashboard/extra", "/dashboard")).toBe(false);
        expect(pathMatchesNavItem("/projects", "/projects")).toBe(true);
        expect(pathMatchesNavItem("/projects/abc", "/projects")).toBe(true);
        expect(pathMatchesNavItem("/projects-archive", "/projects")).toBe(false);
    });
});
