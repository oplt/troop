import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
    Alert,
    Box,
    Button,
    Chip,
    CircularProgress,
    MenuItem,
    Paper,
    Stack,
    Tab,
    Tabs,
    TextField,
    Typography,
} from "@mui/material";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
    Check as ApproveIcon,
    Close as RejectIcon,
    TaskAlt as TaskIcon,
    PlayArrow as RunIcon,
    Info as InfoIcon,
} from "@mui/icons-material";
import type { Approval } from "../api/orchestration";
import {
    decideApproval,
    listAgents,
    listApprovals,
    listGithubSyncEvents,
    listOrchestrationProjects,
    listRuns,
} from "../api/orchestration";
import { useSnackbar } from "../app/snackbarContext";
import { PageHeader } from "../components/ui/PageHeader";
import { PageShell } from "../components/ui/PageShell";
import { SectionCard } from "../components/ui/SectionCard";
import { formatDateTime, humanizeKey } from "../utils/formatters";

/** Map approval_type to a human-readable action description */
function describeAction(approval: { approval_type: string; payload: Record<string, unknown> }): string {
    const { approval_type: type, payload } = approval;
    switch (type) {
        case "github_comment":
            return "Post a comment to GitHub";
        case "rule_escalation": {
            const condition = payload?.condition as string | undefined;
            if (condition === "cost_exceeds_usd") {
                const cost = payload?.cost_usd as number | undefined;
                return cost != null ? `Cost threshold exceeded ($${cost.toFixed(2)})` : "Cost threshold exceeded";
            }
            if (condition === "stuck_for_minutes") {
                const mins = payload?.elapsed_minutes as number | undefined;
                return mins != null ? `Task stalled for ${mins} minutes` : "Task stalled";
            }
            if (condition === "no_consensus_after_rounds") {
                const rounds = payload?.rounds_completed as number | undefined;
                return rounds != null ? `No consensus after ${rounds} rounds` : "No consensus reached";
            }
            return "Escalation rule triggered";
        }
        case "task_escalation": {
            const reason = payload?.reason as string | undefined;
            return reason ?? "Task escalated to human";
        }
        case "agent_memory_write":
            return "Write to agent memory";
        case "post_to_github":
            return "Post results to GitHub";
        case "open_pr":
            return "Open a pull request";
        case "mark_complete":
            return "Mark task as complete";
        case "write_memory":
            return "Write to project memory";
        case "use_expensive_model":
            return "Use an expensive model";
        case "run_tool":
            return "Run an external tool";
        default:
            return humanizeKey(type);
    }
}

function statusColor(status: string) {
    if (status === "approved") return "success" as const;
    if (status === "rejected") return "error" as const;
    return "warning" as const;
}

function parseDateBoundary(value: string, endOfDay: boolean): number | null {
    if (!value.trim()) return null;
    const t = new Date(value + (endOfDay ? "T23:59:59.999Z" : "T00:00:00.000Z"));
    return Number.isNaN(t.getTime()) ? null : t.getTime();
}

