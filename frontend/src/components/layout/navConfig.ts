export type NavGroupId = "work" | "build" | "observe" | "org" | "admin" | "advanced";

export type NavPersona = "operator" | "builder" | "admin";

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
    | "activity"
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
    | "people"
    | "modelSettings"
    | "policies"
    | "audit"
    | "settings";

export type NavItemDef = {
    id: string;
    label: string;
    path: string;
    group: NavGroupId;
    icon: NavIconId;
    /** Personas that show this item in primary navigation (others land under Advanced). */
    primaryPersonas: NavPersona[];
    adminOnly?: boolean;
    /** When true, only include if the AI module pack is enabled. */
    requiresAiModule?: boolean;
};

/** Top-level nav sections. Default open: Work only. */
export const NAV_GROUPS: NavGroupDef[] = [
    { id: "work", title: "Work" },
    { id: "build", title: "Build" },
    { id: "observe", title: "Observe" },
    { id: "org", title: "Organization" },
    { id: "admin", title: "Admin" },
    { id: "advanced", title: "Advanced" },
];

const ALL_PERSONAS: NavPersona[] = ["operator", "builder", "admin"];

/**
 * Single IA source for drawer + command palette pages.
 * Canonical paths: /approvals, /portfolio, /hierarchy (legacy URLs redirect).
 */
export const NAV_ITEM_DEFS: NavItemDef[] = [
    {
        id: "dashboard",
        label: "Dashboard",
        path: "/dashboard",
        group: "work",
        icon: "dashboard",
        primaryPersonas: ALL_PERSONAS,
    },
    {
        id: "projects",
        label: "Projects",
        path: "/projects",
        group: "work",
        icon: "projects",
        primaryPersonas: ["builder", "admin"],
    },
    {
        id: "my-tasks",
        label: "My tasks",
        path: "/my-tasks",
        group: "work",
        icon: "myTasks",
        primaryPersonas: ["operator"],
    },
    {
        id: "approvals",
        label: "Approvals",
        path: "/approvals",
        group: "work",
        icon: "approvals",
        primaryPersonas: ["operator", "admin"],
    },
    {
        id: "activity",
        label: "Activity",
        path: "/activity",
        group: "work",
        icon: "activity",
        primaryPersonas: ["operator", "admin"],
    },
    {
        id: "agents",
        label: "Agents",
        path: "/agents",
        group: "build",
        icon: "agents",
        primaryPersonas: ["builder"],
    },
    {
        id: "skills",
        label: "Skills",
        path: "/skills",
        group: "build",
        icon: "skills",
        primaryPersonas: ["builder"],
    },
    {
        id: "marketplace",
        label: "Marketplace",
        path: "/marketplace",
        group: "build",
        icon: "marketplace",
        primaryPersonas: [],
    },
    {
        id: "hierarchy",
        label: "Hierarchy",
        path: "/hierarchy",
        group: "build",
        icon: "hierarchy",
        primaryPersonas: [],
    },
    {
        id: "workflows",
        label: "Workflows",
        path: "/workforce-workflows",
        group: "build",
        icon: "workflows",
        primaryPersonas: ["operator", "builder"],
    },
    {
        id: "workflow-templates",
        label: "Templates",
        path: "/workflow-templates",
        group: "build",
        icon: "workflowTemplates",
        primaryPersonas: ["builder"],
    },
    {
        id: "integrations",
        label: "Integrations",
        path: "/integrations",
        group: "build",
        icon: "integrations",
        primaryPersonas: ["builder", "admin"],
    },
    {
        id: "portfolio",
        label: "Portfolio",
        path: "/portfolio",
        group: "observe",
        icon: "portfolio",
        primaryPersonas: ["admin"],
    },
    {
        id: "cost",
        label: "Usage",
        path: "/analytics/cost",
        group: "observe",
        icon: "cost",
        primaryPersonas: ["admin"],
    },
    {
        id: "execution",
        label: "Runs",
        path: "/analytics/execution",
        group: "observe",
        icon: "execution",
        primaryPersonas: ["builder", "admin"],
    },
    {
        id: "brainstorms",
        label: "Brainstorms",
        path: "/brainstorms",
        group: "observe",
        icon: "brainstorms",
        primaryPersonas: [],
    },
    {
        id: "ai-studio",
        label: "AI Studio",
        path: "/ai",
        group: "observe",
        icon: "aiStudio",
        requiresAiModule: true,
        primaryPersonas: [],
    },
    {
        id: "departments",
        label: "Departments",
        path: "/departments",
        group: "org",
        icon: "departments",
        primaryPersonas: ["admin"],
    },
    {
        id: "companies",
        label: "Companies",
        path: "/companies",
        group: "org",
        icon: "companies",
        primaryPersonas: ["admin"],
    },
    {
        id: "people",
        label: "People",
        path: "/admin/settings?tab=users",
        group: "org",
        icon: "people",
        adminOnly: true,
        primaryPersonas: ["admin"],
    },
    {
        id: "model-settings",
        label: "Models",
        path: "/model-settings",
        group: "org",
        icon: "modelSettings",
        primaryPersonas: ["admin"],
    },
    {
        id: "policies",
        label: "Policies",
        path: "/admin/settings?tab=providers",
        group: "org",
        icon: "policies",
        adminOnly: true,
        primaryPersonas: ["admin"],
    },
    {
        id: "audit",
        label: "Audit",
        path: "/audit",
        group: "admin",
        icon: "audit",
        primaryPersonas: ["admin"],
    },
    {
        id: "settings",
        label: "Settings",
        path: "/admin/settings",
        group: "admin",
        icon: "settings",
        adminOnly: true,
        primaryPersonas: ["admin"],
    },
];

export const NAV_GROUPS_STORAGE_KEY = "troop.navGroupsExpanded";

/** Fresh sessions: only Work expanded; Observe/Org stay collapsed until opened or active. */
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

export function navItemPathname(path: string): string {
    return path.split("?")[0] ?? path;
}

export function pathMatchesNavItem(currentPath: string, itemPath: string) {
    const pathname = navItemPathname(itemPath);
    if (pathname === "/dashboard") {
        return currentPath === pathname;
    }
    return currentPath === pathname || currentPath.startsWith(`${pathname}/`);
}

/** Product label for a path segment when it is not a UUID-like id. */
export function navLabelForPath(path: string): string | undefined {
    const exact = NAV_ITEM_DEFS.find((item) => navItemPathname(item.path) === navItemPathname(path));
    return exact?.label;
}
