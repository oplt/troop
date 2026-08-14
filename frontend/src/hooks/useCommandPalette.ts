import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { listAgents, listApprovals, listRuns } from "../api/orchestration";
import { listSkills } from "../api/workforce";
import { commandShortcutLabel, readRecentProjects } from "../components/layout/recentProjects";
import type { CommandPaletteItem } from "../components/layout/CommandPalette";
import { queryKeys, defaultQueryStaleTimeMs } from "../config/queryKeys";
import { queryPolicies } from "../config/queryPolicies";
import { humanizeKey } from "../utils/formatters";
import type { AppNavItem } from "./useAppBreadcrumbs";

type UseCommandPaletteOptions = {
    authReady: boolean;
    pendingCount: number;
    unreadNotifications: number;
    visibleNavItems: AppNavItem[];
};

const ACTIVE_RUN = new Set(["queued", "in_progress", "running", "waiting", "blocked"]);
const STUCK_RUN = new Set(["failed", "error", "cancelled", "timed_out"]);

export function useCommandPalette({
    authReady,
    pendingCount,
    unreadNotifications,
    visibleNavItems,
}: UseCommandPaletteOptions) {
    const [open, setOpen] = useState(false);
    const shortcutLabel = useMemo(() => commandShortcutLabel(), []);

    const { data: paletteApprovals = [] } = useQuery({
        queryKey: queryKeys.orchestration.approvals,
        queryFn: listApprovals,
        ...queryPolicies.operational,
        enabled: authReady && open,
        retry: false,
    });
    const { data: paletteRuns = [] } = useQuery({
        queryKey: ["orchestration", "runs", "command-palette"],
        queryFn: () => listRuns(),
        ...queryPolicies.operational,
        enabled: authReady && open,
        retry: false,
    });
    const { data: paletteAgents = [] } = useQuery({
        queryKey: queryKeys.orchestration.agents(),
        queryFn: () => listAgents(),
        ...queryPolicies.operational,
        enabled: authReady && open,
        staleTime: defaultQueryStaleTimeMs,
        retry: false,
    });
    const { data: paletteSkills = [] } = useQuery({
        queryKey: ["workforce", "skills", "command-palette"],
        queryFn: listSkills,
        ...queryPolicies.operational,
        enabled: authReady && open,
        staleTime: defaultQueryStaleTimeMs,
        retry: false,
    });

    const items = useMemo<CommandPaletteItem[]>(() => {
        const suggested: CommandPaletteItem[] = [
            {
                id: "suggested-approvals",
                label: pendingCount > 0 ? `Review approvals (${pendingCount})` : "Review approvals",
                path: "/approvals",
                group: "suggested",
                secondary: "Clear the approval queue",
            },
            {
                id: "suggested-tasks",
                label: "My tasks",
                path: "/my-tasks",
                group: "suggested",
                secondary: "Personal work queue",
            },
            {
                id: "suggested-projects",
                label: "Projects",
                path: "/projects",
                group: "suggested",
                secondary: "Browse orchestration projects",
            },
        ];
        if (unreadNotifications > 0) {
            suggested.unshift({
                id: "suggested-notifications",
                label: `Notifications (${unreadNotifications} unread)`,
                path: "/notifications",
                group: "suggested",
                secondary: "Alerts and account events",
            });
        }
        const recent: CommandPaletteItem[] = readRecentProjects().map((project) => ({
            id: `recent-${project.id}`,
            label: project.name,
            path: `/projects/${project.id}`,
            group: "recent",
            secondary: "Recent project",
        }));
        const actions: CommandPaletteItem[] = [
            {
                id: "action-create-project",
                label: "Create project",
                path: "/projects?create=1",
                group: "actions",
                secondary: "Open new project drawer",
            },
            {
                id: "action-approvals",
                label: "Open approvals",
                path: "/approvals",
                group: "actions",
                secondary: pendingCount > 0 ? `${pendingCount} pending` : "Approval queue",
            },
            {
                id: "action-create-task",
                label: "Go to my tasks",
                path: "/my-tasks",
                group: "actions",
                secondary: "Personal work queue",
            },
        ];
        const pages: CommandPaletteItem[] = visibleNavItems.map((item) => ({
            id: `page-${item.path}`,
            label: item.label,
            path: item.path,
            group: "pages",
            secondary: item.label,
        }));
        const approvals: CommandPaletteItem[] = paletteApprovals
            .filter((item) => item.status === "pending")
            .slice(0, 8)
            .map((item) => ({
                id: `approval-${item.id}`,
                label: humanizeKey(item.approval_type || "approval"),
                path: "/approvals",
                group: "approvals" as const,
                secondary: item.reason?.trim() || (item.run_id ? `Run ${item.run_id.slice(0, 8)}…` : "Pending approval"),
            }));
        const runs: CommandPaletteItem[] = paletteRuns
            .filter((run) => ACTIVE_RUN.has(run.status) || STUCK_RUN.has(run.status))
            .slice(0, 8)
            .map((run) => ({
                id: `run-item-${run.id}`,
                label: `${humanizeKey(run.status)} · ${run.id.slice(0, 8)}…`,
                path: `/runs/${run.id}`,
                group: "runs" as const,
                secondary: run.model_name || run.run_mode || "Open run inspector",
            }));
        const agents: CommandPaletteItem[] = paletteAgents.slice(0, 8).map((agent) => ({
            id: `agent-${agent.id}`,
            label: agent.name,
            path: "/agents",
            group: "agents" as const,
            secondary: agent.role ? humanizeKey(agent.role) : agent.slug,
        }));
        const skills: CommandPaletteItem[] = paletteSkills.slice(0, 8).map((skill) => ({
            id: `skill-${skill.id}`,
            label: skill.name,
            path: "/skills",
            group: "skills" as const,
            secondary: skill.slug || skill.purpose?.slice(0, 72) || "Skill",
        }));
        return [
            ...suggested,
            ...recent,
            ...approvals,
            ...runs,
            ...agents,
            ...skills,
            ...actions,
            ...pages,
        ];
    }, [
        pendingCount,
        unreadNotifications,
        visibleNavItems,
        paletteApprovals,
        paletteRuns,
        paletteAgents,
        paletteSkills,
    ]);

    useEffect(() => {
        function onKeyDown(e: KeyboardEvent) {
            const isModK = (e.ctrlKey || e.metaKey) && (e.key === "k" || e.key === "K");
            if (!isModK) {
                return;
            }
            e.preventDefault();
            setOpen((current) => !current);
        }
        window.addEventListener("keydown", onKeyDown);
        return () => window.removeEventListener("keydown", onKeyDown);
    }, []);

    return {
        open,
        setOpen,
        shortcutLabel,
        items,
    };
}
