export type NavGroupId = "work" | "agents" | "automate" | "insight" | "org" | "admin";

export type NavGroupDef = {
    id: NavGroupId;
    title: string;
};

/** Top-level nav sections. Default open: Work only. */
export const NAV_GROUPS: NavGroupDef[] = [
    { id: "work", title: "Work" },
    { id: "agents", title: "Agents" },
    { id: "automate", title: "Automate" },
    { id: "insight", title: "Insight" },
    { id: "org", title: "Org" },
    { id: "admin", title: "Admin" },
];

export const NAV_GROUPS_STORAGE_KEY = "troop.navGroupsExpanded";
export const DEFAULT_EXPANDED_GROUPS: NavGroupId[] = ["work"];

export function readExpandedNavGroups(): NavGroupId[] {
    try {
        const raw = localStorage.getItem(NAV_GROUPS_STORAGE_KEY);
        if (!raw) {
            return [...DEFAULT_EXPANDED_GROUPS];
        }
        const parsed = JSON.parse(raw) as unknown;
        if (!Array.isArray(parsed)) {
            return [...DEFAULT_EXPANDED_GROUPS];
        }
        const allowed = new Set(NAV_GROUPS.map((g) => g.id));
        const ids = parsed.filter((id): id is NavGroupId => typeof id === "string" && allowed.has(id as NavGroupId));
        return ids.length > 0 ? ids : [...DEFAULT_EXPANDED_GROUPS];
    } catch {
        return [...DEFAULT_EXPANDED_GROUPS];
    }
}

export function writeExpandedNavGroups(ids: NavGroupId[]) {
    try {
        localStorage.setItem(NAV_GROUPS_STORAGE_KEY, JSON.stringify(ids));
    } catch {
        // Ignore persistence failures (private browsing, quota).
    }
}

export function pathMatchesNavItem(currentPath: string, itemPath: string) {
    if (itemPath === "/dashboard") {
        return currentPath === itemPath;
    }
    return currentPath === itemPath || currentPath.startsWith(`${itemPath}/`);
}
