import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
    Box,
    Button,
    Chip,
    MenuItem,
    Skeleton,
    Stack,
    TextField,
    Typography,
} from "@mui/material";
import {
    Assignment as TasksIcon,
    FolderOpen as ProjectsIcon,
    NotificationsActive as NotificationsActiveIcon,
    PendingActions as ApprovalsIcon,
    PlayCircleOutline as RunsIcon,
} from "@mui/icons-material";
import { alpha } from "@mui/material/styles";
import { useNavigate } from "react-router-dom";
import {
    getExecutionInsights,
    getOrchestrationOverview,
} from "../api/orchestration";
import { getNotifications, markAllRead, markRead } from "../api/notifications";
import { DashboardCalendar } from "../components/dashboard/DashboardCalendar";
import { PageShell } from "../components/ui/PageShell";
import { PageHeader } from "../components/ui/PageHeader";
import { CollapsibleSectionCard } from "../components/ui/CollapsibleSectionCard";
import { SectionCard } from "../components/ui/SectionCard";
import { EmptyState } from "../components/ui/EmptyState";
import { OnboardingChecklist } from "../components/ui/OnboardingChecklist";
import { SectionError } from "../components/ui/SectionError";
import { StatusChip } from "../components/ui/StatusChip";
import { queryKeys } from "../config/queryKeys";
import { queryPolicies } from "../config/queryPolicies";
import { formatDateTime, humanizeKey } from "../utils/formatters";
import { listCompanies } from "../api/companies";
import { getGmailStatus, getTelegramStatus } from "../api/integrations";

type NextAction = {
    id: string;
    title: string;
    detail: string;
    cta: string;
    path: string;
    priority: number;
};

