import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
    Alert,
    Box,
    Button,
    Chip,
    Divider,
    FormControlLabel,
    MenuItem,
    Paper,
    Skeleton,
    Stack,
    Switch,
    TextField,
    Tooltip,
    Typography,
} from "@mui/material";
import {
    ArrowForward as ArrowForwardIcon,
    Campaign as CampaignIcon,
    DoneAll as DoneAllIcon,
    FolderOpen as ProjectsIcon,
    MailOutline as MailOutlineIcon,
    Notifications as NotificationsIcon,
    NotificationsActive as NotificationsActiveIcon,
    PlayCircleOutline as RunsIcon,
    PendingActions as ApprovalsIcon,
    SmartToy as AgentsIcon,
    Security as SecurityIcon,
    VerifiedUser as VerifiedUserIcon,
} from "@mui/icons-material";
import { alpha } from "@mui/material/styles";
import { useNavigate } from "react-router-dom";
import {
    getExecutionInsights,
    getOrchestrationOverview,
    listOrchestrationProjects,
} from "../api/orchestration";
import {
    getNotifications,
    getPreferences,
    markAllRead,
    markRead,
    updatePreferences,
} from "../api/notifications";
import { getMe } from "../api/users";
import { DashboardCalendar } from "../components/dashboard/DashboardCalendar";
import { PageHeader } from "../components/ui/PageHeader";
import { PageShell } from "../components/ui/PageShell";
import { CollapsibleSectionCard } from "../components/ui/CollapsibleSectionCard";
import { StatCard } from "../components/ui/StatCard";
import { EmptyState } from "../components/ui/EmptyState";
import { usePlatformMetadata } from "../hooks/usePlatformMetadata";
import { formatDateTime, getFirstName, humanizeKey } from "../utils/formatters";

function PreferenceItem({
    label,
    description,
    checked,
    disabled,
    onChange,
}: {
    label: string;
    description: string;
    checked: boolean;
    disabled: boolean;
    onChange: (nextValue: boolean) => void;
}) {
    return (
        <Box
            sx={(theme) => ({
                p: 2,
                borderRadius: 4,
                border: `1px solid ${theme.palette.divider}`,
                backgroundColor: theme.palette.background.paper,
            })}
        >
            <FormControlLabel
                sx={{ alignItems: "flex-start", m: 0, width: "100%" }}
                control={
                    <Switch
                        checked={checked}
                        onChange={(event) => onChange(event.target.checked)}
                        disabled={disabled}
                    />
                }
                label={
                    <Box sx={{ ml: 1 }}>
                        <Typography variant="subtitle2">{label}</Typography>
                        <Typography variant="body2" color="text.secondary">
                            {description}
                        </Typography>
                    </Box>
                }
            />
        </Box>
    );
}

