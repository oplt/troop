export type NavGroupId = "work" | "agents" | "automate" | "insight" | "org" | "admin";

export type NavGroupDef = {
    id: NavGroupId;
    title: string;
};

/** Icon keys resolved in AppLayout (keeps navConfig free of React nodes). */
export type NavIconId =
    | "dashboard"
    | "projects"
    | "myTasks"
    | "approvals"
    | "agents"
    | "skills"
    | "marketplace"
    | "hierarchy"
    | "workflows"
    | "workflowTemplates"
    | "integrations"
    | "portfolio"
    | "cost"
    | "execution"
    | "brainstorms"
    | "aiStudio"
    | "departments"
    | "companies"
    | "modelSettings"
    | "settings";

export type NavItemDef = {
    id: string;
    label: string;
    path: string;
    group: NavGroupId;
    icon: NavIconId;
    adminOnly?: boolean;
    /** When true, only include if the AI module pack is enabled. */
    requiresAiModule?: boolean;
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

/**
 * Single IA source for drawer + command palette pages.
 * Canonical paths: /approvals, /portfolio, /hierarchy (legacy URLs redirect).
 */
export const NAV_ITEM_DEFS: NavItemDef[] = [
    { id: "dashboard", label: "Dashboard", path: "/dashboard", group: "work", icon: "dashboard" },
    { id: "projects", label: "Projects", path: "/projects", group: "work", icon: "projects" },
    { id: "my-tasks", label: "My tasks", path: "/my-tasks", group: "work", icon: "myTasks" },
    { id: "approvals", label: "Approvals", path: "/approvals", group: "work", icon: "approvals" },
    { id: "agents", label: "Agents", path: "/agents", group: "agents", icon: "agents" },
    { id: "skills", label: "Skills", path: "/skills", group: "agents", icon: "skills" },
    { id: "marketplace", label: "Marketplace", path: "/marketplace", group: "agents", icon: "marketplace" },
    { id: "hierarchy", label: "Hierarchy", path: "/hierarchy", group: "agents", icon: "hierarchy" },
    { id: "workflows", label: "Workflows", path: "/workforce-workflows", group: "automate", icon: "workflows" },
    {
        id: "workflow-templates",
        label: "Workflow templates",
        path: "/workflow-templates",
        group: "automate",
        icon: "workflowTemplates",
    },
    { id: "integrations", label: "Integrations", path: "/integrations", group: "automate", icon: "integrations" },
    { id: "portfolio", label: "Portfolio", path: "/portfolio", group: "insight", icon: "portfolio" },
    { id: "cost", label: "Cost & usage", path: "/analytics/cost", group: "insight", icon: "cost" },
    {
        id: "execution",
        label: "Execution insights",
        path: "/analytics/execution",
        group: "insight",
        icon: "execution",
    },
    { id: "brainstorms", label: "Brainstorms", path: "/brainstorms", group: "insight", icon: "brainstorms" },
    {
        id: "ai-studio",
        label: "AI Studio",
        path: "/ai",
        group: "insight",
        icon: "aiStudio",
        requiresAiModule: true,
    },
    { id: "departments", label: "Departments", path: "/departments", group: "org", icon: "departments" },
    { id: "companies", label: "Companies", path: "/companies", group: "org", icon: "companies" },
    { id: "model-settings", label: "Model settings", path: "/model-settings", group: "org", icon: "modelSettings" },
    {
        id: "settings",
        label: "Settings",
        path: "/admin/settings",
        group: "admin",
        icon: "settings",
        adminOnly: true,
    },
];

export const NAV_GROUPS_STORAGE_KEY = "troop.navGroupsExpanded";

/** Fresh sessions: only Work expanded; Insight/Org stay collapsed until opened or active. */
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

/** Product label for a path segment when it is not a UUID-like id. */
export function navLabelForPath(path: string): string | undefined {
    const exact = NAV_ITEM_DEFS.find((item) => item.path === path);
    return exact?.label;
}
