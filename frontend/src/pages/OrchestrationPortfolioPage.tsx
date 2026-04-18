import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
    Alert,
    Box,
    Button,
    Chip,
    MenuItem,
    Paper,
    Stack,
    TextField,
    Typography,
} from "@mui/material";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { getOrchestrationPortfolioControlPlane, updatePortfolioExecutionPolicy } from "../api/orchestration";
import { PageHeader } from "../components/ui/PageHeader";
import { PageShell } from "../components/ui/PageShell";
import { SectionCard } from "../components/ui/SectionCard";
import { useLiveSnapshotStream } from "../hooks/useLiveSnapshotStream";
import { formatDateTime } from "../utils/formatters";
import { useSnackbar } from "../app/snackbarContext";

export default function OrchestrationPortfolioPage() {
    const navigate = useNavigate();
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();
    const { data, isLoading, error } = useQuery({
        queryKey: ["orchestration", "portfolio", "control-plane"],
        queryFn: getOrchestrationPortfolioControlPlane,
    });
    const [policyDraft, setPolicyDraft] = useState<null | {
        routing_mode: string;
        approval_policy: string;
        repo_indexing_cadence: string;
        cost_cap_usd: string;
    }>(null);

    useLiveSnapshotStream("/orchestration/portfolio/stream", {
        enabled: !error,
        onSnapshot: () => {
            void queryClient.invalidateQueries({ queryKey: ["orchestration", "portfolio", "control-plane"] });
        },
    });

    const resolvedPolicyDraft = policyDraft ?? {
        routing_mode: data?.execution_policy?.routing_mode ?? "capability_based",
        approval_policy: data?.execution_policy?.approval_policy ?? "manager_review",
        repo_indexing_cadence: data?.execution_policy?.repo_indexing_cadence ?? "daily",
        cost_cap_usd: String(data?.execution_policy?.cost_cap_usd ?? 250),
    };

    const savePolicyMutation = useMutation({
        mutationFn: () => updatePortfolioExecutionPolicy({
            routing_mode: resolvedPolicyDraft.routing_mode,
            approval_policy: resolvedPolicyDraft.approval_policy,
            repo_indexing_cadence: resolvedPolicyDraft.repo_indexing_cadence,
            cost_cap_usd: Number(resolvedPolicyDraft.cost_cap_usd || 0),
        }),
        onSuccess: async () => {
            setPolicyDraft(null);
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "portfolio", "control-plane"] });
            showToast({ message: "Portfolio execution defaults saved.", severity: "success" });
        },
        onError: (mutationError) => {
            showToast({
                message: mutationError instanceof Error ? mutationError.message : "Couldn't save portfolio defaults.",
                severity: "error",
            });
        },
    });

    const projects = data?.projects ?? [];
    const totals = data?.totals ?? {};
    const operatorDashboard = data?.operator_dashboard;

    return (
        <PageShell maxWidth="xl">
            <PageHeader
                eyebrow="Orchestration"
                title="Portfolio Control Plane"
                description="Cross-project supervisor view for manager coverage, repo health, blocked work, queue depth, cost, and escalations."
            />

            {error && (
                <Alert severity="error" sx={{ mb: 2 }}>
                    {error.message || "An error occurred loading the portfolio data"}
                </Alert>
            )}

            <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "repeat(2, 1fr)", md: "repeat(4, 1fr)" }, gap: 2, mb: 4 }}>
                {[
                    { label: "Active runs", value: String(totals.active_runs ?? 0) },
                    { label: "Blocked tasks", value: String(totals.blocked_tasks ?? 0) },
                    { label: "Escalations", value: String(totals.pending_escalations ?? 0) },
                    { label: "30d cost", value: `$${Number(totals.cost_usd_30d ?? 0).toFixed(2)}` },
                ].map((metric) => (
                    <Paper key={metric.label} sx={{ p: 2, borderRadius: 4 }}>
                        <Typography variant="caption" color="text.secondary">{metric.label}</Typography>
                        <Typography variant="h5" sx={{ mt: 0.5 }}>{metric.value}</Typography>
                    </Paper>
                ))}
            </Box>

            <SectionCard title="Operator Dashboard" description="Runtime and sync health across queues, replay, webhook lag, and service planes.">
                {!operatorDashboard ? (
                    <Typography variant="body2" color="text.secondary">Loading operator health…</Typography>
                ) : (
                    <Stack spacing={2}>
                        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "repeat(4, 1fr)" }, gap: 2 }}>
                            {[
                                {
                                    label: "Queue health",
                                    value: `${Number(operatorDashboard.queue_health.queued_runs ?? 0)} queued`,
                                    detail: `active ${Number(operatorDashboard.queue_health.active_runs ?? 0)} • blocked ${Number(operatorDashboard.queue_health.blocked_tasks ?? 0)}`,
                                    status: String(operatorDashboard.queue_health.status ?? "healthy"),
                                },
                                {
                                    label: "Webhook lag",
                                    value: `${Number(operatorDashboard.webhook_lag.max_lag_minutes ?? 0).toFixed(1)} min`,
                                    detail: `${Number(operatorDashboard.webhook_lag.pending_events ?? 0)} pending event(s)`,
                                    status: String(operatorDashboard.webhook_lag.status ?? "healthy"),
                                },
                                {
                                    label: "Replay backlog",
                                    value: String(operatorDashboard.replay_backlog.events ?? 0),
                                    detail: `failed ${Number(operatorDashboard.replay_backlog.failed_events ?? 0)}`,
                                    status: String(operatorDashboard.replay_backlog.status ?? "healthy"),
                                },
                                {
                                    label: "Stuck runs",
                                    value: String(operatorDashboard.stuck_runs.count ?? 0),
                                    detail: `threshold ${Number(operatorDashboard.stuck_runs.threshold_minutes ?? 45)} min`,
                                    status: String(operatorDashboard.stuck_runs.status ?? "healthy"),
                                },
                            ].map((card) => (
                                <Paper key={card.label} variant="outlined" sx={{ p: 2, borderRadius: 3 }}>
                                    <Stack direction="row" justifyContent="space-between" spacing={1}>
                                        <Typography variant="caption" color="text.secondary">{card.label}</Typography>
                                        <Chip
                                            size="small"
                                            label={card.status}
                                            color={card.status === "critical" ? "error" : card.status === "watch" ? "warning" : "success"}
                                        />
                                    </Stack>
                                    <Typography variant="h5" sx={{ mt: 1 }}>{card.value}</Typography>
                                    <Typography variant="body2" color="text.secondary">{card.detail}</Typography>
                                </Paper>
                            ))}
                        </Box>
                        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", xl: "repeat(5, 1fr)" }, gap: 2 }}>
                            {operatorDashboard.services.map((service) => (
                                <Paper key={service.key} variant="outlined" sx={{ p: 1.5, borderRadius: 3 }}>
                                    <Stack direction="row" justifyContent="space-between" spacing={1}>
                                        <Typography variant="subtitle2">{service.label}</Typography>
                                        <Chip
                                            size="small"
                                            label={service.status}
                                            color={service.status === "critical" ? "error" : service.status === "watch" ? "warning" : "success"}
                                        />
                                    </Stack>
                                    <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                                        {service.summary}
                                    </Typography>
                                </Paper>
                            ))}
                        </Box>
                    </Stack>
                )}
            </SectionCard>

            <SectionCard title="Execution Defaults" description="Portfolio-wide defaults for routing, approvals, repo indexing cadence, and spend guardrails.">
                <Stack spacing={2}>
                    <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "repeat(4, 1fr)" }, gap: 2 }}>
                        <TextField
                            select
                            label="Routing mode"
                            value={resolvedPolicyDraft.routing_mode}
                            onChange={(event) => setPolicyDraft((current) => ({ ...(current ?? resolvedPolicyDraft), routing_mode: event.target.value }))}
                        >
                            {["capability_based", "balanced", "cost_aware", "throughput", "model_availability", "sla_priority", "user_pinned"].map((value) => (
                                <MenuItem key={value} value={value}>{value}</MenuItem>
                            ))}
                        </TextField>
                        <TextField
                            select
                            label="Approval policy"
                            value={resolvedPolicyDraft.approval_policy}
                            onChange={(event) => setPolicyDraft((current) => ({ ...(current ?? resolvedPolicyDraft), approval_policy: event.target.value }))}
                        >
                            {["manager_review", "human_gate", "auto_if_green"].map((value) => (
                                <MenuItem key={value} value={value}>{value}</MenuItem>
                            ))}
                        </TextField>
                        <TextField
                            select
                            label="Repo indexing cadence"
                            value={resolvedPolicyDraft.repo_indexing_cadence}
                            onChange={(event) => setPolicyDraft((current) => ({ ...(current ?? resolvedPolicyDraft), repo_indexing_cadence: event.target.value }))}
                        >
                            {["hourly", "daily", "weekly", "manual"].map((value) => (
                                <MenuItem key={value} value={value}>{value}</MenuItem>
                            ))}
                        </TextField>
                        <TextField
                            label="Cost cap (USD)"
                            value={resolvedPolicyDraft.cost_cap_usd}
                            onChange={(event) => setPolicyDraft((current) => ({ ...(current ?? resolvedPolicyDraft), cost_cap_usd: event.target.value }))}
                        />
                    </Box>
                    <Stack direction="row" justifyContent="space-between" spacing={2} alignItems={{ md: "center" }} sx={{ flexWrap: "wrap", gap: 1 }}>
                        <Typography variant="body2" color="text.secondary">
                            Saving updates inherited projects immediately. Explicit project overrides stay pinned.
                        </Typography>
                        <Button variant="contained" onClick={() => savePolicyMutation.mutate()} disabled={savePolicyMutation.isPending}>
                            Save defaults
                        </Button>
                    </Stack>
                </Stack>
            </SectionCard>

            <SectionCard title="Supervisor Grid" description="Jump from one control surface into project, task, or run detail.">
                {isLoading ? (
                    <Typography variant="body2" color="text.secondary">Loading portfolio control plane…</Typography>
                ) : projects.length === 0 ? (
                    <Typography variant="body2" color="text.secondary">No orchestration projects yet.</Typography>
                ) : (
                    <Stack spacing={2}>
                        {projects.map((project) => {
                            const manager = project.manager as { name?: string; slug?: string; agent_id?: string | null };
                            const health = project.health as { status?: string; score?: number; repository_failures?: number; index_failures?: number; open_blockers?: number };
                            const costRollup = project.cost_rollup as { cost_usd_30d?: number; token_total_30d?: number; repository_links?: number };
                            const latestRun = project.latest_run as { run_id?: string; status?: string; created_at?: string } | null;
                            const policy = project.execution_policy as { items?: Array<{ key?: string; label?: string; effective?: unknown; default?: unknown; source?: string; overridden?: boolean }> };
                            return (
                                <Paper key={project.project_id} sx={{ p: 2, borderRadius: 4 }}>
                                    <Stack direction={{ xs: "column", xl: "row" }} spacing={2} justifyContent="space-between">
                                        <Box sx={{ flex: 1 }}>
                                            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap alignItems="center">
                                                <Typography variant="h6">{project.name}</Typography>
                                                <Chip size="small" variant="outlined" label={project.slug} />
                                                <Chip
                                                    size="small"
                                                    color={health.status === "critical" ? "error" : health.status === "watch" ? "warning" : "success"}
                                                    label={`${String(health.status ?? "healthy")} • ${Number(health.score ?? 0)}`}
                                                />
                                            </Stack>
                                            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.75 }}>
                                                Manager: {manager.name || "Unassigned"} {manager.slug ? `• ${manager.slug}` : ""}
                                            </Typography>
                                            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mt: 1.25 }}>
                                                <Chip size="small" variant="outlined" label={`queued runs ${Number(project.queue_depth.queued_runs ?? 0)}`} />
                                                <Chip size="small" variant="outlined" label={`active runs ${Number(project.queue_depth.active_runs ?? 0)}`} />
                                                <Chip size="small" variant="outlined" label={`queued tasks ${Number(project.queue_depth.queued_tasks ?? 0)}`} />
                                                <Chip size="small" variant="outlined" label={`repos ${Number(costRollup.repository_links ?? 0)}`} />
                                                <Chip size="small" variant="outlined" label={`30d cost $${Number(costRollup.cost_usd_30d ?? 0).toFixed(2)}`} />
                                                <Chip
                                                    size="small"
                                                    color={Number((project.execution_policy as { override_count?: number }).override_count ?? 0) > 0 ? "warning" : "success"}
                                                    label={`${Number((project.execution_policy as { override_count?: number }).override_count ?? 0)} override(s)`}
                                                />
                                            </Stack>
                                            <Box sx={{ mt: 1.5 }}>
                                                <Typography variant="caption" color="text.secondary">Execution policy visibility</Typography>
                                                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mt: 0.75 }}>
                                                    {(policy.items ?? []).map((item) => (
                                                        <Chip
                                                            key={String(item.key ?? item.label)}
                                                            size="small"
                                                            variant="outlined"
                                                            color={item.source === "project_override" ? "warning" : "default"}
                                                            label={`${String(item.label ?? item.key)}: ${String(item.effective)}${item.source === "project_override" ? " (override)" : ""}`}
                                                        />
                                                    ))}
                                                </Stack>
                                            </Box>
                                            <Stack direction={{ xs: "column", md: "row" }} spacing={2} sx={{ mt: 1.5 }}>
                                                <Box sx={{ flex: 1 }}>
                                                    <Typography variant="caption" color="text.secondary">Blocked work</Typography>
                                                    <Stack spacing={0.75} sx={{ mt: 0.75 }}>
                                                        {project.blocked_work.length > 0 ? project.blocked_work.map((item) => {
                                                            const row = item as { task_id?: string; title?: string; priority?: string; updated_at?: string };
                                                            return (
                                                                <Paper key={row.task_id} variant="outlined" sx={{ p: 1, borderRadius: 2 }}>
                                                                    <Typography variant="body2">{row.title || "Blocked task"}</Typography>
                                                                    <Typography variant="caption" color="text.secondary">
                                                                        {row.priority || "normal"} {row.updated_at ? `• ${formatDateTime(row.updated_at)}` : ""}
                                                                    </Typography>
                                                                </Paper>
                                                            );
                                                        }) : (
                                                            <Typography variant="body2" color="text.secondary">No blocked tasks.</Typography>
                                                        )}
                                                    </Stack>
                                                </Box>
                                                <Box sx={{ flex: 1 }}>
                                                    <Typography variant="caption" color="text.secondary">Escalation inbox</Typography>
                                                    <Stack spacing={0.75} sx={{ mt: 0.75 }}>
                                                        {project.escalation_inbox.length > 0 ? project.escalation_inbox.map((item) => {
                                                            const row = item as { approval_id?: string; approval_type?: string; task_id?: string | null; created_at?: string };
                                                            return (
                                                                <Alert key={row.approval_id} severity="warning">
                                                                    {row.approval_type} {row.task_id ? `• task ${row.task_id.slice(0, 8)}` : ""} {row.created_at ? `• ${formatDateTime(row.created_at)}` : ""}
                                                                </Alert>
                                                            );
                                                        }) : (
                                                            <Typography variant="body2" color="text.secondary">No pending escalations.</Typography>
                                                        )}
                                                    </Stack>
                                                </Box>
                                            </Stack>
                                        </Box>
                                        <Stack spacing={1} sx={{ width: { xs: "100%", xl: 240 } }}>
                                            <Paper variant="outlined" sx={{ p: 1.25, borderRadius: 3 }}>
                                                <Typography variant="caption" color="text.secondary">Repo health</Typography>
                                                <Typography variant="body2" sx={{ mt: 0.5 }}>
                                                    Sync failures {Number(health.repository_failures ?? 0)} • Index failures {Number(health.index_failures ?? 0)}
                                                </Typography>
                                                <Typography variant="body2" color="text.secondary">
                                                    Open blockers {Number(health.open_blockers ?? 0)}
                                                </Typography>
                                            </Paper>
                                            <Paper variant="outlined" sx={{ p: 1.25, borderRadius: 3 }}>
                                                <Typography variant="caption" color="text.secondary">Latest run</Typography>
                                                <Typography variant="body2" sx={{ mt: 0.5 }}>
                                                    {latestRun?.run_id ? latestRun.status : "No runs yet"}
                                                </Typography>
                                                <Typography variant="caption" color="text.secondary">
                                                    {latestRun?.created_at ? formatDateTime(latestRun.created_at) : ""}
                                                </Typography>
                                            </Paper>
                                            <Button variant="contained" onClick={() => navigate(`/agent-projects/${project.project_id}`)}>
                                                Open project
                                            </Button>
                                            {latestRun?.run_id ? (
                                                <Button variant="outlined" onClick={() => navigate(`/runs/${latestRun.run_id}`)}>
                                                    Open latest run
                                                </Button>
                                            ) : null}
                                        </Stack>
                                    </Stack>
                                </Paper>
                            );
                        })}
                    </Stack>
                )}
            </SectionCard>
        </PageShell>
    );
}