function ApprovalCard({ approval }: { approval: Approval }) {
    const [reason, setReason] = useState("");
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();
    const navigate = useNavigate();

    const mutation = useMutation({
        mutationFn: ({ status, reason: r }: { status: "approved" | "rejected"; reason?: string }) =>
            decideApproval(approval.id, { status, reason: r }),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "approvals"] });
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "approvals", "pending-count"] });
            showToast({ message: "Approval decision saved.", severity: "success" });
        },
    });

    const isPending = approval.status === "pending";
    const actionDescription = describeAction(approval);

    return (
        <Paper
            sx={{
                p: 2,
                borderRadius: 3,
                border: (t) => (isPending ? `1px solid ${t.palette.warning.light}` : "1px solid transparent"),
                bgcolor: (t) => (!isPending ? t.palette.action.hover : "transparent"),
            }}
        >
            <Stack spacing={1.5}>
                <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                    <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                        {actionDescription}
                    </Typography>
                    <Chip
                        label={humanizeKey(approval.status)}
                        size="small"
                        color={statusColor(approval.status)}
                        variant={isPending ? "outlined" : "filled"}
                    />
                    {approval.approval_type.includes("escalation") && (
                        <Chip label="Escalation" size="small" variant="outlined" color="info" />
                    )}
                </Stack>

                <Stack direction="row" spacing={1.5} alignItems="center" flexWrap="wrap" useFlexGap>
                    {approval.task_id && (
                        <Stack direction="row" spacing={0.5} alignItems="center">
                            <TaskIcon fontSize="small" sx={{ color: "text.secondary" }} />
                            <Typography variant="caption" color="text.secondary">
                                Task: {approval.task_id.slice(0, 8)}
                            </Typography>
                        </Stack>
                    )}
                    {approval.run_id && (
                        <Stack direction="row" spacing={0.5} alignItems="center">
                            <RunIcon fontSize="small" sx={{ color: "text.secondary" }} />
                            <Button
                                size="small"
                                variant="text"
                                sx={{ p: 0, minWidth: "auto", fontSize: "0.75rem" }}
                                onClick={() => navigate(`/runs/${approval.run_id}`)}
                            >
                                Run {approval.run_id.slice(0, 8)}
                            </Button>
                        </Stack>
                    )}
                    {approval.issue_link_id && (
                        <Typography variant="caption" color="text.secondary">
                            Issue link: {approval.issue_link_id.slice(0, 8)}
                        </Typography>
                    )}
                    <Typography variant="caption" color="text.secondary" sx={{ ml: "auto" }}>
                        {formatDateTime(approval.created_at)}
                    </Typography>
                </Stack>

                {Object.keys(approval.payload).length > 0 && (
                    <Box
                        sx={{
                            p: 1.25,
                            borderRadius: 2,
                            bgcolor: "background.default",
                            border: 1,
                            borderColor: "divider",
                            fontFamily: "monospace",
                            fontSize: "0.78rem",
                            maxHeight: 120,
                            overflow: "auto",
                            whiteSpace: "pre-wrap",
                        }}
                    >
                        {JSON.stringify(approval.payload, null, 2)}
                    </Box>
                )}

                {!isPending && approval.reason && (
                    <Alert severity={approval.status === "approved" ? "success" : "warning"} sx={{ py: 0.5, px: 1.5 }} icon={<InfoIcon fontSize="small" />}>
                        <Typography variant="caption">{approval.reason}</Typography>
                    </Alert>
                )}

                {isPending && (
                    <>
                        <TextField
                            size="small"
                            label="Reason (optional)"
                            value={reason}
                            onChange={(e) => setReason(e.target.value)}
                            disabled={mutation.isPending}
                        />
                        <Stack direction="row" spacing={1}>
                            <Button
                                size="small"
                                variant="contained"
                                startIcon={mutation.isPending ? <CircularProgress size={16} /> : <ApproveIcon />}
                                disabled={mutation.isPending}
                                onClick={() => mutation.mutate({ status: "approved", reason: reason || undefined })}
                            >
                                Approve
                            </Button>
                            <Button
                                size="small"
                                variant="outlined"
                                color="error"
                                startIcon={mutation.isPending ? <CircularProgress size={16} /> : <RejectIcon />}
                                disabled={mutation.isPending}
                                onClick={() => mutation.mutate({ status: "rejected", reason: reason || undefined })}
                            >
                                Reject
                            </Button>
                        </Stack>
                    </>
                )}
            </Stack>
        </Paper>
    );
}

