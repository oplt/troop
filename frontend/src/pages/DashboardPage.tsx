import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
    Alert,
    Box,
    Button,
    Chip,
    Divider,
    MenuItem,
    Paper,
    Skeleton,
    Stack,
    TextField,
    Typography,
} from "@mui/material";
import {
    DoneAll as DoneAllIcon,
    FolderOpen as ProjectsIcon,
    MailOutline as MailOutlineIcon,
    Notifications as NotificationsIcon,
    NotificationsActive as NotificationsActiveIcon,
    PlayCircleOutline as RunsIcon,
    PendingActions as ApprovalsIcon,
    SmartToy as AgentsIcon,
} from "@mui/icons-material";
import { alpha } from "@mui/material/styles";
import { useNavigate } from "react-router-dom";
import {
    getExecutionInsights,
    getOrchestrationOverview,
    listOrchestrationProjects,
} from "../api/orchestration";
import { getNotifications, markAllRead, markRead } from "../api/notifications";
import { DashboardCalendar } from "../components/dashboard/DashboardCalendar";
import { PageShell } from "../components/ui/PageShell";
import { CollapsibleSectionCard } from "../components/ui/CollapsibleSectionCard";
import { StatCard } from "../components/ui/StatCard";
import { EmptyState } from "../components/ui/EmptyState";
import { formatDateTime, humanizeKey } from "../utils/formatters";

