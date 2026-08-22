import { describe, expect, it, beforeEach, afterEach, vi } from "vitest";
import {
    DEFAULT_EXPANDED_GROUPS,
    NAV_GROUPS,
    NAV_GROUPS_STORAGE_KEY,
    NAV_ITEM_DEFS,
    navItemPathname,
    pathMatchesNavItem,
    readExpandedNavGroups,
    writeExpandedNavGroups,
} from "./navConfig";
import {
    deriveNavPersona,
    partitionNavItemsForPersona,
    readNavPersonaPreference,
    writeNavPersonaPreference,
    NAV_PERSONA_STORAGE_KEY,
} from "./navPersona";

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
        writeExpandedNavGroups(["work", "build"]);
        expect(localStorage.getItem(NAV_GROUPS_STORAGE_KEY)).toBe(JSON.stringify(["work", "build"]));
        expect(readExpandedNavGroups()).toEqual(["work", "build"]);
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

    it("strips query strings when matching admin settings deep links", () => {
        expect(pathMatchesNavItem("/admin/settings", "/admin/settings?tab=users")).toBe(true);
        expect(navItemPathname("/admin/settings?tab=users")).toBe("/admin/settings");
    });

    it("defines canonical IA paths, observe group, and persona metadata", () => {
        expect(NAV_GROUPS.map((g) => g.id)).toEqual(["work", "build", "observe", "org", "admin", "advanced"]);
        const byId = Object.fromEntries(NAV_ITEM_DEFS.map((item) => [item.id, item]));
        expect(byId.approvals.path).toBe("/approvals");
        expect(byId.activity.path).toBe("/activity");
        expect(byId.audit.path).toBe("/audit");
        expect(byId.portfolio.path).toBe("/portfolio");
        expect(byId.hierarchy.path).toBe("/hierarchy");
        expect(byId.execution.label).toBe("Runs");
        expect(byId.approvals.primaryPersonas).toContain("operator");
        expect(byId["ai-studio"].requiresAiModule).toBe(true);
        expect(byId.settings.adminOnly).toBe(true);
    });
});

describe("navPersona", () => {
    beforeEach(() => {
        localStorage.clear();
    });

    afterEach(() => {
        localStorage.clear();
    });

    it("derives persona from workspace role and platform admin", () => {
        expect(deriveNavPersona({ isAdmin: true })).toBe("admin");
        expect(deriveNavPersona({ isAdmin: false, workspaceRole: "owner" })).toBe("admin");
        expect(deriveNavPersona({ isAdmin: false, workspaceRole: "builder" })).toBe("builder");
        expect(deriveNavPersona({ isAdmin: false, workspaceRole: "operator" })).toBe("operator");
        expect(deriveNavPersona({ isAdmin: false, workspaceRole: "approver" })).toBe("operator");
    });

    it("persists persona preference", () => {
        writeNavPersonaPreference("builder");
        expect(localStorage.getItem(NAV_PERSONA_STORAGE_KEY)).toBe("builder");
        expect(readNavPersonaPreference()).toBe("builder");
    });

    it("partitions operator primary nav and advanced overflow", () => {
        const accessible = NAV_ITEM_DEFS.filter((item) => !item.adminOnly && !item.requiresAiModule);
        const { primary, advanced } = partitionNavItemsForPersona(accessible, "operator");
        expect(primary.map((item) => item.id)).toEqual(["dashboard", "my-tasks", "approvals", "workflows"]);
        expect(primary.map((item) => item.id)).not.toContain("agents");
        expect(advanced.map((item) => item.id)).toEqual(expect.arrayContaining(["agents", "projects", "execution"]));
    });

    it("keeps the builder sidebar focused on building", () => {
        const accessible = NAV_ITEM_DEFS.filter((item) => !item.adminOnly && !item.requiresAiModule);
        const { primary } = partitionNavItemsForPersona(accessible, "builder");
        expect(primary.map((item) => item.id)).toEqual([
            "dashboard",
            "projects",
            "agents",
            "workflows",
            "integrations",
        ]);
    });

    it("keeps the admin sidebar at five decision-level destinations", () => {
        const { primary } = partitionNavItemsForPersona(NAV_ITEM_DEFS, "admin");
        expect(primary.map((item) => item.id)).toEqual([
            "dashboard",
            "projects",
            "activity",
            "companies",
            "settings",
        ]);
        expect(primary.map((item) => item.personaLabels?.admin ?? item.label)).toEqual([
            "Home",
            "Work",
            "Observe",
            "Organization",
            "Settings",
        ]);
    });
});
