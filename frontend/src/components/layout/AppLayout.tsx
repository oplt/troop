import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link as RouterLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import {
    AppBar,
    Avatar,
    Badge,
    Breadcrumbs,
    Box,
    Button,
    Chip,
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
    Analytics as ActivityIcon,
    ArrowBack as ArrowBackIcon,
    ChevronLeft as ChevronLeftIcon,
    ChevronRight as ChevronRightIcon,
    Dashboard as DashboardIcon,
    DarkMode as DarkModeIcon,
    Hub as AgentProjectsIcon,
    LightMode as LightModeIcon,
    Logout as LogoutIcon,
    Menu as MenuIcon,
    AccountCircle as ProfileIcon,
    AttachMoney as CostAnalyticsIcon,
    Forum as BrainstormsIcon,
    Tune as ModelSettingsIcon,
    ViewModule as PortfolioNavIcon,
    AccountTree as WorkflowTemplatesIcon,
    Settings as SettingsIcon,
    SettingsBrightness as SystemModeIcon,
    SmartToy as AgentsIcon,
} from "@mui/icons-material";
import { alpha, useTheme } from "@mui/material/styles";
import { useQuery } from "@tanstack/react-query";
import { useColorMode } from "../../app/colorModeContext";
import { getPendingApprovalsCount, getOrchestrationProject } from "../../api/orchestration";
import { useCanonicalUser } from "../../hooks/useCanonicalUser";
import { useAuth } from "../../hooks/useAuth";
import { queryKeys, defaultQueryStaleTimeMs } from "../../config/queryKeys";
import { queryPolicies } from "../../config/queryPolicies";
import { usePlatformMetadata } from "../../hooks/usePlatformMetadata";
import { getInitials } from "../../utils/formatters";
import { CommandPalette } from "./CommandPalette";
import GroupsIcon from '@mui/icons-material/Groups';
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome';
import BusinessIcon from '@mui/icons-material/Business';
import PsychologyIcon from '@mui/icons-material/Psychology';

const DRAWER_WIDTH = 288;
const COLLAPSED_DRAWER_WIDTH = 96;

type NavItem = {
    label: string;
    icon: ReactNode;
    path: string;
    adminOnly?: boolean;
    badge?: number;
    /** Shown under the label when the drawer is expanded (e.g. pending approvals). */
    subtitle?: string;
    group: "workspace" | "admin";
};

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
                sx={{ borderRadius: 1 }}
            >
                {icon}
            </IconButton>
        </Tooltip>
    );
}

function NavBlock({
    title,
    items,
    currentPath,
    onNavigate,
    collapsed,
}: {
    title?: string;
    items: NavItem[];
    currentPath: string;
    onNavigate: (path: string) => void;
    collapsed: boolean;
}) {
    if (items.length === 0) {
        return null;
    }

    return (
        <Stack spacing={1}>
            {!collapsed && title && (
                <Typography variant="overline" color="text.secondary" sx={{ px: 1.5 }}>
                    {title}
                </Typography>
            )}
            <List disablePadding sx={{ display: "grid", gap: 0.75 }}>
                {items.map((item) => {
                    const selected =
                        item.path === "/dashboard"
                            ? currentPath === item.path
                            : currentPath.startsWith(item.path);
                    const itemButton = (
                        <ListItemButton
                            key={item.path}
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
                                    : undefined
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
                                    secondary={
                                        item.subtitle
                                            ? item.subtitle
                                            : selected
                                              ? "Current section"
                                              : undefined
                                    }
                                    secondaryTypographyProps={{ sx: { fontSize: "0.74rem" } }}
                                />
                            )}
                        </ListItemButton>
                    );

                    if (!collapsed) {
                        return itemButton;
                    }

                    const collapsedTitle =
                        item.path === "/activity" && item.badge
                            ? `${item.label} — ${item.badge} pending approval${item.badge === 1 ? "" : "s"}`
                            : item.label;
                    return (
                        <Tooltip key={item.path} title={collapsedTitle} placement="right">
                            {itemButton}
                        </Tooltip>
                    );
                })}
            </List>
        </Stack>
    );
}