export default function DashboardPage() {
    const navigate = useNavigate();
    const queryClient = useQueryClient();
    const {
        data: orchestrationOverview,
        isLoading: orchestrationLoading,
        isError: orchestrationLoadFailed,
        error: orchestrationError,
        refetch: refetchOrchestration,
        isFetching: orchestrationFetching,
    } = useQuery({
        queryKey: queryKeys.orchestration.overview,
        queryFn: getOrchestrationOverview,
        ...queryPolicies.realtime,
    });
    const projects = orchestrationOverview?.projects;
    const { data: companies = [] } = useQuery({
        queryKey: queryKeys.companies.root,
        queryFn: listCompanies,
        ...queryPolicies.userScoped,
    });
    const { data: gmailStatus } = useQuery({
        queryKey: ["integrations", "gmail-status"],
        queryFn: getGmailStatus,
        retry: false,
        ...queryPolicies.userScoped,
    });
    const { data: telegramStatus } = useQuery({
        queryKey: ["integrations", "telegram-status"],
        queryFn: getTelegramStatus,
        retry: false,
        ...queryPolicies.userScoped,
    });
    const { data: notifications, isLoading: notificationsLoading, error: notificationsError, refetch: refetchNotifications } = useQuery({
        queryKey: queryKeys.notifications.root,
        queryFn: getNotifications,
        ...queryPolicies.operational,
    });

    const [signalDays, setSignalDays] = useState(7);
    const {
        data: executionInsights,
        isLoading: insightsLoading,
        isError: insightsLoadFailed,
        error: insightsError,
        refetch: refetchInsights,
        isFetching: insightsFetching,
    } = useQuery({
        queryKey: queryKeys.orchestration.executionInsights(signalDays),
        queryFn: () => getExecutionInsights(signalDays),
        ...queryPolicies.userScoped,
    });

    const dashboardLoadFailed = orchestrationLoadFailed || insightsLoadFailed;
    const dashboardRetrying = orchestrationFetching || insightsFetching;

    const markOneMutation = useMutation({
        mutationFn: markRead,
        onSuccess: () => void queryClient.invalidateQueries({ queryKey: queryKeys.notifications.root }),
    });
    const markAllMutation = useMutation({
        mutationFn: markAllRead,
        onSuccess: () => void queryClient.invalidateQueries({ queryKey: queryKeys.notifications.root }),
    });

    const pendingApprovals = orchestrationOverview?.pending_approvals ?? [];
    const activeRuns = orchestrationOverview?.active_runs ?? [];
    const unreadCount = notifications?.filter((item) => !item.is_read).length ?? 0;
    const attentionProjects = useMemo(
        () =>
            (projects ?? [])
                .filter((project) => project.status === "active" || project.status === "running")
                .slice(0, 4),
        [projects],
    );

    const nextActions = useMemo<NextAction[]>(() => {
        const items: NextAction[] = [];
        if (pendingApprovals.length > 0) {
            items.push({
                id: "approvals",
                title: `${pendingApprovals.length} approval${pendingApprovals.length === 1 ? "" : "s"} waiting`,
                detail: "Clear the queue so agents and teammates can continue.",
                cta: "Review approvals",
                path: "/approvals",
                priority: 0,
            });
        }
        if (activeRuns.length > 0) {
            const run = activeRuns[0];
            items.push({
                id: "runs",
                title: `${activeRuns.length} active run${activeRuns.length === 1 ? "" : "s"}`,
                detail: `${humanizeKey(run.run_mode)} · ${humanizeKey(run.status)}`,
                cta: "Open run",
                path: `/runs/${run.id}`,
                priority: 1,
            });
        }
        if (attentionProjects.length > 0) {
            const project = attentionProjects[0];
            items.push({
                id: "project",
                title: `Continue ${project.name}`,
                detail: project.description || "Open the board and move the next task.",
                cta: "Open project",
                path: `/projects/${project.id}?tab=board`,
                priority: 2,
            });
        }
        items.push({
            id: "my-tasks",
            title: "Check my tasks",
            detail: "Personal work queue across projects.",
            cta: "My tasks",
            path: "/my-tasks",
            priority: 3,
        });
        return items.sort((a, b) => a.priority - b.priority).slice(0, 3);
    }, [pendingApprovals, activeRuns, attentionProjects]);

    const primaryAction = nextActions[0];
    const visibleNotifications = useMemo(() => notifications?.slice(0, 5) ?? [], [notifications]);
    const hasIntegration =
        Boolean(gmailStatus && ["connected", "active", "healthy"].includes(String(gmailStatus.status))) ||
        Boolean(telegramStatus && ["connected", "active", "healthy", "linked"].includes(String(telegramStatus.status)));
    const showOnboarding = !orchestrationLoading && (projects?.length ?? 0) === 0;
    const onboardingSteps = useMemo(
        () => [
            {
                id: "company",
                label: "Add a company (org context for knowledge)",
                done: companies.length > 0,
                path: "/companies",
                cta: "Open companies",
            },
            {
                id: "project",
                label: "Create your first project",
                done: (projects?.length ?? 0) > 0,
                path: "/projects?create=1",
                cta: "Create project",
            },
            {
                id: "integration",
                label: "Connect an integration (optional)",
                done: hasIntegration,
                path: "/integrations",
                cta: "Connect integration",
            },
        ],
        [companies.length, projects?.length, hasIntegration],
    );

    return (
        <PageShell variant="browse">
            {dashboardLoadFailed && (
                <SectionError
                    error={orchestrationError ?? insightsError}
                    fallback="Couldn't load dashboard data. Check your connection and try again."
                    retrying={dashboardRetrying}
                    onRetry={() => {
                        void refetchOrchestration();
                        void refetchInsights();
                    }}
                />
            )}

            {showOnboarding ? <OnboardingChecklist steps={onboardingSteps} /> : null}

            <PageHeader
                eyebrow="Work"
                title={primaryAction ? primaryAction.title : "You're caught up."}
                description={
                    primaryAction
                        ? primaryAction.detail
                        : "No pending approvals or hot runs. Browse projects when you're ready."
                }
                actions={
                    <>
                        <Button
                            variant="contained"
                            onClick={() => navigate(primaryAction?.path ?? "/projects")}
                        >
                            {primaryAction?.cta ?? "Open projects"}
                        </Button>
                        <Button variant="outlined" onClick={() => navigate("/my-tasks")}>
                            My tasks
                        </Button>
                    </>
                }
            />

            <Box
                sx={{
                    display: "grid",
                    gap: 2,
                    gridTemplateColumns: { xs: "1fr", md: "repeat(3, minmax(0, 1fr))" },
                }}
            >
                <SectionCard
                    title="Do next"
                    info="Highest-priority work across approvals, runs, and projects."
                    density="framed"
                >
                    {orchestrationLoading ? (
                        <Stack spacing={1}>
                            <Skeleton height={56} />
                            <Skeleton height={56} />
                        </Stack>
                    ) : (
                        <Stack spacing={0} sx={{ borderTop: "1px solid", borderColor: "divider" }}>
                            {nextActions.map((item) => (
                                <Stack
                                    key={item.id}
                                    direction={{ xs: "column", sm: "row" }}
                                    justifyContent="space-between"
                                    alignItems={{ sm: "center" }}
                                    spacing={1}
                                    sx={{ py: 1.5, borderBottom: "1px solid", borderColor: "divider" }}
                                >
                                    <Box sx={{ minWidth: 0 }}>
                                        <Typography variant="subtitle2">{item.title}</Typography>
                                        <Typography variant="body2" color="text.secondary">
                                            {item.detail}
                                        </Typography>
                                    </Box>
                                    <Button size="small" variant="outlined" onClick={() => navigate(item.path)}>
                                        {item.cta}
                                    </Button>
                                </Stack>
                            ))}
                        </Stack>
                    )}
                </SectionCard>

                <SectionCard title="Approvals" density="framed">
                    <Stack spacing={1.5}>
                        <Stack direction="row" spacing={1} alignItems="center">
                            <Typography variant="h4" sx={{ fontVariantNumeric: "tabular-nums" }}>
                                {orchestrationLoading ? "…" : pendingApprovals.length}
                            </Typography>
                            {pendingApprovals.length > 0 ? (
                                <StatusChip status="pending" kind="approval" celebrate={false} />
                            ) : null}
                        </Stack>
                        <Typography variant="body2" color="text.secondary">
                            Waiting for your decision.
                        </Typography>
                        <Button
                            variant={pendingApprovals.length > 0 ? "contained" : "outlined"}
                            startIcon={<ApprovalsIcon />}
                            onClick={() => navigate("/approvals")}
                        >
                            {pendingApprovals.length > 0 ? "Review approvals" : "Open approvals"}
                        </Button>
                    </Stack>
                </SectionCard>

                <SectionCard title="Projects" density="framed">
                    <Stack spacing={1.5}>
                        <Typography variant="h4" sx={{ fontVariantNumeric: "tabular-nums" }}>
                            {orchestrationLoading ? "…" : projects?.length ?? 0}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                            {activeRuns.length} active run{activeRuns.length === 1 ? "" : "s"}.
                        </Typography>
                        <Stack direction="row" spacing={1}>
                            <Button variant="outlined" startIcon={<ProjectsIcon />} onClick={() => navigate("/projects")}>
                                Browse
                            </Button>
                            <Button variant="text" startIcon={<TasksIcon />} onClick={() => navigate("/my-tasks")}>
                                My tasks
                            </Button>
                        </Stack>
                    </Stack>
                </SectionCard>
            </Box>

            <Box
                sx={{
                    display: "grid",
                    gap: 3,
                    gridTemplateColumns: { xs: "1fr", lg: "minmax(0, 1.2fr) minmax(0, 0.8fr)" },
                    alignItems: "start",
                }}
            >
                <SectionCard
                    title="Needs attention"
                    density="plain"
                    action={
                        <Button size="small" variant="text" onClick={() => navigate("/projects")}>
                            All projects
                        </Button>
                    }
                >
                    {orchestrationLoading ? (
                        <Skeleton height={120} />
                    ) : attentionProjects.length > 0 ? (
                        <Stack spacing={0} sx={{ borderTop: "1px solid", borderColor: "divider" }}>
                            {attentionProjects.map((project) => (
                                <Stack
                                    key={project.id}
                                    direction={{ xs: "column", sm: "row" }}
                                    justifyContent="space-between"
                                    alignItems={{ sm: "center" }}
                                    spacing={1}
                                    sx={{ py: 1.5, borderBottom: "1px solid", borderColor: "divider" }}
                                >
                                    <Box sx={{ minWidth: 0 }}>
                                        <Stack direction="row" spacing={1} alignItems="center">
                                            <Typography variant="subtitle2" noWrap>
                                                {project.name}
                                            </Typography>
                                            <StatusChip status={project.status} kind="project" />
                                        </Stack>
                                        <Typography variant="body2" color="text.secondary" noWrap>
                                            {project.description || "No description"}
                                        </Typography>
                                    </Box>
                                    <Button
                                        size="small"
                                        variant="outlined"
                                        onClick={() => navigate(`/projects/${project.id}?tab=board`)}
                                    >
                                        Open board
                                    </Button>
                                </Stack>
                            ))}
                        </Stack>
                    ) : (
                        <EmptyState
                            icon={<ProjectsIcon />}
                            title="No projects yet"
                            description="Create a project to start assigning work."
                            action={
                                <Button variant="contained" onClick={() => navigate("/projects?create=1")}>
                                    Create project
                                </Button>
                            }
                        />
                    )}
                </SectionCard>

                <SectionCard
                    title="Inbox"
                    density="plain"
                    action={
                        <Stack direction="row" spacing={1}>
                            <Button size="small" variant="text" onClick={() => navigate("/notifications")}>
                                View all
                            </Button>
                            {unreadCount > 0 && (
                                <Button
                                    size="small"
                                    variant="contained"
                                    disabled={markAllMutation.isPending}
                                    onClick={() => markAllMutation.mutate()}
                                >
                                    Mark all read
                                </Button>
                            )}
                        </Stack>
                    }
                >
                    {notificationsError && (
                        <SectionError
                            error={notificationsError}
                            fallback="Couldn't load notifications."
                            onRetry={() => void refetchNotifications()}
                        />
                    )}
                    {notificationsLoading ? (
                        <Skeleton height={120} />
                    ) : visibleNotifications.length > 0 ? (
                        <Stack spacing={0} sx={{ borderTop: "1px solid", borderColor: "divider" }}>
                            {visibleNotifications.map((notification) => (
                                <Box
                                    key={notification.id}
                                    sx={{
                                        py: 1.25,
                                        borderBottom: "1px solid",
                                        borderColor: "divider",
                                        backgroundColor: notification.is_read
                                            ? "transparent"
                                            : (theme) =>
                                                  alpha(
                                                      theme.palette.primary.main,
                                                      theme.palette.mode === "dark" ? 0.12 : 0.05,
                                                  ),
                                        px: 1,
                                    }}
                                >
                                    <Stack direction="row" justifyContent="space-between" spacing={1}>
                                        <Typography variant="subtitle2">{notification.title}</Typography>
                                        {!notification.is_read && (
                                            <Chip size="small" color="primary" label="New" />
                                        )}
                                    </Stack>
                                    <Typography variant="caption" color="text.secondary">
                                        {formatDateTime(notification.created_at)}
                                    </Typography>
                                    {!notification.is_read && (
                                        <Button
                                            size="small"
                                            sx={{ mt: 0.5 }}
                                            onClick={() => markOneMutation.mutate(notification.id)}
                                        >
                                            Mark read
                                        </Button>
                                    )}
                                </Box>
                            ))}
                        </Stack>
                    ) : (
                        <EmptyState
                            icon={<NotificationsActiveIcon />}
                            title="Inbox clear"
                            description="New updates land here."
                        />
                    )}
                </SectionCard>
            </Box>

            <CollapsibleSectionCard
                title="Schedule & analytics"
                info="Calendar and run-event detail — secondary to the work queue above."
                defaultExpanded={false}
                action={
                    <Button size="small" variant="text" onClick={() => navigate("/analytics/execution")}>
                        Execution insights
                    </Button>
                }
            >
                <Stack spacing={3}>
                    <DashboardCalendar allowedViews={["month"]} initialView="month" />
                    <Box>
                        <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                            <Typography variant="subtitle2">Run activity</Typography>
                            <TextField
                                select
                                size="small"
                                label="Window"
                                value={signalDays}
                                onChange={(e) => setSignalDays(Number(e.target.value))}
                                sx={{ minWidth: 140 }}
                            >
                                <MenuItem value={7}>Last 7 days</MenuItem>
                                <MenuItem value={14}>Last 14 days</MenuItem>
                                <MenuItem value={30}>Last 30 days</MenuItem>
                            </TextField>
                        </Stack>
                        {insightsLoadFailed && (
                            <SectionError
                                error={insightsError}
                                fallback="Couldn't load run activity."
                                onRetry={() => void refetchInsights()}
                            />
                        )}
                        {insightsLoading ? (
                            <Typography variant="body2" color="text.secondary">
                                Loading…
                            </Typography>
                        ) : (
                            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                                <Chip
                                    icon={<RunsIcon />}
                                    label={`Tool failures: ${executionInsights?.tool_call_failed_events ?? 0}`}
                                    size="small"
                                    variant="outlined"
                                />
                                <Chip
                                    label={`Blocked: ${executionInsights?.blocked_events ?? 0}`}
                                    size="small"
                                    variant="outlined"
                                />
                                <Chip
                                    label={`Reopened: ${executionInsights?.reopen_events ?? 0}`}
                                    size="small"
                                    variant="outlined"
                                />
                            </Stack>
                        )}
                    </Box>
                </Stack>
            </CollapsibleSectionCard>
        </PageShell>
    );
}