export default function ActivityAuditPage() {
    const navigate = useNavigate();
    const [mainTab, setMainTab] = useState<"approvals" | "ledger">("approvals");
    const [approvalSubTab, setApprovalSubTab] = useState<"pending" | "history">("pending");
    const [dateFrom, setDateFrom] = useState("");
    const [dateTo, setDateTo] = useState("");
    const [projectFilter, setProjectFilter] = useState("");
    const [agentFilter, setAgentFilter] = useState("");

    const { data: approvals = [], isLoading: approvalsLoading } = useQuery({
        queryKey: ["orchestration", "approvals"],
        queryFn: listApprovals,
    });
    const { data: runs = [], isLoading: runsLoading } = useQuery({
        queryKey: ["orchestration", "runs"],
        queryFn: () => listRuns(),
    });
    const { data: projects = [] } = useQuery({
        queryKey: ["orchestration", "projects"],
        queryFn: listOrchestrationProjects,
    });
    const { data: agents = [] } = useQuery({
        queryKey: ["orchestration", "agents"],
        queryFn: () => listAgents(),
    });
    const { data: syncEvents = [], isLoading: syncLoading } = useQuery({
        queryKey: ["orchestration", "github-sync-events", "all"],
        queryFn: () => listGithubSyncEvents(),
    });

    const fromMs = parseDateBoundary(dateFrom, false);
    const toMs = parseDateBoundary(dateTo, true);

    const filterByDate = (iso: string) => {
        const t = new Date(iso).getTime();
        if (fromMs != null && t < fromMs) return false;
        if (toMs != null && t > toMs) return false;
        return true;
    };

    const filteredApprovals = useMemo(() => {
        return approvals.filter((a) => {
            if (!filterByDate(a.created_at)) return false;
            if (projectFilter && a.project_id !== projectFilter) return false;
            if (agentFilter) {
                const payloadAgent =
                    (a.payload?.agent_id as string | undefined) ||
                    (a.payload?.worker_agent_id as string | undefined) ||
                    (a.payload?.orchestrator_agent_id as string | undefined);
                const run = a.run_id ? runs.find((r) => r.id === a.run_id) : undefined;
                const runAgents = [run?.worker_agent_id, run?.orchestrator_agent_id, run?.reviewer_agent_id].filter(Boolean);
                const hit =
                    payloadAgent === agentFilter ||
                    runAgents.includes(agentFilter);
                if (!hit) return false;
            }
            return true;
        });
    }, [approvals, agentFilter, projectFilter, fromMs, toMs, runs]);

    const filteredRuns = useMemo(() => {
        return runs.filter((run) => {
            if (!filterByDate(run.created_at)) return false;
            if (projectFilter && run.project_id !== projectFilter) return false;
            if (agentFilter) {
                const ids = [run.worker_agent_id, run.orchestrator_agent_id, run.reviewer_agent_id];
                if (!ids.includes(agentFilter)) return false;
            }
            return true;
        });
    }, [runs, projectFilter, agentFilter, fromMs, toMs]);

    const filteredSync = useMemo(() => {
        return syncEvents.filter((e) => filterByDate(e.created_at));
    }, [syncEvents, fromMs, toMs]);

    const { pending, resolved } = useMemo(() => {
        const pendingList: Approval[] = [];
        const resolvedList: Approval[] = [];
        for (const a of filteredApprovals) {
            if (a.status === "pending") pendingList.push(a);
            else resolvedList.push(a);
        }
        pendingList.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
        resolvedList.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
        return { pending: pendingList, resolved: resolvedList };
    }, [filteredApprovals]);

    return (
        <PageShell maxWidth="xl">
            <PageHeader
                eyebrow="Observability"
                title="Activity & Approvals"
                description="Approvals queue and history, plus a run ledger and GitHub sync trail. Filter by date range, agent project, and agent identity."
            />

            <Paper sx={{ p: 2, borderRadius: 3, mb: 2 }}>
                <Stack spacing={2}>
                    <Stack direction={{ xs: "column", md: "row" }} spacing={2} flexWrap="wrap" useFlexGap>
                        <TextField
                            label="From date"
                            type="date"
                            size="small"
                            value={dateFrom}
                            onChange={(e) => setDateFrom(e.target.value)}
                            InputLabelProps={{ shrink: true }}
                            sx={{ minWidth: 160 }}
                        />
                        <TextField
                            label="To date"
                            type="date"
                            size="small"
                            value={dateTo}
                            onChange={(e) => setDateTo(e.target.value)}
                            InputLabelProps={{ shrink: true }}
                            sx={{ minWidth: 160 }}
                        />
                        <TextField
                            select
                            label="Agent project"
                            size="small"
                            value={projectFilter}
                            onChange={(e) => setProjectFilter(e.target.value)}
                            sx={{ minWidth: 200 }}
                        >
                            <MenuItem value="">All projects</MenuItem>
                            {projects.map((p) => (
                                <MenuItem key={p.id} value={p.id}>{p.name}</MenuItem>
                            ))}
                        </TextField>
                        <TextField
                            select
                            label="Agent"
                            size="small"
                            value={agentFilter}
                            onChange={(e) => setAgentFilter(e.target.value)}
                            sx={{ minWidth: 200 }}
                        >
                            <MenuItem value="">Any agent</MenuItem>
                            {agents.map((a) => (
                                <MenuItem key={a.id} value={a.id}>{a.name}</MenuItem>
                            ))}
                        </TextField>
                    </Stack>
                </Stack>
            </Paper>

            <Paper sx={{ mb: 2, borderRadius: 4, p: 1 }}>
                <Tabs value={mainTab} onChange={(_, v) => setMainTab(v)}>
                    <Tab label="Approvals" value="approvals" />
                    <Tab label={`Run ledger (${filteredRuns.length})`} value="ledger" />
                </Tabs>
            </Paper>

            {mainTab === "approvals" && (
                <Stack spacing={2}>
                    <Paper sx={{ borderRadius: 4, p: 1 }}>
                        <Tabs value={approvalSubTab} onChange={(_, v) => setApprovalSubTab(v)}>
                            <Tab label={`Pending (${pending.length})`} value="pending" />
                            <Tab label={`History (${resolved.length})`} value="history" />
                        </Tabs>
                    </Paper>

                    {approvalSubTab === "pending" && (
                        <SectionCard
                            title="Pending approvals"
                            description="Actions that wait for a human decision before the run can continue."
                        >
                            <Stack spacing={1.5}>
                                {approvalsLoading && (
                                    <Box sx={{ display: "flex", justifyContent: "center", py: 3 }}>
                                        <CircularProgress size={24} />
                                    </Box>
                                )}
                                {!approvalsLoading && pending.length === 0 && (
                                    <Alert severity="success" sx={{ py: 1 }}>
                                        <Typography variant="body2">All caught up — no pending approvals in this filter.</Typography>
                                    </Alert>
                                )}
                                {pending.map((approval) => (
                                    <ApprovalCard key={approval.id} approval={approval} />
                                ))}
                            </Stack>
                        </SectionCard>
                    )}

                    {approvalSubTab === "history" && (
                        <SectionCard title="Approval history" description="Previously decided requests (newest first).">
                            <Stack spacing={1.5}>
                                {resolved.length === 0 && (
                                    <Typography variant="body2" color="text.secondary">
                                        No resolved approvals match the current filters.
                                    </Typography>
                                )}
                                {resolved.map((approval) => (
                                    <ApprovalCard key={approval.id} approval={approval} />
                                ))}
                            </Stack>
                        </SectionCard>
                    )}
                </Stack>
            )}

            {mainTab === "ledger" && (
                <Stack spacing={2}>
                    <SectionCard
                        title="Runs"
                        description="Execution history with model and token metadata. Use Inspect for the live event stream."
                    >
                        {runsLoading && (
                            <Box sx={{ display: "flex", justifyContent: "center", py: 3 }}>
                                <CircularProgress size={24} />
                            </Box>
                        )}
                        <Stack spacing={1.5}>
                            {filteredRuns.map((run) => (
                                <Paper key={run.id} sx={{ p: 2, borderRadius: 3 }}>
                                    <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
                                        <Box>
                                            <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                                                <Chip label={humanizeKey(run.run_mode)} size="small" variant="outlined" />
                                                <Chip
                                                    label={humanizeKey(run.status)}
                                                    size="small"
                                                    color={
                                                        run.status === "completed"
                                                            ? "success"
                                                            : run.status === "failed"
                                                              ? "error"
                                                              : run.status === "in_progress"
                                                                ? "info"
                                                                : "default"
                                                    }
                                                />
                                            </Stack>
                                            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                                                {run.model_name || "default model"} • {run.token_total.toLocaleString()} tokens • {run.latency_ms ?? 0} ms
                                            </Typography>
                                            <Typography variant="caption" color="text.secondary">
                                                Project {projects.find((p) => p.id === run.project_id)?.name ?? run.project_id.slice(0, 8)} • {formatDateTime(run.created_at)}
                                            </Typography>
                                        </Box>
                                        <Button size="small" variant="outlined" onClick={() => navigate(`/runs/${run.id}`)}>
                                            Inspect
                                        </Button>
                                    </Stack>
                                </Paper>
                            ))}
                            {filteredRuns.length === 0 && !runsLoading && (
                                <Typography variant="body2" color="text.secondary">No runs match the current filters.</Typography>
                            )}
                        </Stack>
                    </SectionCard>

                    <SectionCard title="GitHub sync events" description="Webhook and sync pipeline activity (filtered by date only).">
                        {syncLoading && <CircularProgress size={20} />}
                        <Stack spacing={1.25}>
                            {filteredSync.map((event) => (
                                <Paper key={event.id} sx={{ p: 1.5, borderRadius: 3 }}>
                                    <Typography variant="body2">{event.action} • {event.status}</Typography>
                                    <Typography variant="caption" color="text.secondary">
                                        {event.detail || "—"} • {formatDateTime(event.created_at)}
                                    </Typography>
                                </Paper>
                            ))}
                            {filteredSync.length === 0 && !syncLoading && (
                                <Typography variant="body2" color="text.secondary">No sync events in range.</Typography>
                            )}
                        </Stack>
                    </SectionCard>
                </Stack>
            )}
        </PageShell>
    );
}
