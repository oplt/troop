const RECENT_PROJECTS_KEY = "troop.recentProjects";
const MAX_RECENT = 8;

export type RecentProject = {
    id: string;
    name: string;
    visitedAt: number;
};

export function readRecentProjects(): RecentProject[] {
    try {
        const raw = localStorage.getItem(RECENT_PROJECTS_KEY);
        if (!raw) {
            return [];
        }
        const parsed = JSON.parse(raw) as unknown;
        if (!Array.isArray(parsed)) {
            return [];
        }
        return parsed
            .filter(
                (item): item is RecentProject =>
                    !!item &&
                    typeof item === "object" &&
                    typeof (item as RecentProject).id === "string" &&
                    typeof (item as RecentProject).name === "string" &&
                    typeof (item as RecentProject).visitedAt === "number",
            )
            .sort((left, right) => right.visitedAt - left.visitedAt)
            .slice(0, MAX_RECENT);
    } catch {
        return [];
    }
}

export function recordRecentProject(project: { id: string; name: string }) {
    if (!project.id || !project.name) {
        return;
    }
    try {
        const next: RecentProject[] = [
            { id: project.id, name: project.name, visitedAt: Date.now() },
            ...readRecentProjects().filter((item) => item.id !== project.id),
        ].slice(0, MAX_RECENT);
        localStorage.setItem(RECENT_PROJECTS_KEY, JSON.stringify(next));
    } catch {
        // Ignore persistence failures.
    }
}

export function commandShortcutLabel(): string {
    if (typeof navigator === "undefined") {
        return "Ctrl+K";
    }
    const platform = navigator.platform ?? "";
    const uaData = (navigator as Navigator & { userAgentData?: { platform?: string } }).userAgentData;
    const isMac = /mac/i.test(uaData?.platform ?? platform);
    return isMac ? "⌘K" : "Ctrl+K";
}
