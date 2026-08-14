export type HierarchyBuilderTab = "library" | "hierarchy";

export const HIERARCHY_CANVAS_PATHS = new Set([
    "/agent-hierarchy",
    "/hierarchy-builder",
    "/hierarchy",
]);

/** Map router pathname to the default builder tab. */
export function resolveHierarchyBuilderTab(pathname: string): HierarchyBuilderTab {
    return HIERARCHY_CANVAS_PATHS.has(pathname) ? "hierarchy" : "library";
}

/** Manual tab selection overrides route-derived defaults until cleared. */
export function resolveHierarchyActiveTab(
    routeTab: HierarchyBuilderTab,
    manualTab: HierarchyBuilderTab | null,
): HierarchyBuilderTab {
    return manualTab ?? routeTab;
}
