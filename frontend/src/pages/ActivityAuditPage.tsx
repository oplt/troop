import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
    Alert,
    Box,
    Button,
    Chip,
    CircularProgress,
    Dialog,
    DialogActions,
    DialogContent,
    DialogTitle,
    Divider,
    MenuItem,
    Paper,
    Stack,
    Tab,
    Tabs,
    TextField,
    Typography,
} from "@mui/material";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
    Check as ApproveIcon,
    Close as RejectIcon,
    TaskAlt as TaskIcon,
    PlayArrow as RunIcon,
    Info as InfoIcon,
    EditOutlined as EditIcon,
    RateReviewOutlined as RequestChangesIcon,
} from "@mui/icons-material";
import type { Approval, HITLAuditLog } from "../api/orchestration";
import {
    decideApproval,
    listAgents,
    listApprovals,
    listGithubSyncEvents,
    listHITLAuditLogs,
    listOrchestrationProjects,
    listRuns,
} from "../api/orchestration";
import { useSnackbar } from "../app/snackbarContext";
import { PageShell } from "../components/ui/PageShell";
import { PageHeader } from "../components/ui/PageHeader";
import { SectionCard } from "../components/ui/SectionCard";
import { StatusChip } from "../components/ui/StatusChip";
import { FilterToolbar } from "../components/ui/FilterToolbar";
import { queryKeys } from "../config/queryKeys";
import { formatDateTime, humanizeKey } from "../utils/formatters";
import { editEmailApprovalPayload, requestApprovalChanges } from "../api/integrations";
import { normalizeEmailApproval } from "../features/approvals/emailApproval";