export default function DashboardPage() {
    const navigate = useNavigate();
    const queryClient = useQueryClient();
    const { data: platformMetadata } = usePlatformMetadata();
    const { data: user, isLoading: userLoading } = useQuery({
        queryKey: ["me"],
        queryFn: getMe,
    });
    const { data: projects, isLoading: projectsLoading } = useQuery({
        queryKey: ["projects"],
        queryFn: listOrchestrationProjects,
    });
    const { data: notifications, isLoading: notificationsLoading, error: notificationsError } = useQuery({
        queryKey: ["notifications"],
        queryFn: getNotifications,
    });
    const { data: prefs } = useQuery({
        queryKey: ["notification-preferences"],
        queryFn: getPreferences,
    });
    const { data: orchestrationOverview, isLoading: orchestrationLoading } = useQuery({
        queryKey: ["orchestration", "overview"],
        queryFn: getOrchestrationOverview,
    });

    const [signalDays, setSignalDays] = useState(7);
    const { data: executionInsights, isLoading: insightsLoading } = useQuery({
        queryKey: ["orchestration", "execution-insights", signalDays],
        queryFn: () => getExecutionInsights(signalDays),
    });

    const markOneMutation = useMutation({
        mutationFn: markRead,
        onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["notifications"] }),
    });
    const markAllMutation = useMutation({
        mutationFn: markAllRead,
        onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["notifications"] }),
    });
    const prefsMutation = useMutation({
        mutationFn: updatePreferences,
        onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["notification-preferences"] }),
    });

    const coreDomainPlural = platformMetadata?.core_domain_plural ?? "Projects";
    const coreDomainLower = coreDomainPlural.toLowerCase();
    const firstName = getFirstName(user?.full_name) || "there";
    const unreadCount = notifications?.filter((item) => !item.is_read).length ?? 0;
    const totalNotifications = notifications?.length ?? 0;
    const enabledChannels = [
        prefs?.email_enabled,
        prefs?.push_enabled,
        prefs?.marketing_enabled,
    ].filter(Boolean).length;
    const recentNotifications = notifications?.slice(0, 5) ?? [];
    const eventRows = useMemo(() => executionInsights?.by_event_type ?? [], [executionInsights]);
    const toolFailures = useMemo(
        () => executionInsights?.tool_failures_by_tool ?? [],
        [executionInsights]
    );
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
                    <Button variant="contained" endIcon={<ArrowForwardIcon />} onClick={() => navigate("/projects")}>
                        Open {coreDomainPlural}
                    </Button>
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
                    gap: 1.25,
                    gridTemplateColumns: {
                        xs: "repeat(2, minmax(0, 1fr))",
                        sm: "repeat(4, minmax(0, 1fr))",
                        lg: "repeat(8, minmax(0, 1fr))",
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
                    gridTemplateColumns: { xs: "1fr", md: "repeat(2, minmax(0, 1fr))" },
                    alignItems: "start",
                }}
            >
                <CollapsibleSectionCard
                    title="Recent activity"
                    info="Latest notifications and alerts from across your workspace."
                    defaultExpanded
                    count={recentNotifications.length}
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
                </CollapsibleSectionCard>

                <CollapsibleSectionCard
                    title="Inbox"
                    info="Full notification history. Mark individual items or all as read."
                    count={totalNotifications}
                    action={
                        unreadCount > 0 ? (
                            <Button
                                size="small"
                                variant="contained"
                                startIcon={<DoneAllIcon />}
                                disabled={markAllMutation.isPending}
                                onClick={() => markAllMutation.mutate()}
                            >
                                {markAllMutation.isPending ? "Updating..." : "Mark all read"}
                            </Button>
                        ) : undefined
                    }
                >
                    <Stack
                        direction={{ xs: "column", sm: "row" }}
                        spacing={1}
                        sx={{ mb: 2 }}
                    >
                        <Chip
                            icon={<NotificationsActiveIcon />}
                            label={`${unreadCount} unread`}
                            color={unreadCount > 0 ? "primary" : "default"}
                            variant="outlined"
                        />
                        <Chip icon={<MailOutlineIcon />} label={`${totalNotifications} total`} variant="outlined" />
                        <Chip icon={<CampaignIcon />} label={`${enabledChannels}/3 channels`} color="success" variant="outlined" />
                    </Stack>
                    {notificationsError && (
                        <Alert severity="error" sx={{ mb: 2 }}>
                            {notificationsError.message || "Couldn't load notifications. Refresh to retry."}
                        </Alert>
                    )}
                    {notificationsLoading ? (
                        <Stack spacing={1.5}>
                            {Array.from({ length: 5 }).map((_, index) => (
                                <Skeleton key={index} variant="rounded" height={102} sx={{ borderRadius: 4 }} />
                            ))}
                        </Stack>
                    ) : notifications && notifications.length > 0 ? (
                        <Stack spacing={1.5}>
                            {notifications.map((notification) => {
                                const isUpdatingThisItem =
                                    markOneMutation.isPending &&
                                    markOneMutation.variables === notification.id;
                                return (
                                    <Box
                                        key={notification.id}
                                        sx={(theme) => ({
                                            p: 2.25,
                                            borderRadius: 4,
                                            border: `1px solid ${theme.palette.divider}`,
                                            backgroundColor: notification.is_read
                                                ? alpha(theme.palette.background.paper, 0.68)
                                                : alpha(theme.palette.primary.main, theme.palette.mode === "dark" ? 0.16 : 0.06),
                                        })}
                                    >
                                        <Stack spacing={1.25}>
                                            <Stack
                                                direction={{ xs: "column", sm: "row" }}
                                                justifyContent="space-between"
                                                spacing={1.5}
                                            >
                                                <Box>
                                                    <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                                                        <Typography variant="subtitle2">{notification.title}</Typography>
                                                        <Chip label={humanizeKey(notification.type)} size="small" variant="outlined" />
                                                        {!notification.is_read && <Chip label="New" size="small" color="primary" />}
                                                    </Stack>
                                                </Box>
                                                <Typography variant="caption" color="text.secondary">
                                                    {formatDateTime(notification.created_at)}
                                                </Typography>
                                            </Stack>
                                            {notification.body && (
                                                <Typography variant="body2" color="text.secondary">
                                                    {notification.body}
                                                </Typography>
                                            )}
                                            {!notification.is_read && (
                                                <Box>
                                                    <Button
                                                        size="small"
                                                        variant="outlined"
                                                        disabled={isUpdatingThisItem}
                                                        onClick={() => markOneMutation.mutate(notification.id)}
                                                    >
                                                        {isUpdatingThisItem ? "Saving..." : "Mark as read"}
                                                    </Button>
                                                </Box>
                                            )}
                                        </Stack>
                                    </Box>
                                );
                            })}
                        </Stack>
                    ) : (
                        <EmptyState
                            icon={<NotificationsActiveIcon />}
                            title="Inbox is clear"
                            description="You have no notifications yet. New product updates and account events will appear here."
                        />
                    )}
                </CollapsibleSectionCard>

                <CollapsibleSectionCard
                    title="Delivery preferences"
                    info="Choose how you want this workspace to reach you."
                >
                    <Stack spacing={1.5}>
                        <PreferenceItem
                            label="Email notifications"
                            description="Receive operational updates and account messages in your inbox."
                            checked={prefs?.email_enabled ?? true}
                            disabled={prefsMutation.isPending}
                            onChange={(nextValue) => prefsMutation.mutate({ email_enabled: nextValue })}
                        />
                        <PreferenceItem
                            label="Push notifications"
                            description="Surface urgent activity directly inside the app experience."
                            checked={prefs?.push_enabled ?? true}
                            disabled={prefsMutation.isPending}
                            onChange={(nextValue) => prefsMutation.mutate({ push_enabled: nextValue })}
                        />
                        <PreferenceItem
                            label="Marketing emails"
                            description="Get launch announcements, feature roundups, and educational updates."
                            checked={prefs?.marketing_enabled ?? false}
                            disabled={prefsMutation.isPending}
                            onChange={(nextValue) => prefsMutation.mutate({ marketing_enabled: nextValue })}
                        />
                    </Stack>
                </CollapsibleSectionCard>

                <CollapsibleSectionCard
                    title="Run signals"
                    info="Aggregated run-event telemetry across orchestration projects (tool failures, fallbacks, LLM responses, etc.)."
                    action={
                        <TextField
                            select
                            label="Window"
                            size="small"
                            value={signalDays}
                            onChange={(e) => setSignalDays(Number(e.target.value))}
                            sx={{ minWidth: 160 }}
                            onClick={(e) => e.stopPropagation()}
                        >
                            <MenuItem value={7}>Last 7 days</MenuItem>
                            <MenuItem value={14}>Last 14 days</MenuItem>
                            <MenuItem value={30}>Last 30 days</MenuItem>
                        </TextField>
                    }
                >
                    <Stack spacing={2}>
                        {executionInsights?.since && (
                            <Typography variant="body2" color="text.secondary">
                                Since {formatDateTime(executionInsights.since)}
                            </Typography>
                        )}
                        <Box>
                            <Typography variant="subtitle2" sx={{ mb: 1 }}>
                                Events by type
                            </Typography>
                            {insightsLoading ? (
                                <Typography variant="body2" color="text.secondary">Loading…</Typography>
                            ) : eventRows.length === 0 ? (
                                <Typography variant="body2" color="text.secondary">
                                    No run events in this window.
                                </Typography>
                            ) : (
                                <Stack spacing={1}>
                                    {eventRows.map((row) => (
                                        <Paper key={row.event_type} variant="outlined" sx={{ p: 1.5, borderRadius: 2 }}>
                                            <Stack direction="row" justifyContent="space-between" alignItems="center">
                                                <Typography variant="subtitle2" sx={{ fontFamily: "IBM Plex Mono, monospace" }}>
                                                    {row.event_type}
                                                </Typography>
                                                <Typography variant="h6">{row.count}</Typography>
                                            </Stack>
                                        </Paper>
                                    ))}
                                </Stack>
                            )}
                        </Box>
                        <Divider />
                        <Box>
                            <Typography variant="subtitle2" sx={{ mb: 1 }}>
                                Quality heuristics
                            </Typography>
                            {insightsLoading || !executionInsights ? (
                                <Typography variant="body2" color="text.secondary">Loading…</Typography>
                            ) : (
                                <Stack spacing={1.5}>
                                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                                        <Chip label={`Reopens: ${executionInsights.reopen_events}`} size="small" variant="outlined" />
                                        <Chip label={`Blocked: ${executionInsights.blocked_events}`} size="small" variant="outlined" />
                                        <Chip label={`Tool failures: ${executionInsights.tool_call_failed_events}`} size="small" variant="outlined" />
                                        <Chip label={`Brainstorm summaries: ${executionInsights.brainstorm_round_summary_events}`} size="small" variant="outlined" />
                                    </Stack>
                                    <Divider />
                                    <Typography variant="subtitle2">Tool failures by tool name</Typography>
                                    {toolFailures.length === 0 ? (
                                        <Typography variant="body2" color="text.secondary">
                                            No tool_call_failed events in this window.
                                        </Typography>
                                    ) : (
                                        <Stack spacing={1}>
                                            {toolFailures.map((row) => (
                                                <Paper key={row.tool} variant="outlined" sx={{ p: 1.5, borderRadius: 2 }}>
                                                    <Stack direction="row" justifyContent="space-between" alignItems="center">
                                                        <Typography variant="subtitle2" sx={{ fontFamily: "IBM Plex Mono, monospace" }}>
                                                            {row.tool}
                                                        </Typography>
                                                        <Typography variant="h6">{row.count}</Typography>
                                                    </Stack>
                                                </Paper>
                                            ))}
                                        </Stack>
                                    )}
                                </Stack>
                            )}
                        </Box>
                    </Stack>
                </CollapsibleSectionCard>

                <CollapsibleSectionCard
                    title="Orchestration"
                    info="Projects, runs, approvals, and GitHub activity from the execution workspace."
                    action={
                        <Button size="small" variant="text" onClick={() => navigate("/projects")}>
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
                </CollapsibleSectionCard>

                <CollapsibleSectionCard
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
                </CollapsibleSectionCard>

                <CollapsibleSectionCard
                    title="Calendar"
                    info={`Upcoming ${coreDomainLower} dates and workspace schedule.`}
                >
                    <DashboardCalendar
                        projects={projects ?? []}
                        projectsLoading={projectsLoading}
                        onOpenProjects={() => navigate("/projects")}
                        allowedViews={["month"]}
                        initialView="month"
                    />
                </CollapsibleSectionCard>

                <CollapsibleSectionCard
                    title={`${coreDomainPlural} snapshot`}
                    info={`Most recent ${coreDomainLower} in your workspace. Click Open ${coreDomainPlural} for the full list.`}
                    count={projects?.length ?? 0}
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
                </CollapsibleSectionCard>
            </Box>
        </PageShell>
    );
}