export function AppLayout() {
    const [drawerOpen, setDrawerOpen] = useState(false);
    const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);
    const [desktopNavCollapsed, setDesktopNavCollapsed] = useState(false);
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
    const pendingCount = pendingApprovals?.count ?? 0;
    const appName = platformMetadata?.app_name ?? "Troop";
    const hasAiModule =
        platformMetadata?.module_catalog.some((item) => item.key === "ai" && item.enabled) ?? false;
    const drawerCollapsed = !isMobile && desktopNavCollapsed;
    const desktopDrawerWidth = drawerCollapsed ? COLLAPSED_DRAWER_WIDTH : DRAWER_WIDTH;

    const navItems = useMemo<NavItem[]>(
        () => [
            { label: "Dashboard", icon: <DashboardIcon />, path: "/dashboard", group: "workspace" },
            { label: "Projects", icon: <AgentProjectsIcon />, path: "/agent-projects", group: "workspace" },
            {
                label: "Approvals",
                icon: <ActivityIcon />,
                path: "/activity",
                group: "workspace",
                badge: pendingCount || undefined,
                subtitle:
                    pendingCount > 0
                        ? `${pendingCount} pending approval${pendingCount === 1 ? "" : "s"}`
                        : undefined,
            },
            { label: "Agents", icon: <AgentsIcon />, path: "/agents", group: "workspace" },
            { label: "Skills", icon: <PsychologyIcon />, path: "/skills", group: "workspace" },
            { label: "Teams", icon: <GroupsIcon />, path: "/hierarchy-builder", group: "workspace" },
            { label: "Workflows", icon: <WorkflowTemplatesIcon />, path: "/workflow-templates", group: "workspace" },
            { label: "Departments", icon: <BusinessIcon />, path: "/departments", group: "workspace" },
            { label: "Knowledge", icon: <AutoAwesomeIcon />, path: "/companies", group: "workspace" },
            { label: "Model settings", icon: <ModelSettingsIcon />, path: "/model-settings", group: "workspace" },
            { label: "Portfolio", icon: <PortfolioNavIcon />, path: "/agent-portfolio", group: "workspace" },
            { label: "Cost & usage", icon: <CostAnalyticsIcon />, path: "/analytics/cost", group: "workspace" },
            { label: "Execution insights", icon: <ActivityIcon />, path: "/analytics/execution", group: "workspace" },
            { label: "Brainstorms", icon: <BrainstormsIcon />, path: "/brainstorms", group: "workspace" },
            ...(hasAiModule
                ? [{ label: "AI Studio", icon: <AutoAwesomeIcon />, path: "/ai", group: "workspace" as const }]
                : []),
            { label: "Settings", icon: <SettingsIcon />, path: "/admin/settings", adminOnly: true, group: "admin" },
        ],
        [hasAiModule, pendingCount]
    );

    const visibleNavItems = navItems.filter((item) => !item.adminOnly || isAdmin);

    const commandRoutes = useMemo(
        () => visibleNavItems.map((item) => ({ label: item.label, path: item.path })),
        [visibleNavItems],
    );

    useEffect(() => {
        function onKeyDown(e: KeyboardEvent) {
            const isModK = (e.ctrlKey || e.metaKey) && (e.key === "k" || e.key === "K");
            const t = e.target as HTMLElement | null;
            const inField =
                !!t &&
                (t.tagName === "INPUT" ||
                    t.tagName === "TEXTAREA" ||
                    t.tagName === "SELECT" ||
                    t.isContentEditable);
            if (isModK) {
                e.preventDefault();
                setCommandPaletteOpen((open) => !open);
                return;
            }
            if (inField) return;
            if (e.key === "k" || e.key === "K") {
                if (e.ctrlKey || e.metaKey || e.altKey) return;
                e.preventDefault();
                setCommandPaletteOpen(true);
            }
        }
        window.addEventListener("keydown", onKeyDown);
        return () => window.removeEventListener("keydown", onKeyDown);
    }, []);

    const currentItem = visibleNavItems.find((item) =>
        item.path === "/dashboard" ? location.pathname === item.path : location.pathname.startsWith(item.path)
    );
    const projectIdFromPath = useMemo(() => {
        const match = location.pathname.match(/^\/agent-projects\/([^/]+)/);
        return match?.[1] ?? null;
    }, [location.pathname]);
    const { data: breadcrumbProject } = useQuery({
        queryKey: queryKeys.orchestration.project(projectIdFromPath ?? ""),
        queryFn: () => getOrchestrationProject(projectIdFromPath!),
        enabled: Boolean(projectIdFromPath),
        staleTime: defaultQueryStaleTimeMs,
    });

    const breadcrumbs = useMemo(
        () =>
            buildBreadcrumbs(location.pathname, visibleNavItems, (segment, index, segments) => {
                if (index > 0 && segments[index - 1] === "agent-projects") {
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

                            {platformMetadata?.module_pack && (
                                <Chip
                                    label={`Pack: ${platformMetadata.module_pack}`}
                                    size="small"
                                    variant="outlined"
                                    sx={{ mt: 1.5 }}
                                />
                            )}
                        </Box>
                    )}
                </Box>
            </Tooltip>

            <Stack spacing={drawerCollapsed ? 1 : 2}>
                <NavBlock
                    title="Workspace"
                    items={visibleNavItems.filter((item) => item.group === "workspace")}
                    currentPath={location.pathname}
                    onNavigate={handleNavigate}
                    collapsed={drawerCollapsed}
                />
                {isAdmin && drawerCollapsed && <Divider sx={{ mx: 1.5 }} />}
                {isAdmin && (
                    <NavBlock
                        title="Admin"
                        items={visibleNavItems.filter((item) => item.group === "admin")}
                        currentPath={location.pathname}
                        onNavigate={handleNavigate}
                        collapsed={drawerCollapsed}
                    />
                )}
            </Stack>

            <Box sx={{ flexGrow: 1 }} />

            <Box
                sx={(theme) => ({
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
                                    sx={{ borderRadius: 1 }}
                                >
                                    <ProfileIcon fontSize="small" />
                                </IconButton>
                            </Tooltip>
                            <Tooltip title="Sign out" placement="right">
                                <IconButton
                                    onClick={() => void handleSignOut()}
                                    aria-label="Sign out"
                                    sx={{ borderRadius: 1 }}
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
                    transition: theme.transitions.create(["left", "width", "background-color"], {
                        duration: 330,
                    }),
                }}
            >
                <Toolbar sx={{ minHeight: { xs: 72, md: 80 }, px: { xs: 2, md: 3 } }}>
                    {isMobile ? (
                        <IconButton edge="start" aria-label="Open navigation menu" onClick={() => setDrawerOpen(true)} sx={{ mr: 1.25 }}>
                            <MenuIcon />
                        </IconButton>
                    ) : (
                        <Tooltip title={drawerCollapsed ? "Expand menu" : "Collapse menu"}>
                            <IconButton
                                edge="start"
                                aria-label={drawerCollapsed ? "Expand navigation" : "Collapse navigation"}
                                onClick={() => setDesktopNavCollapsed((current) => !current)}
                                sx={{ mr: 1.25, borderRadius: 1 }}
                            >
                                {drawerCollapsed ? <ChevronRightIcon /> : <ChevronLeftIcon />}
                            </IconButton>
                        </Tooltip>
                    )}
                    <Box sx={{ minWidth: 0, flexGrow: 1 }}>
                        <Typography variant="caption" color="text.secondary">
                            {appName}
                        </Typography>
                        <Stack direction="row" spacing={1} alignItems="center" sx={{ minWidth: 0 }}>
                            {canGoBack ? (
                                <Button
                                    size="small"
                                    variant="text"
                                    startIcon={<ArrowBackIcon fontSize="small" />}
                                    onClick={() => navigate(-1)}
                                    sx={{ minWidth: "auto", px: 0.75 }}
                                >
                                    Back
                                </Button>
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
                                        maxWidth: "100%",
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
                    <ThemeToggle />
                </Toolbar>
            </AppBar>

            {isMobile ? (
                <Drawer
                    open={drawerOpen}
                    onClose={() => setDrawerOpen(false)}
                    ModalProps={{ keepMounted: true }}
                    sx={{ "& .MuiDrawer-paper": { width: DRAWER_WIDTH } }}
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
                            transition: theme.transitions.create("width", {
                                duration: theme.transitions.duration.shorter,
                            }),
                        },
                    }}
                >
                    {drawerContent}
                </Drawer>
            )}

            <Box
                component="main"
                sx={{
                    minHeight: "100vh",
                    ml: { md: `${desktopDrawerWidth}px` },
                    pt: { xs: "72px", md: "80px" },
                    transition: theme.transitions.create("margin-left", {
                        duration: theme.transitions.duration.shorter,
                    }),
                }}
            >
                <Outlet />
            </Box>

            <CommandPalette
                open={commandPaletteOpen}
                onClose={() => setCommandPaletteOpen(false)}
                routes={commandRoutes}
                onNavigate={handleNavigate}
            />
        </Box>
    );
}