/** Map approval_type to a human-readable action description */
function describeAction(approval: { approval_type: string; payload: Record<string, unknown> }): string {
    const { approval_type: type, payload } = approval;
    const operation = String(payload.operation ?? payload.action ?? payload.tool_key ?? "");
    if (type.includes("email") || type.includes("gmail") || operation.includes("gmail")) {
        return operation.includes("send") ? "Approve and send email draft" : "Review email action";
    }
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

function parseDateBoundary(value: string, endOfDay: boolean): number | null {
    if (!value.trim()) return null;
    const t = new Date(value + (endOfDay ? "T23:59:59.999Z" : "T00:00:00.000Z"));
    return Number.isNaN(t.getTime()) ? null : t.getTime();
}

function EmailApprovalDetails({ approval }: { approval: Approval }) {
    const email = normalizeEmailApproval(approval.payload, approval.approval_type);
    const formatAddress = (item: { name?: string; email: string } | null) =>
        item ? (item.name ? `${item.name} <${item.email}>` : item.email) : "Not provided";
    return (
        <Stack spacing={2}>
            {email.stale && <Alert severity="error">This draft is stale or invalidated and must not be sent without a new approval.</Alert>}
            <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", lg: "repeat(2, minmax(0, 1fr))" }, gap: 2 }}>
                <Paper variant="outlined" sx={{ p: 2, borderRadius: 1 }}>
                    <Typography variant="subtitle2">Incoming email</Typography>
                    <Divider sx={{ my: 1 }} />
                    <Typography variant="caption" color="text.secondary">From</Typography>
                    <Typography variant="body2">{formatAddress(email.incoming.from)}</Typography>
                    <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>Subject</Typography>
                    <Typography variant="body2">{email.incoming.subject || "No subject"}</Typography>
                    <Typography variant="body2" sx={{ mt: 1, whiteSpace: "pre-wrap", maxHeight: 220, overflow: "auto" }}>
                        {email.incoming.body || "Body not included in approval payload."}
                    </Typography>
                </Paper>
                <Paper variant="outlined" sx={{ p: 2, borderRadius: 1 }}>
                    <Typography variant="subtitle2">Proposed reply</Typography>
                    <Divider sx={{ my: 1 }} />
                    <Typography variant="caption" color="text.secondary">To</Typography>
                    <Typography variant="body2">{email.draft.to.join(", ") || "Not provided"}</Typography>
                    <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>CC / BCC</Typography>
                    <Typography variant="body2">{email.draft.cc.join(", ") || "—"} / {email.draft.bcc.join(", ") || "—"}</Typography>
                    <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>Subject</Typography>
                    <Typography variant="body2">{email.draft.subject || "No subject"}</Typography>
                    <Typography variant="body2" sx={{ mt: 1, whiteSpace: "pre-wrap", maxHeight: 220, overflow: "auto" }}>
                        {email.draft.body_text || "Draft body not included."}
                    </Typography>
                </Paper>
            </Box>
            <Stack direction="row" gap={1} flexWrap="wrap" useFlexGap>
                <Chip label={`Risk: ${humanizeKey(email.risk)}`} color={email.risk === "high" ? "error" : email.risk === "medium" ? "warning" : "default"} size="small" />
                {email.agent && <Chip label={`Agent: ${email.agent}`} size="small" variant="outlined" />}
                {email.workflow && <Chip label={`Workflow: ${email.workflow}`} size="small" variant="outlined" />}
                {(email.project || email.task) && <Chip label={[email.project, email.task].filter(Boolean).join(" · ")} size="small" variant="outlined" />}
            </Stack>
            {email.warnings.length > 0 && <Alert severity="warning">{email.warnings.join(" · ")}</Alert>}
            {email.context.length > 0 && (
                <Box>
                    <Typography variant="subtitle2">Context and sources</Typography>
                    <Stack component="ul" sx={{ my: 0.5, pl: 2.5 }}>
                        {email.context.map((item, index) => (
                            <Typography component="li" variant="body2" key={`${item.title}-${index}`}>
                                {item.title}{item.source ? ` · ${item.source}` : ""}
                            </Typography>
                        ))}
                    </Stack>
                </Box>
            )}
        </Stack>
    );
}

function ApprovalCard({
    approval,
    focused = false,
    onFocusCard,
}: {
    approval: Approval;
    focused?: boolean;
    onFocusCard?: () => void;
}) {
    const [reason, setReason] = useState("");
    const [editOpen, setEditOpen] = useState(false);
    const email = normalizeEmailApproval(approval.payload, approval.approval_type);
    const [emailDraft, setEmailDraft] = useState(email.draft);
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();
    const navigate = useNavigate();

    const mutation = useMutation({
        mutationFn: ({ status, reason: r }: { status: "approved" | "rejected"; reason?: string }) =>
            decideApproval(approval.id, { status, reason: r }),
        onSuccess: async (decision) => {
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.approvals });
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.approvalsPendingCount });
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.runsRoot });
            showToast({
                message: decision.run_id && decision.status === "approved"
                    ? "Approval saved; the blocked run is being queued to resume."
                    : "Approval decision saved.",
                severity: "success",
            });
        },
        onError: (error) => {
            showToast({
                message: error instanceof Error ? error.message : "Couldn't save the approval decision.",
                severity: "error",
            });
        },
    });
    const editMutation = useMutation({
        mutationFn: () => editEmailApprovalPayload(approval.id, emailDraft),
        onSuccess: async () => {
            setEditOpen(false);
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.approvals });
            showToast({ message: "Draft updated. Review and approve the new exact version.", severity: "success" });
        },
        onError: (error) => showToast({ message: error instanceof Error ? error.message : "Draft update failed.", severity: "error" }),
    });
    const requestChangesMutation = useMutation({
        mutationFn: () => requestApprovalChanges(approval.id, reason),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.approvals });
            showToast({ message: "Changes requested on the canonical approval.", severity: "success" });
        },
        onError: (error) => showToast({ message: error instanceof Error ? error.message : "Request failed.", severity: "error" }),
    });

    const isPending = approval.status === "pending";
    const actionDescription = describeAction(approval);

    return (
        <Paper
            onClick={onFocusCard}
            tabIndex={isPending ? 0 : -1}
            onFocus={onFocusCard}
            sx={{
                p: 2,
                borderRadius: 1,
                outline: focused ? (t) => `2px solid ${t.palette.primary.main}` : "none",
                outlineOffset: 2,
                border: (t) => (isPending ? `1px solid ${t.palette.warning.light}` : "1px solid transparent"),
                bgcolor: (t) => (!isPending ? t.palette.action.hover : "transparent"),
            }}
        >
            <Stack spacing={1.5}>
                <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                    <Typography variant="subtitle2" sx={{ fontWeight: 500 }}>
                        {actionDescription}
                    </Typography>
                    <StatusChip
                        status={approval.status}
                        kind="approval"
                        variant={isPending ? "outlined" : "filled"}
                        celebrate={approval.status === "approved"}
                    />
                    {approval.approval_type.includes("escalation") && (
                        <Chip label="Escalation" size="small" variant="outlined" color="info" />
                    )}
                </Stack>

                <Stack direction="row" spacing={1.5} alignItems="center" flexWrap="wrap" useFlexGap>
                    {approval.task_id && (
                        <Stack direction="row" spacing={0.5} alignItems="center">
                            <TaskIcon fontSize="small" sx={{ color: "text.secondary" }} />
                            {approval.project_id ? (
                                <Button
                                    size="small"
                                    variant="text"
                                    sx={{ p: 0, minWidth: "auto", fontSize: "0.75rem" }}
                                    onClick={() => navigate(`/projects/${approval.project_id}`)}
                                >
                                    Task {approval.task_id.slice(0, 8)}
                                </Button>
                            ) : (
                                <Typography variant="caption" color="text.secondary">
                                    Task: {approval.task_id.slice(0, 8)}
                                </Typography>
                            )}
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

                {email.isEmail ? (
                    <EmailApprovalDetails approval={approval} />
                ) : Object.keys(approval.payload).length > 0 && (
                    <Box
                        sx={{
                            p: 1.25,
                            borderRadius: 1,
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
                            label="Decision note"
                            value={reason}
                            onChange={(e) => setReason(e.target.value)}
                            disabled={mutation.isPending}
                            helperText="A rejection requires a reason."
                        />
                        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                            <Button
                                size="small"
                                variant="contained"
                                startIcon={mutation.isPending ? <CircularProgress size={16} /> : <ApproveIcon />}
                                onClick={() => mutation.mutate({ status: "approved", reason: reason || undefined })}
                                disabled={mutation.isPending || email.stale}
                            >
                                {email.isEmail ? "Approve & Send" : "Approve"}
                            </Button>
                            {email.isEmail && (
                                <Button
                                    size="small"
                                    variant="outlined"
                                    startIcon={<EditIcon />}
                                    disabled={mutation.isPending}
                                    onClick={() => setEditOpen(true)}
                                >
                                    Edit
                                </Button>
                            )}
                            <Button
                                size="small"
                                variant="outlined"
                                color="error"
                                startIcon={mutation.isPending ? <CircularProgress size={16} /> : <RejectIcon />}
                                disabled={mutation.isPending || !reason.trim()}
                                onClick={() => mutation.mutate({ status: "rejected", reason: reason || undefined })}
                            >
                                Reject
                            </Button>
                            {email.isEmail && (
                                <Button
                                    size="small"
                                    variant="outlined"
                                    startIcon={<RequestChangesIcon />}
                                    disabled={requestChangesMutation.isPending || !reason.trim()}
                                    onClick={() => requestChangesMutation.mutate()}
                                >
                                    Request changes
                                </Button>
                            )}
                        </Stack>
                    </>
                )}
            </Stack>
            <Dialog open={editOpen} onClose={() => !editMutation.isPending && setEditOpen(false)} fullWidth maxWidth="md">
                <DialogTitle>Edit proposed email</DialogTitle>
                <DialogContent>
                    <Stack spacing={2} sx={{ pt: 1 }}>
                        <Alert severity="warning">Editing invalidates the previous content hash. The updated draft must be approved again before sending.</Alert>
                        <TextField label="To" value={emailDraft.to.join(", ")} onChange={(event) => setEmailDraft((current) => ({ ...current, to: event.target.value.split(",").map((item) => item.trim()).filter(Boolean) }))} fullWidth />
                        <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
                            <TextField label="CC" value={emailDraft.cc.join(", ")} onChange={(event) => setEmailDraft((current) => ({ ...current, cc: event.target.value.split(",").map((item) => item.trim()).filter(Boolean) }))} fullWidth />
                            <TextField label="BCC" value={emailDraft.bcc.join(", ")} onChange={(event) => setEmailDraft((current) => ({ ...current, bcc: event.target.value.split(",").map((item) => item.trim()).filter(Boolean) }))} fullWidth />
                        </Stack>
                        <TextField label="Subject" value={emailDraft.subject} onChange={(event) => setEmailDraft((current) => ({ ...current, subject: event.target.value }))} fullWidth />
                        <TextField label="Reply" value={emailDraft.body_text} onChange={(event) => setEmailDraft((current) => ({ ...current, body_text: event.target.value }))} multiline minRows={8} fullWidth />
                    </Stack>
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setEditOpen(false)} disabled={editMutation.isPending}>Cancel</Button>
                    <Button variant="contained" onClick={() => editMutation.mutate()} disabled={editMutation.isPending || !emailDraft.to.length || !emailDraft.body_text.trim()}>
                        Save revised draft
                    </Button>
                </DialogActions>
            </Dialog>
        </Paper>
    );
}

export default function ActivityAuditPage() {
    const navigate = useNavigate();
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();
    const [mainTab, setMainTab] = useState<"approvals" | "ledger" | "audit">("approvals");
    const [approvalSubTab, setApprovalSubTab] = useState<"pending" | "history">("pending");
    const [dateFrom, setDateFrom] = useState("");
    const [dateTo, setDateTo] = useState("");
    const [projectFilter, setProjectFilter] = useState("");
    const [agentFilter, setAgentFilter] = useState("");
    const [queueIndex, setQueueIndex] = useState(0);

    const { data: approvals = [], isLoading: approvalsLoading } = useQuery({
        queryKey: queryKeys.orchestration.approvals,
        queryFn: listApprovals,
    });
    const { data: runs = [], isLoading: runsLoading } = useQuery({
        queryKey: queryKeys.orchestration.runsRoot,
        queryFn: () => listRuns(),
    });
    const { data: projects = [] } = useQuery({
        queryKey: queryKeys.orchestration.projects,
        queryFn: listOrchestrationProjects,
    });
    const { data: agents = [] } = useQuery({
        queryKey: queryKeys.orchestration.agents(),
        queryFn: () => listAgents(),
    });
    const { data: syncEvents = [], isLoading: syncLoading } = useQuery({
        queryKey: queryKeys.orchestration.githubSyncEvents,
        queryFn: () => listGithubSyncEvents(),
    });
    const { data: auditLogs = [], isLoading: auditLoading } = useQuery({
        queryKey: queryKeys.orchestration.hitlAuditLogs,
        queryFn: () => listHITLAuditLogs(),
    });

    const fromMs = parseDateBoundary(dateFrom, false);
    const toMs = parseDateBoundary(dateTo, true);

    const filterByDate = useCallback((iso: string) => {
        const t = new Date(iso).getTime();
        if (fromMs != null && t < fromMs) return false;
        if (toMs != null && t > toMs) return false;
        return true;
    }, [fromMs, toMs]);

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
    }, [approvals, agentFilter, projectFilter, filterByDate, runs]);

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
    }, [runs, projectFilter, agentFilter, filterByDate]);

    const filteredSync = useMemo(() => {
        return syncEvents.filter((e) => filterByDate(e.created_at));
    }, [syncEvents, filterByDate]);

    const filteredAuditLogs = useMemo(() => {
        return auditLogs.filter((log: HITLAuditLog) => {
            if (!filterByDate(log.created_at)) return false;
            const projectId = log.metadata.project_id as string | undefined;
            return !projectFilter || projectId === projectFilter;
        });
    }, [auditLogs, filterByDate, projectFilter]);

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

    useEffect(() => {
        setQueueIndex((idx) => (pending.length === 0 ? 0 : Math.min(idx, pending.length - 1)));
    }, [pending.length]);

    const queueDecide = useMutation({
        mutationFn: ({ id, status }: { id: string; status: "approved" | "rejected" }) =>
            decideApproval(id, { status, reason: status === "rejected" ? "Rejected via keyboard shortcut" : undefined }),
        onSuccess: async (_, vars) => {
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.approvals });
            showToast({
                message: vars.status === "approved" ? "Approved — next item focused." : "Rejected.",
                severity: vars.status === "approved" ? "success" : "warning",
            });
        },
        onError: (error) =>
            showToast({ message: error instanceof Error ? error.message : "Decision failed.", severity: "error" }),
    });

    useEffect(() => {
        const onKey = (event: KeyboardEvent) => {
            if (mainTab !== "approvals" || approvalSubTab !== "pending" || pending.length === 0) return;
            const target = event.target as HTMLElement | null;
            const tag = target?.tagName?.toLowerCase();
            if (tag === "input" || tag === "textarea" || target?.isContentEditable) return;
            if (event.key === "j" || event.key === "ArrowDown") {
                event.preventDefault();
                setQueueIndex((i) => Math.min(i + 1, pending.length - 1));
            } else if (event.key === "k" || event.key === "ArrowUp") {
                event.preventDefault();
                setQueueIndex((i) => Math.max(i - 1, 0));
            } else if (event.key === "a" || event.key === "A") {
                const item = pending[queueIndex];
                if (!item || queueDecide.isPending) return;
                event.preventDefault();
                queueDecide.mutate({ id: item.id, status: "approved" });
            } else if (event.key === "r" || event.key === "R") {
                const item = pending[queueIndex];
                if (!item || queueDecide.isPending) return;
                event.preventDefault();
                queueDecide.mutate({ id: item.id, status: "rejected" });
            }
        };
        window.addEventListener("keydown", onKey);
        return () => window.removeEventListener("keydown", onKey);
    }, [mainTab, approvalSubTab, pending, queueIndex, queueDecide]);

    return (
        <PageShell variant="browse">
            <PageHeader
                title="Approvals"
                description="Decide pending requests, then browse the ledger or HITL audit log. This is the action queue — not My tasks."
                actions={
                    <Button variant="outlined" onClick={() => navigate("/my-tasks")}>
                        My tasks
                    </Button>
                }
            />

            <Paper sx={{ p: 2, borderRadius: 1 }}>
                <Stack spacing={2}>
                    <Typography variant="body2" color="text.secondary">
                        Queue tip: decide pending cards first. Keys: j/k move · a approve · r reject (when not typing). Ledger and Audit are history.
                    </Typography>
                    <FilterToolbar>
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
                            label="Project"
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
                    </FilterToolbar>
                </Stack>
            </Paper>

            <Paper sx={{ mb: 2, borderRadius: 4, p: 1 }}>
                <Tabs value={mainTab} onChange={(_, v) => setMainTab(v)}>
                    <Tab label="Approvals" value="approvals" />
                    <Tab label={`Run ledger (${filteredRuns.length})`} value="ledger" />
                    <Tab label={`HITL audit (${filteredAuditLogs.length})`} value="audit" />
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
                                {pending.map((approval, index) => (
                                    <ApprovalCard
                                        key={approval.id}
                                        approval={approval}
                                        focused={index === queueIndex}
                                        onFocusCard={() => setQueueIndex(index)}
                                    />
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
                                <Paper key={run.id} sx={{ p: 2, borderRadius: 1 }}>
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
                                <Paper key={event.id} sx={{ p: 1.5, borderRadius: 1 }}>
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

            {mainTab === "audit" && (
                <SectionCard
                    title="Human-in-the-loop audit log"
                    description="Approval requests, decisions, and project control changes. Sensitive payload values are intentionally excluded."
                >
                    {auditLoading && <CircularProgress size={22} />}
                    <Stack spacing={1.25}>
                        {filteredAuditLogs.map((log) => (
                            <Paper key={log.id} variant="outlined" sx={{ p: 1.5, borderRadius: 1 }}>
                                <Stack direction={{ xs: "column", sm: "row" }} spacing={1} justifyContent="space-between">
                                    <Box>
                                        <Typography variant="body2">{humanizeKey(log.action)}</Typography>
                                        <Typography variant="caption" color="text.secondary">
                                            {log.resource_type ?? "resource"}{log.resource_id ? ` • ${log.resource_id.slice(0, 8)}` : ""}
                                        </Typography>
                                    </Box>
                                    <Typography variant="caption" color="text.secondary">{formatDateTime(log.created_at)}</Typography>
                                </Stack>
                                {Object.keys(log.metadata).length > 0 && (
                                    <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.75 }}>
                                        {Object.entries(log.metadata).map(([key, value]) => `${humanizeKey(key)}: ${String(value)}`).join(" • ")}
                                    </Typography>
                                )}
                            </Paper>
                        ))}
                        {filteredAuditLogs.length === 0 && !auditLoading && (
                            <Typography variant="body2" color="text.secondary">No HITL audit entries match the current filters.</Typography>
                        )}
                    </Stack>
                </SectionCard>
            )}
        </PageShell>
    );
}
