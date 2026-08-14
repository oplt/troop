import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { Link as RouterLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import {
    AppBar,
    Avatar,
    Badge,
    Breadcrumbs,
    Box,
    Button,
    Chip,
    Collapse,
    Divider,
    Drawer,
    IconButton,
    Link,
    List,
    ListItemButton,
    ListItemIcon,
    ListItemText,
    Stack,
    Toolbar,
    Tooltip,
    Typography,
    useMediaQuery,
} from "@mui/material";
import {
    ArrowBack as ArrowBackIcon,
    Assignment as MyTasksIcon,
    AutoAwesome as AiStudioIcon,
    Business as DepartmentsIcon,
    Cable as IntegrationsIcon,
    ChevronLeft as ChevronLeftIcon,
    ChevronRight as ChevronRightIcon,
    CorporateFare as CompaniesIcon,
    Dashboard as DashboardIcon,
    DarkMode as DarkModeIcon,
    ExpandLess as ExpandLessIcon,
    ExpandMore as ExpandMoreIcon,
    Forum as BrainstormsIcon,
    Hub as ProjectsIcon,
    Insights as ExecutionIcon,
    LibraryBooks as WorkflowTemplatesIcon,
    LightMode as LightModeIcon,
    Logout as LogoutIcon,
    Menu as MenuIcon,
    NotificationsNone as NotificationsIcon,
    AccountCircle as ProfileIcon,
    AccountTree as HierarchyIcon,
    AttachMoney as CostAnalyticsIcon,
    PendingActions as ApprovalsIcon,
    Psychology as SkillsIcon,
    Schema as WorkflowsIcon,
    Search as SearchIcon,
    Settings as SettingsIcon,
    SettingsBrightness as SystemModeIcon,
    SmartToy as AgentsIcon,
    Storefront as MarketplaceIcon,
    Tune as ModelSettingsIcon,
    ViewModule as PortfolioNavIcon,
} from "@mui/icons-material";
import { alpha, useTheme } from "@mui/material/styles";
import { useQuery } from "@tanstack/react-query";
import { useColorMode } from "../../app/colorModeContext";
import { getPendingApprovalsCount, getOrchestrationProject, listApprovals, listRuns, listAgents } from "../../api/orchestration";
import { listSkills } from "../../api/workforce";
import { getNotifications } from "../../api/notifications";
import { useCanonicalUser } from "../../hooks/useCanonicalUser";
import { useAuth } from "../../hooks/useAuth";
import { queryKeys, defaultQueryStaleTimeMs } from "../../config/queryKeys";
import { queryPolicies } from "../../config/queryPolicies";
import { usePlatformMetadata } from "../../hooks/usePlatformMetadata";
import { getInitials, humanizeKey } from "../../utils/formatters";
import { CommandPalette, type CommandPaletteItem } from "./CommandPalette";
import {
    NAV_GROUPS,
    NAV_ITEM_DEFS,
    pathMatchesNavItem,
    readExpandedNavGroups,
    writeExpandedNavGroups,
    type NavGroupId,
    type NavIconId,
    type NavItemDef,
} from "./navConfig";
import { commandShortcutLabel, readRecentProjects, recordRecentProject } from "./recentProjects";

const DRAWER_WIDTH = 288;
const COLLAPSED_DRAWER_WIDTH = 96;
/** Keep AppBar / drawer / main margin on the same curve to avoid CLS on collapse. */
const SHELL_TRANSITION_MS = 330;

const NAV_ICONS: Record<NavIconId, ReactNode> = {
    dashboard: <DashboardIcon />,
    projects: <ProjectsIcon />,
    myTasks: <MyTasksIcon />,
    approvals: <ApprovalsIcon />,
    agents: <AgentsIcon />,
    skills: <SkillsIcon />,
    marketplace: <MarketplaceIcon />,
    hierarchy: <HierarchyIcon />,
    workflows: <WorkflowsIcon />,
    workflowTemplates: <WorkflowTemplatesIcon />,
    integrations: <IntegrationsIcon />,
    portfolio: <PortfolioNavIcon />,
    cost: <CostAnalyticsIcon />,
    execution: <ExecutionIcon />,
    brainstorms: <BrainstormsIcon />,
    aiStudio: <AiStudioIcon />,
    departments: <DepartmentsIcon />,
    companies: <CompaniesIcon />,
    modelSettings: <ModelSettingsIcon />,
    settings: <SettingsIcon />,
};

type NavItem = {
    label: string;
    icon: ReactNode;
    path: string;
    adminOnly?: boolean;
    badge?: number;
    /** Shown under the label when the drawer is expanded (e.g. pending approvals). */
    subtitle?: string;
    group: NavGroupId;
};

function navItemFromDef(
    def: NavItemDef,
    extras?: { badge?: number; subtitle?: string },
): NavItem {
    return {
        label: def.label,
        path: def.path,
        group: def.group,
        adminOnly: def.adminOnly,
        icon: NAV_ICONS[def.icon],
        badge: extras?.badge,
        subtitle: extras?.subtitle,
    };
}

type BreadcrumbItem = {
    label: string;
    path: string;
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

function buildBreadcrumbs(
    pathname: string,
    navItems: NavItem[],
    resolveSegmentLabel?: (segment: string, index: number, segments: string[]) => string | undefined,
): BreadcrumbItem[] {
    const exact = navItems.find((item) => item.path === pathname);
    if (exact) {
        return [{ label: exact.label, path: exact.path }];
    }
    const root = [...navItems]
        .sort((left, right) => right.path.length - left.path.length)
        .find((item) => pathname.startsWith(item.path));
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

export function ThemeToggle() {
    const { colorMode, setColorMode } = useColorMode();
    const cycle = () => {
        const next: Record<string, typeof colorMode> = { light: "dark", dark: "system", system: "light" };
        setColorMode(next[colorMode]);
    };
    const icon =
        colorMode === "light" ? <LightModeIcon fontSize="small" /> :
        colorMode === "dark" ? <DarkModeIcon fontSize="small" /> :
        <SystemModeIcon fontSize="small" />;

    const nextMode = colorMode === "light" ? "dark" : colorMode === "dark" ? "system" : "light";

    return (
        <Tooltip title={`Switch theme to ${nextMode} (currently ${colorMode})`}>
            <IconButton
                onClick={cycle}
                size="small"
                aria-label={`Switch theme to ${nextMode}`}
                sx={{ borderRadius: 1, minWidth: 40, minHeight: 40 }}
            >
                {icon}
            </IconButton>
        </Tooltip>
    );
}

function NavItemButton({
    item,
    currentPath,
    onNavigate,
    collapsed,
}: {
    item: NavItem;
    currentPath: string;
    onNavigate: (path: string) => void;
    collapsed: boolean;
}) {
    const selected = pathMatchesNavItem(currentPath, item.path);
    const itemButton = (
        <ListItemButton
            selected={selected}
            aria-label={collapsed ? item.label : undefined}
            onClick={() => onNavigate(item.path)}
            sx={
                collapsed
                    ? {
                          minHeight: 48,
                          px: 1,
                          justifyContent: "center",
                      }
                    : {
                          minHeight: 40,
                          pl: 2,
                          pr: 1.5,
                      }
            }
        >
            <ListItemIcon
                sx={{
                    minWidth: collapsed ? "auto" : 40,
                    justifyContent: "center",
                }}
            >
                {item.badge ? (
                    <Badge badgeContent={item.badge} color="error" max={99}>
                        {item.icon}
                    </Badge>
                ) : (
                    item.icon
                )}
            </ListItemIcon>
            {!collapsed && (
                <ListItemText
                    primary={item.label}
                    secondary={item.subtitle}
                    secondaryTypographyProps={{ sx: { fontSize: "0.74rem" } }}
                />
            )}
        </ListItemButton>
    );

    if (!collapsed) {
        return itemButton;
    }

    const collapsedTitle =
        item.path === "/approvals" && item.badge
            ? `${item.label} — ${item.badge} pending approval${item.badge === 1 ? "" : "s"}`
            : item.label;
    return (
        <Tooltip title={collapsedTitle} placement="right">
            {itemButton}
        </Tooltip>
    );
}

function NavGroupBlock({
    groupId,
    title,
    items,
    currentPath,
    onNavigate,
    drawerCollapsed,
    expanded,
    onToggle,
}: {
    groupId: NavGroupId;
    title: string;
    items: NavItem[];
    currentPath: string;
    onNavigate: (path: string) => void;
    drawerCollapsed: boolean;
    expanded: boolean;
    onToggle: (groupId: NavGroupId) => void;
}) {
    if (items.length === 0) {
        return null;
    }

    if (drawerCollapsed) {
        return (
            <List disablePadding sx={{ display: "grid", gap: 0.75 }}>
                {items.map((item) => (
                    <NavItemButton
                        key={item.path}
                        item={item}
                        currentPath={currentPath}
                        onNavigate={onNavigate}
                        collapsed
                    />
                ))}
            </List>
        );
    }

    const groupBadge = items.reduce((sum, item) => sum + (item.badge ?? 0), 0);

    return (
        <Stack spacing={0.5}>
            <ListItemButton
                onClick={() => onToggle(groupId)}
                aria-expanded={expanded}
                aria-controls={`nav-group-${groupId}`}
                sx={{ minHeight: 36, px: 1.5, borderRadius: 1 }}
            >
                <ListItemText
                    primary={title}
                    primaryTypographyProps={{
                        variant: "overline",
                        color: "text.secondary",
                        sx: { lineHeight: 1.2 },
                    }}
                />
                {groupBadge > 0 && (
                    <Badge badgeContent={groupBadge} color="error" max={99} sx={{ mr: 1 }} />
                )}
                {expanded ? (
                    <ExpandLessIcon fontSize="small" sx={{ color: "text.secondary" }} />
                ) : (
                    <ExpandMoreIcon fontSize="small" sx={{ color: "text.secondary" }} />
                )}
            </ListItemButton>
            <Collapse in={expanded} timeout="auto" unmountOnExit>
                <List
                    id={`nav-group-${groupId}`}
                    disablePadding
                    sx={{ display: "grid", gap: 0.5, pb: 0.5 }}
                >
                    {items.map((item) => (
                        <NavItemButton
                            key={item.path}
                            item={item}
                            currentPath={currentPath}
                            onNavigate={onNavigate}
                            collapsed={false}
                        />
                    ))}
                </List>
            </Collapse>
        </Stack>
    );
}

export function AppLayout() {
    const [drawerOpen, setDrawerOpen] = useState(false);
    const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);
    const [desktopNavCollapsed, setDesktopNavCollapsed] = useState(false);
    const [expandedGroups, setExpandedGroups] = useState<NavGroupId[]>(readExpandedNavGroups);
    const { logout, isAdmin, isAuthenticated, isReady } = useAuth();
    const navigate = useNavigate();
    const location = useLocation();
    const theme = useTheme();
    const isMobile = useMediaQuery(theme.breakpoints.down("md"));
    const { data: platformMetadata } = usePlatformMetadata();

    const authReady = isReady && isAuthenticated;
    const { user: currentUser, profile } = useCanonicalUser({ profileEnabled: authReady });
    const { data: pendingApprovals } = useQuery({
        queryKey: queryKeys.orchestration.approvalsPendingCount,
        queryFn: getPendingApprovalsCount,
        ...queryPolicies.operational,
        refetchInterval: 30_000,
        enabled: authReady,
        retry: false,
    });
    const { data: notifications } = useQuery({
        queryKey: queryKeys.notifications.root,
        queryFn: getNotifications,
        ...queryPolicies.operational,
        refetchInterval: 60_000,
        enabled: authReady,
        retry: false,
    });
    const pendingCount = pendingApprovals?.count ?? 0;
    const unreadNotifications = notifications?.filter((item) => !item.is_read).length ?? 0;

    const { data: paletteApprovals = [] } = useQuery({
        queryKey: queryKeys.orchestration.approvals,
        queryFn: listApprovals,
        ...queryPolicies.operational,
        enabled: authReady && commandPaletteOpen,
        retry: false,
    });
    const { data: paletteRuns = [] } = useQuery({
        queryKey: ["orchestration", "runs", "command-palette"],
        queryFn: () => listRuns(),
        ...queryPolicies.operational,
        enabled: authReady && commandPaletteOpen,
        retry: false,
    });
    const { data: paletteAgents = [] } = useQuery({
        queryKey: queryKeys.orchestration.agents(),
        queryFn: () => listAgents(),
        ...queryPolicies.operational,
        enabled: authReady && commandPaletteOpen,
        staleTime: defaultQueryStaleTimeMs,
        retry: false,
    });
    const { data: paletteSkills = [] } = useQuery({
        queryKey: ["workforce", "skills", "command-palette"],
        queryFn: listSkills,
        ...queryPolicies.operational,
        enabled: authReady && commandPaletteOpen,
        staleTime: defaultQueryStaleTimeMs,
        retry: false,
    });

    const appName = platformMetadata?.app_name ?? "Troop";
    const shortcutLabel = useMemo(() => commandShortcutLabel(), []);
    const hasAiModule =
        platformMetadata?.module_catalog.some((item) => item.key === "ai" && item.enabled) ?? false;
    const drawerCollapsed = !isMobile && desktopNavCollapsed;
    const desktopDrawerWidth = drawerCollapsed ? COLLAPSED_DRAWER_WIDTH : DRAWER_WIDTH;

    const navItems = useMemo<NavItem[]>(
        () =>
            NAV_ITEM_DEFS.filter((def) => !def.requiresAiModule || hasAiModule).map((def) => {
                if (def.id === "approvals") {
                    return navItemFromDef(def, {
                        badge: pendingCount || undefined,
                        subtitle:
                            pendingCount > 0
                                ? `${pendingCount} pending approval${pendingCount === 1 ? "" : "s"}`
                                : undefined,
                    });
                }
                return navItemFromDef(def);
            }),
        [hasAiModule, pendingCount],
    );

    const visibleNavItems = navItems.filter((item) => !item.adminOnly || isAdmin);

    const activeGroupId = useMemo(() => {
        const match = [...visibleNavItems]
            .sort((left, right) => right.path.length - left.path.length)
            .find((item) => pathMatchesNavItem(location.pathname, item.path));
        return match?.group;
    }, [location.pathname, visibleNavItems]);

    const [trackedActiveGroup, setTrackedActiveGroup] = useState<NavGroupId | undefined>(activeGroupId);
    if (activeGroupId !== trackedActiveGroup) {
        setTrackedActiveGroup(activeGroupId);
        if (activeGroupId && !expandedGroups.includes(activeGroupId)) {
            const next = [...expandedGroups, activeGroupId];
            setExpandedGroups(next);
            writeExpandedNavGroups(next);
        }
    }

    const toggleGroup = useCallback((groupId: NavGroupId) => {
        setExpandedGroups((current) => {
            const next = current.includes(groupId)
                ? current.filter((id) => id !== groupId)
                : [...current, groupId];
            writeExpandedNavGroups(next);
            return next;
        });
    }, []);

    const commandItems = useMemo<CommandPaletteItem[]>(() => {
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
        const ACTIVE_RUN = new Set(["queued", "in_progress", "running", "waiting", "blocked"]);
        const STUCK_RUN = new Set(["failed", "error", "cancelled", "timed_out"]);
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
            setCommandPaletteOpen((open) => !open);
        }
        window.addEventListener("keydown", onKeyDown);
        return () => window.removeEventListener("keydown", onKeyDown);
    }, []);

    const currentItem = visibleNavItems.find((item) => pathMatchesNavItem(location.pathname, item.path));
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
    const canGoBack = breadcrumbs.length > 1 || location.pathname !== (currentItem?.path ?? "/dashboard");
    const avatarLabel = getInitials(currentUser?.full_name, currentUser?.email);

    function handleNavigate(path: string) {
        navigate(path);
        setDrawerOpen(false);
    }

    async function handleSignOut() {
        await logout();
        setDrawerOpen(false);
        navigate("/", { replace: true });
    }

    const drawerContent = (
        <Stack sx={{ height: "100%", p: drawerCollapsed ? 1.25 : 2 }}>
            <Tooltip
                title={appName}
                placement="right"
                disableHoverListener={!drawerCollapsed}
            >
                <Box
                    sx={{
                        borderRadius: 1,
                        px: drawerCollapsed ? 1 : 2,
                        py: drawerCollapsed ? 1.75 : 2.25,
                        mb: 2,
                        backgroundColor: "background.paper",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: drawerCollapsed ? "center" : "flex-start",
                        textAlign: drawerCollapsed ? "center" : "left",
                    }}
                >
                    {drawerCollapsed ? (
                        <Typography variant="h6" sx={{ lineHeight: 1 }}>
                            {appName.trim().charAt(0).toUpperCase() || "W"}
                        </Typography>
                    ) : (
                        <Box>
                            <Typography variant="h6" sx={{ mt: 0.5 }}>
                                {appName}
                            </Typography>
                            <Typography variant="caption" color="text.secondary">
                                Workspace
                            </Typography>
                        </Box>
                    )}
                </Box>
            </Tooltip>

            <Stack
                spacing={drawerCollapsed ? 1 : 0.75}
                sx={{ overflowY: "auto", flexGrow: 1, minHeight: 0 }}
            >
                {NAV_GROUPS.map((group) => {
                    const items = visibleNavItems.filter((item) => item.group === group.id);
                    if (items.length === 0) {
                        return null;
                    }
                    if (drawerCollapsed && group.id === "admin") {
                        return (
                            <Stack key={group.id} spacing={1}>
                                <Divider sx={{ mx: 1.5 }} />
                                <NavGroupBlock
                                    groupId={group.id}
                                    title={group.title}
                                    items={items}
                                    currentPath={location.pathname}
                                    onNavigate={handleNavigate}
                                    drawerCollapsed={drawerCollapsed}
                                    expanded={expandedGroups.includes(group.id)}
                                    onToggle={toggleGroup}
                                />
                            </Stack>
                        );
                    }
                    return (
                        <NavGroupBlock
                            key={group.id}
                            groupId={group.id}
                            title={group.title}
                            items={items}
                            currentPath={location.pathname}
                            onNavigate={handleNavigate}
                            drawerCollapsed={drawerCollapsed}
                            expanded={expandedGroups.includes(group.id)}
                            onToggle={toggleGroup}
                        />
                    );
                })}
            </Stack>

            <Box
                sx={(theme) => ({
                    mt: 2,
                    p: drawerCollapsed ? 1.25 : 2,
                    borderRadius: 1,
                    backgroundColor:
                        theme.palette.mode === "dark"
                            ? alpha(theme.palette.common.white, 0.04)
                            : theme.palette.grey[50],
                })}
            >
                <Stack spacing={1.5} alignItems={drawerCollapsed ? "center" : "stretch"}>
                    <Stack
                        direction={drawerCollapsed ? "column" : "row"}
                        spacing={1.5}
                        alignItems="center"
                        justifyContent="center"
                        sx={{ width: "100%" }}
                    >
                        <Avatar
                            src={profile?.avatar_url ?? undefined}
                            sx={{ width: drawerCollapsed ? 40 : 44, height: drawerCollapsed ? 40 : 44 }}
                        >
                            {avatarLabel}
                        </Avatar>
                        {!drawerCollapsed && (
                            <Box sx={{ minWidth: 0 }}>
                                <Typography variant="subtitle2" noWrap>
                                    {currentUser?.full_name ?? "Your profile"}
                                </Typography>
                                <Typography variant="caption" color="text.secondary" noWrap>
                                    {currentUser?.email ?? "Signed in"}
                                </Typography>
                            </Box>
                        )}
                    </Stack>
                    {drawerCollapsed ? (
                        <Stack spacing={1}>
                            <Tooltip title="Manage profile" placement="right">
                                <IconButton
                                    onClick={() => handleNavigate("/profile")}
                                    aria-label="Manage profile"
                                    sx={{ borderRadius: 1, minWidth: 40, minHeight: 40 }}
                                >
                                    <ProfileIcon fontSize="small" />
                                </IconButton>
                            </Tooltip>
                            <Tooltip title="Sign out" placement="right">
                                <IconButton
                                    onClick={() => void handleSignOut()}
                                    aria-label="Sign out"
                                    sx={{ borderRadius: 1, minWidth: 40, minHeight: 40 }}
                                >
                                    <LogoutIcon fontSize="small" />
                                </IconButton>
                            </Tooltip>
                        </Stack>
                    ) : (
                        <Stack spacing={1}>
                            <Button
                                variant="text"
                                color="inherit"
                                fullWidth
                                startIcon={<ProfileIcon />}
                                onClick={() => handleNavigate("/profile")}
                            >
                                Profile
                            </Button>
                            <Button
                                variant="text"
                                color="inherit"
                                fullWidth
                                startIcon={<LogoutIcon />}
                                onClick={() => void handleSignOut()}
                            >
                                Sign out
                            </Button>
                        </Stack>
                    )}
                </Stack>
            </Box>
        </Stack>
    );

    return (
        <Box sx={{ minHeight: "100vh" }}>
            <Box
                component="a"
                href="#main-content"
                sx={{
                    position: "absolute",
                    left: -10000,
                    top: 0,
                    zIndex: (t) => t.zIndex.tooltip + 1,
                    px: 2,
                    py: 1,
                    borderRadius: 1,
                    backgroundColor: "background.paper",
                    color: "text.primary",
                    border: "1px solid",
                    borderColor: "divider",
                    textDecoration: "none",
                    "&:focus": {
                        left: 16,
                        top: 16,
                    },
                }}
            >
                Skip to main content
            </Box>
            <AppBar
                position="fixed"
                elevation={0}
                sx={{
                    left: { md: `${desktopDrawerWidth}px` },
                    width: { md: `calc(100% - ${desktopDrawerWidth}px)` },
                    backgroundColor: (t) =>
                        t.palette.mode === "dark"
                            ? alpha(t.palette.background.default, 0.88)
                            : "rgba(255, 255, 255, 0.75)",
                    color: "text.primary",
                    backdropFilter: "blur(12px)",
                    borderBottom: "1px solid",
                    borderColor: "divider",
                    transition: theme.transitions.create(["left", "width", "background-color"], {
                        duration: SHELL_TRANSITION_MS,
                        easing: theme.transitions.easing.easeInOut,
                    }),
                }}
            >
                <Toolbar
                    sx={{
                        minHeight: { xs: 64, md: 72 },
                        height: { xs: 64, md: 72 },
                        px: { xs: 2, md: 3 },
                        gap: 1,
                        boxSizing: "border-box",
                    }}
                >
                    {isMobile ? (
                        <IconButton
                            edge="start"
                            aria-label="Open navigation menu"
                            onClick={() => setDrawerOpen(true)}
                            sx={{ borderRadius: 1, minWidth: 40, minHeight: 40 }}
                        >
                            <MenuIcon />
                        </IconButton>
                    ) : (
                        <Tooltip title={drawerCollapsed ? "Expand menu" : "Collapse menu"}>
                            <IconButton
                                edge="start"
                                aria-label={drawerCollapsed ? "Expand navigation" : "Collapse navigation"}
                                onClick={() => setDesktopNavCollapsed((current) => !current)}
                                sx={{ borderRadius: 1, minWidth: 40, minHeight: 40 }}
                            >
                                {drawerCollapsed ? <ChevronRightIcon /> : <ChevronLeftIcon />}
                            </IconButton>
                        </Tooltip>
                    )}
                    <Box sx={{ minWidth: 0, flexGrow: 1 }}>
                        <Stack direction="row" spacing={1} alignItems="center" sx={{ minWidth: 0 }}>
                            {canGoBack && isMobile ? (
                                <IconButton
                                    size="small"
                                    aria-label="Go back"
                                    onClick={() => navigate(-1)}
                                    sx={{ borderRadius: 1, minWidth: 40, minHeight: 40 }}
                                >
                                    <ArrowBackIcon fontSize="small" />
                                </IconButton>
                            ) : null}
                            <Breadcrumbs
                                separator="›"
                                aria-label="breadcrumb"
                                sx={{
                                    "& .MuiBreadcrumbs-ol": { flexWrap: "nowrap" },
                                    "& .MuiBreadcrumbs-li": { minWidth: 0 },
                                }}
                            >
                                {breadcrumbs.map((crumb, index) => {
                                    const isLast = index === breadcrumbs.length - 1;
                                    const crumbSx = {
                                        minWidth: 0,
                                        maxWidth: { xs: 140, sm: 220, md: 320 },
                                        overflow: "hidden",
                                        textOverflow: "ellipsis",
                                        whiteSpace: "nowrap",
                                    } as const;
                                    return (
                                        <Link
                                            key={`${index}-${crumb.path}`}
                                            component={RouterLink}
                                            to={crumb.path}
                                            underline="hover"
                                            color="inherit"
                                            aria-current={isLast ? "page" : undefined}
                                            onClick={() => setDrawerOpen(false)}
                                            sx={{
                                                ...crumbSx,
                                                typography: isLast ? "subtitle1" : "body2",
                                                fontWeight: 500,
                                                color: isLast ? "text.primary" : "text.secondary",
                                            }}
                                        >
                                            {crumb.label}
                                        </Link>
                                    );
                                })}
                            </Breadcrumbs>
                        </Stack>
                    </Box>
                    <Stack direction="row" spacing={0.5} alignItems="center">
                        <Tooltip title={`Command palette (${shortcutLabel})`}>
                            <Button
                                size="small"
                                variant="text"
                                color="inherit"
                                onClick={() => setCommandPaletteOpen(true)}
                                startIcon={<SearchIcon fontSize="small" />}
                                aria-label={`Open command palette (${shortcutLabel})`}
                                sx={{
                                    display: { xs: "none", sm: "inline-flex" },
                                    minHeight: 40,
                                    color: "text.secondary",
                                    px: 1,
                                }}
                            >
                                <Chip
                                    label={shortcutLabel}
                                    size="small"
                                    variant="outlined"
                                    sx={{ height: 22, borderRadius: 1, "& .MuiChip-label": { px: 0.75 } }}
                                />
                            </Button>
                        </Tooltip>
                        <Tooltip title={`Command palette (${shortcutLabel})`}>
                            <IconButton
                                aria-label={`Open command palette (${shortcutLabel})`}
                                onClick={() => setCommandPaletteOpen(true)}
                                sx={{ display: { xs: "inline-flex", sm: "none" }, borderRadius: 1, minWidth: 40, minHeight: 40 }}
                            >
                                <SearchIcon />
                            </IconButton>
                        </Tooltip>
                        <Tooltip title={unreadNotifications > 0 ? `${unreadNotifications} unread notifications` : "Notifications"}>
                            <IconButton
                                aria-label={
                                    unreadNotifications > 0
                                        ? `Notifications, ${unreadNotifications} unread`
                                        : "Notifications"
                                }
                                onClick={() => handleNavigate("/notifications")}
                                sx={{ borderRadius: 1, minWidth: 40, minHeight: 40 }}
                            >
                                <Badge badgeContent={unreadNotifications || undefined} color="error" max={99}>
                                    <NotificationsIcon />
                                </Badge>
                            </IconButton>
                        </Tooltip>
                        <ThemeToggle />
                    </Stack>
                </Toolbar>
            </AppBar>

            {isMobile ? (
                <Drawer
                    open={drawerOpen}
                    onClose={() => setDrawerOpen(false)}
                    ModalProps={{ keepMounted: true }}
                    sx={{ "& .MuiDrawer-paper": { width: DRAWER_WIDTH } }}
                    slotProps={{
                        paper: {
                            component: "nav",
                            "aria-label": "Primary",
                        },
                    }}
                >
                    {drawerContent}
                </Drawer>
            ) : (
                <Drawer
                    variant="permanent"
                    open
                    sx={{
                        width: desktopDrawerWidth,
                        flexShrink: 0,
                        "& .MuiDrawer-paper": {
                            width: desktopDrawerWidth,
                            boxSizing: "border-box",
                            overflowX: "hidden",
                            borderRight: "1px solid",
                            borderColor: "divider",
                            transition: theme.transitions.create("width", {
                                duration: SHELL_TRANSITION_MS,
                                easing: theme.transitions.easing.easeInOut,
                            }),
                        },
                    }}
                    slotProps={{
                        paper: {
                            component: "nav",
                            "aria-label": "Primary",
                        },
                    }}
                >
                    {drawerContent}
                </Drawer>
            )}

            <Box
                component="main"
                id="main-content"
                tabIndex={-1}
                sx={{
                    minHeight: "100vh",
                    ml: { md: `${desktopDrawerWidth}px` },
                    pt: { xs: "64px", md: "72px" },
                    outline: "none",
                    transition: theme.transitions.create("margin-left", {
                        duration: SHELL_TRANSITION_MS,
                        easing: theme.transitions.easing.easeInOut,
                    }),
                }}
            >
                <Outlet />
            </Box>

            <CommandPalette
                open={commandPaletteOpen}
                onClose={() => setCommandPaletteOpen(false)}
                items={commandItems}
                onNavigate={handleNavigate}
            />
        </Box>
    );
}
