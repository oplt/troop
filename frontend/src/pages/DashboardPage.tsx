import { useQuery } from "@tanstack/react-query";
import {
    Box,
    Button,
    Chip,
    Skeleton,
    Stack,
    Tooltip,
    Typography,
} from "@mui/material";
import {
    ArrowForward as ArrowForwardIcon,
    FolderOpen as ProjectsIcon,
    Notifications as NotificationsIcon,
    PlayCircleOutline as RunsIcon,
    PendingActions as ApprovalsIcon,
    SmartToy as AgentsIcon,
    Security as SecurityIcon,
    VerifiedUser as VerifiedUserIcon,
} from "@mui/icons-material";
import { alpha } from "@mui/material/styles";
import { useNavigate } from "react-router-dom";
import { getOrchestrationOverview, listOrchestrationProjects } from "../api/orchestration";
import { getNotifications } from "../api/notifications";
import { getMe } from "../api/users";
import { DashboardCalendar } from "../components/dashboard/DashboardCalendar";
import { PageHeader } from "../components/ui/PageHeader";
import { PageShell } from "../components/ui/PageShell";
import { SectionCard } from "../components/ui/SectionCard";
import { StatCard } from "../components/ui/StatCard";
import { EmptyState } from "../components/ui/EmptyState";
import { usePlatformMetadata } from "../hooks/usePlatformMetadata";
import { formatDateTime, getFirstName } from "../utils/formatters";