export default function DashboardPage() {
    const navigate = useNavigate();
    const queryClient = useQueryClient();
    const { data: projects, isLoading: projectsLoading } = useQuery({
        queryKey: ["orchestration", "projects"],
        queryFn: listOrchestrationProjects,
    });
    const { data: notifications, isLoading: notificationsLoading, error: notificationsError } = useQuery({
        queryKey: ["notifications"],
        queryFn: getNotifications,
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

    const canonicalProjectLabel = "Agent Projects";
    const canonicalProjectLower = canonicalProjectLabel.toLowerCase();
    const unreadCount = notifications?.filter((item) => !item.is_read).length ?? 0;
    const totalNotifications = notifications?.length ?? 0;
    const visibleNotifications = useMemo(
        () => notifications?.slice(0, 20) ?? [],
        [notifications]
    );
    const visibleProjects = useMemo(
        () => projects?.slice(0, 3) ?? [],
        [projects]
    );
    const eventRows = useMemo(() => executionInsights?.by_event_type ?? [], [executionInsights]);
    const toolFailures = useMemo(
        () => executionInsights?.tool_failures_by_tool ?? [],
        [executionInsights]
    );
    return (
        <PageShell maxWidth="xl">
            <Paper
                sx={(theme) => ({
                    p: { xs: 2.5, md: 4 },
                    borderRadius: 2,
                    overflow: "hidden",
                    position: "relative",
                    border: `1px solid ${theme.palette.divider}`,
                    backgroundColor: theme.palette.background.paper,
                })}
            >
                <Stack
                    direction={{ xs: "column", md: "row" }}
                    spacing={{ xs: 2.5, md: 4 }}
                    alignItems={{ xs: "flex-start", md: "center" }}
                    justifyContent="space-between"
                >
                    <Box sx={{ maxWidth: 760 }}>
                        <Typography variant="overline" color="text.secondary">
                            Workspace
                        </Typography>
                        <Typography variant="h2" sx={{ mt: 0.5 }}>
                            Command current work without losing context.
                        </Typography>
                        <Typography color="text.secondary" sx={{ mt: 1.5, maxWidth: 660 }}>
                            Projects, approvals, runs, and notifications stay visible so next action is clear.
                        </Typography>
                    </Box>
                    <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ width: { xs: "100%", md: "auto" } }}>
                        <Button variant="contained" onClick={() => navigate("/agent-projects")}>
                            Open projects
                        </Button>
                        <Button variant="outlined" onClick={() => navigate("/activity")}>
                            Review activity
                        </Button>
                    </Stack>
                </Stack>
            </Paper>

            <Box
                sx={{
                    display: "grid",
                    gap: 2,
                    gridTemplateColumns: {
                        xs: "repeat(2, minmax(0, 1fr))",
                        sm: "repeat(3, minmax(0, 1fr))",
                        lg: "repeat(5, minmax(0, 1fr))",
                    },
                }}
            >
                <StatCard
                    label={canonicalProjectLabel}
                    value={projects?.length ?? 0}
                    icon={<ProjectsIcon />}
                    loading={projectsLoading}
                    info="Where goals, tasks, repos, and approvals live."
                />
                <StatCard
                    label="Active runs"
                    value={orchestrationOverview?.active_runs.length ?? 0}
                    icon={<RunsIcon />}
                    loading={orchestrationLoading}
                    color="secondary"
                    info="Runs queued or in progress."
                />
                <StatCard
                    label="Pending approvals"
                    value={orchestrationOverview?.pending_approvals.length ?? 0}
                    icon={<ApprovalsIcon />}
                    loading={orchestrationLoading}
                    color="warning"
                    info="Actions waiting for your approval."
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
                    label="Agents"
                    value={orchestrationOverview?.agents.length ?? 0}
                    icon={<AgentsIcon />}
                    loading={orchestrationLoading}
                    color="primary"
                    info="Agents across all projects."
                />
            </Box>

            <Box
                sx={{
                    display: "grid",
                    gap: 3,
                    gridTemplateColumns: {
                        xs: "1fr",
                        md: "repeat(2, minmax(0, 1fr))",
                        lg: "repeat(12, minmax(0, 1fr))",
                    },
                    alignItems: "start",
                }}
            >
                <CollapsibleSectionCard
                    sx={{ gridColumn: { lg: "span 8" } }}
                    title="Calendar"
                    info="Upcoming project dates and workspace schedule."
                    defaultExpanded
                >
                    <DashboardCalendar
                        allowedViews={["month"]}
                        initialView="month"
                    />
                </CollapsibleSectionCard>

                <CollapsibleSectionCard
                    sx={{ gridColumn: { lg: "span 4" }, gridRow: { lg: "span 2" } }}
                    title="Recent notifications"
                    info="Most recent notification history. Mark individual items or all as read."
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
                    </Stack>
                    {notificationsError && (
                        <Alert severity="error" sx={{ mb: 2 }}>
                            {notificationsError.message || "Couldn't load notifications. Refresh to retry."}
                        </Alert>
                    )}
                    {notificationsLoading ? (
                        <Stack spacing={1.5}>
                            {Array.from({ length: 5 }).map((_, index) => (
                                <Skeleton key={index} variant="rounded" height={102} sx={{ borderRadius: 2 }} />
                            ))}
                        </Stack>
                    ) : visibleNotifications.length > 0 ? (
                        <Stack spacing={1.5}>
                            {visibleNotifications.map((notification) => {
                                const isUpdatingThisItem =
                                    markOneMutation.isPending &&
                                    markOneMutation.variables === notification.id;
                                return (
                                    <Box
                                        key={notification.id}
                                        sx={(theme) => ({
                                            p: 2.25,
                                            borderRadius: 2,
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
                            description="New updates and account events will land here."
                        />
                    )}
                </CollapsibleSectionCard>

                <CollapsibleSectionCard
                    sx={{ gridColumn: { lg: "span 8" } }}
                    title="Run activity"
                    info="Run events across projects: tool failures, fallbacks, model responses."
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
                                <Typography variant="body2" color="text.secondary">Loading run events…</Typography>
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
                                Run health
                            </Typography>
                            {insightsLoading || !executionInsights ? (
                                <Typography variant="body2" color="text.secondary">Loading run health…</Typography>
                            ) : (
                                <Stack spacing={1.5}>
                                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                                        <Chip label={`Tasks reopened: ${executionInsights.reopen_events}`} size="small" variant="outlined" />
                                        <Chip label={`Tasks blocked: ${executionInsights.blocked_events}`} size="small" variant="outlined" />
                                        <Chip label={`Tool failures: ${executionInsights.tool_call_failed_events}`} size="small" variant="outlined" />
                                        <Chip label={`Brainstorm rounds: ${executionInsights.brainstorm_round_summary_events}`} size="small" variant="outlined" />
                                    </Stack>
                                    <Divider />
                                    <Typography variant="subtitle2">Failures by tool</Typography>
                                    {toolFailures.length === 0 ? (
                                        <Typography variant="body2" color="text.secondary">
                                            No tool failures in this window.
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
                    sx={{ gridColumn: { lg: "span 4" } }}
                    title="Orchestration"
                    info="Projects, runs, approvals, and GitHub activity from the execution workspace."
                    action={
                        <Button size="small" variant="text" onClick={() => navigate("/agent-projects")}>
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
                                    borderRadius: 2,
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

                {/*
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
                                        borderRadius: 2,
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
                */}

                <CollapsibleSectionCard
                    sx={{ gridColumn: { lg: "span 4" } }}
                    title={`${canonicalProjectLabel} snapshot`}
                    info={`Most recent ${canonicalProjectLower} in your workspace. Click Open ${canonicalProjectLabel} for the full list.`}
                    count={projects?.length ?? 0}
                >
                    {projectsLoading ? (
                        <Stack spacing={1.25}>
                            {Array.from({ length: 3 }).map((_, index) => (
                                <Skeleton key={index} variant="rounded" height={72} sx={{ borderRadius: 2 }} />
                            ))}
                        </Stack>
                    ) : projects && projects.length > 0 ? (
                        <Stack spacing={1.25}>
                            {visibleProjects.map((project) => (
                                <Box
                                    key={project.id}
                                    sx={(theme) => ({
                                        p: 2,
                                        borderRadius: 2,
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
                            title={`No ${canonicalProjectLower} yet`}
                            description="Create your first project to begin."
                            action={
                                <Button variant="contained" onClick={() => navigate("/agent-projects")}>
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
