import { useEffect, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useLocation } from "react-router-dom";

import { getOrchestrationProject } from "../api/orchestration";
import { queryKeys, defaultQueryStaleTimeMs } from "../config/queryKeys";
import { recordRecentProject } from "../components/layout/recentProjects";
import {
    pathMatchesNavItem,
    navItemPathname,
    type NavItemDef,
} from "../components/layout/navConfig";

export type BreadcrumbItem = {
    label: string;
    path: string;
};

export type AppNavItem = {
    label: string;
    path: string;
    adminOnly?: boolean;
    group: NavItemDef["group"];
};

function formatPathSegment(segment: string) {
    if (!segment) return "";
    const decoded = decodeURIComponent(segment);
    const looksLikeId = /^[0-9a-f]{8,}$/i.test(decoded) || decoded.length > 24;
    if (looksLikeId) {
        return "Details";
    }
    return decoded
        .replace(/[-_]+/g, " ")
        .replace(/\b\w/g, (char) => char.toUpperCase());
}

export function buildBreadcrumbs(
    pathname: string,
    navItems: AppNavItem[],
    resolveSegmentLabel?: (segment: string, index: number, segments: string[]) => string | undefined,
): BreadcrumbItem[] {
    const exact = navItems.find((item) => navItemPathname(item.path) === pathname);
    if (exact) {
        return [{ label: exact.label, path: exact.path }];
    }
    const root = [...navItems]
        .sort((left, right) => navItemPathname(right.path).length - navItemPathname(left.path).length)
        .find((item) => pathname.startsWith(navItemPathname(item.path)) || pathname === navItemPathname(item.path));
    if (!root) {
        return [{ label: "Workspace", path: pathname }];
    }
    const breadcrumbs: BreadcrumbItem[] = [{ label: root.label, path: root.path }];
    const rootSegments = root.path.split("/").filter(Boolean);
    const pathSegments = pathname.split("/").filter(Boolean);
    for (let index = rootSegments.length; index < pathSegments.length; index += 1) {
        const segment = pathSegments[index];
        const nextPath = `/${pathSegments.slice(0, index + 1).join("/")}`;
        breadcrumbs.push({
            label: resolveSegmentLabel?.(segment, index, pathSegments) ?? formatPathSegment(segment),
            path: nextPath,
        });
    }
    return breadcrumbs;
}

export function useAppBreadcrumbs(visibleNavItems: AppNavItem[]) {
    const location = useLocation();

    const projectIdFromPath = useMemo(() => {
        const match = location.pathname.match(/^\/(?:projects|agent-projects)\/([^/]+)/);
        return match?.[1] ?? null;
    }, [location.pathname]);

    const { data: breadcrumbProject } = useQuery({
        queryKey: queryKeys.orchestration.project(projectIdFromPath ?? ""),
        queryFn: () => getOrchestrationProject(projectIdFromPath!),
        enabled: Boolean(projectIdFromPath),
        staleTime: defaultQueryStaleTimeMs,
    });

    useEffect(() => {
        if (breadcrumbProject?.id && breadcrumbProject.name) {
            recordRecentProject({ id: breadcrumbProject.id, name: breadcrumbProject.name });
        }
    }, [breadcrumbProject?.id, breadcrumbProject?.name]);

    const breadcrumbs = useMemo(
        () =>
            buildBreadcrumbs(location.pathname, visibleNavItems, (segment, index, segments) => {
                if (index > 0 && (segments[index - 1] === "agent-projects" || segments[index - 1] === "projects")) {
                    if (segment === projectIdFromPath && breadcrumbProject?.name) {
                        return breadcrumbProject.name;
                    }
                }
                if (segment === "memory") return "Memory";
                if (segment === "benchmark") return "Benchmark";
                return undefined;
            }),
        [location.pathname, visibleNavItems, breadcrumbProject, projectIdFromPath],
    );

    const currentItem = visibleNavItems.find((item) => pathMatchesNavItem(location.pathname, item.path));
    const canGoBack = breadcrumbs.length > 1 || location.pathname !== (currentItem?.path ?? "/dashboard");

    return {
        breadcrumbs,
        canGoBack,
        currentItem,
    };
}