export default function DashboardPage() {
    const navigate = useNavigate();
    const { data: platformMetadata } = usePlatformMetadata();
    const { data: user, isLoading: userLoading } = useQuery({
        queryKey: ["me"],
        queryFn: getMe,
    });
    const { data: projects, isLoading: projectsLoading } = useQuery({
        queryKey: ["projects"],
        queryFn: listOrchestrationProjects,
    });
    const { data: notifications, isLoading: notificationsLoading } = useQuery({
        queryKey: ["notifications"],
        queryFn: getNotifications,
    });
    const { data: orchestrationOverview, isLoading: orchestrationLoading } = useQuery({
        queryKey: ["orchestration", "overview"],
        queryFn: getOrchestrationOverview,
    });

    const coreDomainPlural = platformMetadata?.core_domain_plural ?? "Projects";
    const coreDomainLower = coreDomainPlural.toLowerCase();
    const firstName = getFirstName(user?.full_name) || "there";
    const unreadCount = notifications?.filter((item) => !item.is_read).length ?? 0;
    const recentNotifications = notifications?.slice(0, 5) ?? [];
    const accountChecks = [
        {
            label: "Email verified",
            value: user?.is_verified ? "Verified" : "Pending",
            color: user?.is_verified ? "success.main" : "warning.main",
            tooltip: user?.is_verified
                ? "Sign-in identity confirmed."
                : "Verify email to unlock recovery and trust signals.",
        },
        {
            label: "Multi-factor auth",
            value: user?.mfa_enabled ? "Enabled" : "Off",
            color: user?.mfa_enabled ? "success.main" : "warning.main",
            tooltip: user?.mfa_enabled
                ? "Extra sign-in layer active."
                : "Enable MFA to reduce account takeover risk.",
        },
    ];

    return (
        <PageShell maxWidth="xl">
            <PageHeader
                eyebrow="Overview"
                title={`Welcome back, ${firstName}`}
                description={`Your ${coreDomainLower}, agents, and signals at a glance.`}
                actions={
                    <>
                        <Button variant="contained" endIcon={<ArrowForwardIcon />} onClick={() => navigate("/projects")}>
                            Open {coreDomainPlural}
                        </Button>
                        <Button variant="outlined" onClick={() => navigate("/notifications")}>
                            Inbox
                        </Button>
                    </>
                }
                meta={
                    <>
                        <Chip
                            label={
                                platformMetadata?.module_pack
                                    ? `Pack · ${platformMetadata.module_pack}`
                                    : "Standard workspace"
                            }
                            variant="outlined"
                            size="small"
                        />
                        <Chip
                            label={
                                userLoading
                                    ? "Checking security"
                                    : user?.is_verified && user?.mfa_enabled
                                        ? "Account secure"
                                        : "Security pending"
                            }
                            color={user?.is_verified && user?.mfa_enabled ? "success" : "warning"}
                            variant="outlined"
                            size="small"
                        />
                    </>
                }
            />

            <Box
                sx={{
                    display: "grid",
                    gap: 2,
                    gridTemplateColumns: {
                        xs: "1fr",
                        sm: "repeat(2, minmax(0, 1fr))",
                        lg: "repeat(4, minmax(0, 1fr))",
                    },
                }}
            >
                <StatCard
                    label={coreDomainPlural}
                    value={projects?.length ?? 0}
                    icon={<ProjectsIcon />}
                    loading={projectsLoading}
                    info={`Total ${coreDomainLower} in your workspace. Includes active, paused, and archived.`}
                />
                <StatCard
                    label="Agent projects"
                    value={orchestrationOverview?.projects.length ?? 0}
                    icon={<AgentsIcon />}
                    loading={orchestrationLoading}
                    color="info"
                    info="Execution workspaces running agents and durable tasks."
                />
                <StatCard
                    label="Active runs"
                    value={orchestrationOverview?.active_runs.length ?? 0}
                    icon={<RunsIcon />}
                    loading={orchestrationLoading}
                    color="secondary"
                    info="Orchestration runs currently queued or in progress."
                />
                <StatCard
                    label="Pending approvals"
                    value={orchestrationOverview?.pending_approvals.length ?? 0}
                    icon={<ApprovalsIcon />}
                    loading={orchestrationLoading}
                    color="warning"
                    info="Human decisions gating external actions."
                />
                <StatCard
                    label="Unread inbox"
                    value={unreadCount}
                    icon={<NotificationsIcon />}
                    loading={notificationsLoading}
                    color="warning"
                    info="New updates and alerts waiting for review."
                />
                <StatCard
                    label="Email"
                    value={user?.is_verified ? "Verified" : "Pending"}
                    icon={<VerifiedUserIcon />}
                    loading={userLoading}
                    color={user?.is_verified ? "success" : "warning"}
                    info="Identity confirmation status for your account."
                />
                <StatCard
                    label="MFA"
                    value={user?.mfa_enabled ? "On" : "Off"}
                    icon={<SecurityIcon />}
                    loading={userLoading}
                    color={user?.mfa_enabled ? "success" : "secondary"}
                    info="Multi-factor authentication protects sign-in against stolen passwords."
                />
                <StatCard
                    label="Agents"
                    value={orchestrationOverview?.agents.length ?? 0}
                    icon={<AgentsIcon />}
                    loading={orchestrationLoading}
                    color="primary"
                    info="Deployed agents across all orchestration projects."
                />
            </Box>

            <Box
                sx={{
                    display: "grid",
                    gap: 2,
                    gridTemplateColumns: { xs: "1fr", lg: "minmax(0, 1.25fr) minmax(320px, 0.9fr)" },
                }}
            >
                <SectionCard
                    title="Recent activity"
                    info="Latest notifications and alerts from across your workspace."
                    action={
                        <Button variant="text" onClick={() => navigate("/notifications")}>
                            Open all
                        </Button>
                    }
                >
                    {notificationsLoading ? (
                        <Stack spacing={1.5}>
                            {Array.from({ length: 4 }).map((_, index) => (
                                <Skeleton key={index} variant="rounded" height={92} sx={{ borderRadius: 3 }} />
                            ))}
                        </Stack>
                    ) : recentNotifications.length === 0 ? (
                        <EmptyState
                            icon={<NotificationsIcon />}
                            title="No notifications yet"
                            description="Updates and account events appear here as workspace activity begins."
                            action={
                                <Button variant="outlined" onClick={() => navigate("/projects")}>
                                    Explore workspace
                                </Button>
                            }
                        />
                    ) : (
                        <Stack spacing={1.25}>
                            {recentNotifications.map((notification) => (
                                <Box
                                    key={notification.id}
                                    sx={(theme) => ({
                                        border: `1px solid ${theme.palette.divider}`,
                                        borderRadius: 3,
                                        px: 2,
                                        py: 1.75,
                                        backgroundColor: notification.is_read
                                            ? "transparent"
                                            : alpha(theme.palette.primary.main, theme.palette.mode === "dark" ? 0.12 : 0.05),
                                    })}
                                >
                                    <Stack
                                        direction={{ xs: "column", sm: "row" }}
                                        justifyContent="space-between"
                                        spacing={1}
                                    >
                                        <Box sx={{ minWidth: 0 }}>
                                            <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.5 }}>
                                                <Typography variant="subtitle2">{notification.title}</Typography>
                                                {!notification.is_read && <Chip label="New" size="small" color="primary" />}
                                            </Stack>
                                            {notification.body && (
                                                <Typography variant="body2" color="text.secondary">
                                                    {notification.body}
                                                </Typography>
                                            )}
                                        </Box>
                                        <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: "nowrap" }}>
                                            {formatDateTime(notification.created_at)}
                                        </Typography>
                                    </Stack>
                                </Box>
                            ))}
                        </Stack>
                    )}
                </SectionCard>

                <Stack spacing={2}>
                    <SectionCard
                        title="Orchestration"
                        info="Projects, runs, approvals, and GitHub activity from the execution workspace."
                        action={
                            <Button variant="text" onClick={() => navigate("/projects")}>
                                Open
                            </Button>
                        }
                    >
                        <Stack spacing={1.25}>
                            <Typography variant="body2" color="text.secondary">
                                {orchestrationLoading
                                    ? "Loading status…"
                                    : `${orchestrationOverview?.agents.length ?? 0} agents · ${orchestrationOverview?.projects.length ?? 0} projects`}
                            </Typography>
                            {(orchestrationOverview?.active_runs ?? []).slice(0, 3).map((run) => (
                                <Box
                                    key={run.id}
                                    sx={(theme) => ({
                                        p: 1.5,
                                        borderRadius: 3,
                                        border: `1px solid ${theme.palette.divider}`,
                                    })}
                                >
                                    <Typography variant="subtitle2" sx={{ textTransform: "capitalize" }}>
                                        {run.run_mode.replaceAll("_", " ")} · {run.status.replaceAll("_", " ")}
                                    </Typography>
                                    <Typography variant="caption" color="text.secondary">
                                        {formatDateTime(run.created_at)}
                                    </Typography>
                                </Box>
                            ))}
                        </Stack>
                    </SectionCard>

                    <SectionCard
                        title="Account health"
                        info="Trust and security posture of your account. Hover each item for remediation guidance."
                    >
                        <Stack spacing={1.25}>
                            {accountChecks.map((item) => (
                                <Tooltip key={item.label} title={item.tooltip} arrow placement="left">
                                    <Box
                                        sx={(theme) => ({
                                            p: 2,
                                            borderRadius: 3,
                                            border: `1px solid ${theme.palette.divider}`,
                                            backgroundColor: theme.palette.background.paper,
                                            cursor: "help",
                                        })}
                                    >
                                        <Stack direction="row" justifyContent="space-between" spacing={1} alignItems="center">
                                            <Typography variant="subtitle2">{item.label}</Typography>
                                            {userLoading ? (
                                                <Skeleton variant="rounded" width={96} height={28} />
                                            ) : (
                                                <Typography variant="body2" sx={{ color: item.color, fontWeight: 700 }}>
                                                    {item.value}
                                                </Typography>
                                            )}
                                        </Stack>
                                    </Box>
                                </Tooltip>
                            ))}
                        </Stack>
                    </SectionCard>

                    <DashboardCalendar
                        projects={projects ?? []}
                        projectsLoading={projectsLoading}
                        onOpenProjects={() => navigate("/projects")}
                        allowedViews={["month"]}
                        initialView="month"
                    />

                    <SectionCard
                        title={`${coreDomainPlural} snapshot`}
                        info={`Most recent ${coreDomainLower} in your workspace. Click Open ${coreDomainPlural} for the full list.`}
                    >
                        {projectsLoading ? (
                            <Stack spacing={1.25}>
                                {Array.from({ length: 3 }).map((_, index) => (
                                    <Skeleton key={index} variant="rounded" height={72} sx={{ borderRadius: 3 }} />
                                ))}
                            </Stack>
                        ) : projects && projects.length > 0 ? (
                            <Stack spacing={1.25}>
                                {projects.slice(0, 3).map((project) => (
                                    <Box
                                        key={project.id}
                                        sx={(theme) => ({
                                            p: 2,
                                            borderRadius: 3,
                                            border: `1px solid ${theme.palette.divider}`,
                                        })}
                                    >
                                        <Typography variant="subtitle2">{project.name}</Typography>
                                        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                                            {project.description || `No description yet.`}
                                        </Typography>
                                    </Box>
                                ))}
                            </Stack>
                        ) : (
                            <EmptyState
                                icon={<ProjectsIcon />}
                                title={`No ${coreDomainLower} yet`}
                                description={`Create your first ${platformMetadata?.core_domain_singular?.toLowerCase() ?? "project"} to start.`}
                                action={
                                    <Button variant="contained" onClick={() => navigate("/projects")}>
                                        Create
                                    </Button>
                                }
                            />
                        )}
                    </SectionCard>
                </Stack>
            </Box>
        </PageShell>
    );
}
