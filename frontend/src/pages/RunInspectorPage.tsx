import { useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
    Alert,
    Box,
    Button,
    Chip,
    CircularProgress,
    Collapse,
    Divider,
    IconButton,
    Paper,
    Skeleton,
    Stack,
    Tab,
    Tabs,
    TextField,
    Tooltip,
    Typography,
} from "@mui/material";
import { alpha } from "@mui/material/styles";
import {
    CheckCircleOutline as DoneIcon,
    Cancel as CancelIcon,
    Error as ErrorIcon,
    HourglassEmpty as QueuedIcon,
    PlayArrow as RunningIcon,
    ExpandMore as ExpandMoreIcon,
    ExpandLess as ExpandLessIcon,
    Replay as ReplayIcon,
    SmartToy as AgentIcon,
    Psychology as ModelIcon,
    Build as ToolIcon,
} from "@mui/icons-material";
import {
    cancelRun,
    getRun,
    getRunCostSummary,
    getRunExecutionState,
    getRunExplanation,
    getRunWorkingMemory,
    listRunEvents,
    patchRunWorkingMemory,
    resumeRun,
    replayRun,
    type RunCostSummary,
    type RunEvent,
    type RunExecutionSnapshot,
    type RunTraceStep,
    type TaskRun,
    type WorkingMemory,
} from "../api/orchestration";
import { readOrchestrationSelectionMeta } from "../utils/orchestrationSelection";
import { PageHeader } from "../components/ui/PageHeader";
import { PageShell } from "../components/ui/PageShell";
import { SectionCard } from "../components/ui/SectionCard";
import { formatDateTime, humanizeKey } from "../utils/formatters";

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "http://localhost:8000/api/v1";

function readCookie(name: string): string | null {
    const match = document.cookie.match(
        new RegExp(`(?:^|; )${name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}=([^;]*)`)
    );
    return match ? decodeURIComponent(match[1]) : null;
}

function RunStatusChip({ status }: { status: string }) {
    const map: Record<string, { color: "success" | "error" | "warning" | "info" | "default"; icon: React.ReactElement | null }> = {
        completed: { color: "success", icon: <DoneIcon fontSize="small" /> },
        failed: { color: "error", icon: <ErrorIcon fontSize="small" /> },
        cancelled: { color: "default", icon: <CancelIcon fontSize="small" /> },
        in_progress: { color: "info", icon: <RunningIcon fontSize="small" /> },
        queued: { color: "warning", icon: <QueuedIcon fontSize="small" /> },
    };
    const { color, icon } = map[status] ?? { color: "default" as const, icon: null };
    return <Chip icon={icon ?? undefined} label={humanizeKey(status)} color={color} size="small" />;
}

function EventLevelColor(level: string) {
    if (level === "error") return "error";
    if (level === "warning") return "warning";
    if (level === "success") return "success";
    return "info";
}

/** Detect if an event is a collapsible agent/model/tool block */
function blockType(event: RunEvent): "agent" | "model" | "tool_call" | "tool_response" | null {
    const t = event.event_type;
    if (t === "agent_message" || t === "agent_output") return "agent";
    if (t === "llm_request" || t === "llm_response" || t === "model_response") return "model";
    if (t === "tool_call") return "tool_call";
    if (t === "tool_result" || t === "tool_response") return "tool_response";
    return null;
}

function blockIcon(type: ReturnType<typeof blockType>) {
    if (type === "agent") return <AgentIcon fontSize="small" />;
    if (type === "model") return <ModelIcon fontSize="small" />;
    if (type === "tool_call" || type === "tool_response") return <ToolIcon fontSize="small" />;
    return null;
}

function formatDelta(ms: number): string {
    if (ms < 1000) return `+${ms}ms`;
    return `+${(ms / 1000).toFixed(1)}s`;
}

function RunEventRow({
    event,
    prevTime,
    index,
    modelRationale,
}: {
    event: RunEvent;
    prevTime: number | null;
    index: number;
    modelRationale?: string;
}) {
    const [open, setOpen] = useState(true);
    const color = EventLevelColor(event.level);
    const hasPayload = event.payload && Object.keys(event.payload).length > 0;
    const bType = blockType(event);
    const isCollapsible = bType !== null;
    const deltaMs = prevTime !== null ? new Date(event.created_at).getTime() - prevTime : null;
    const hasTokens = (event.input_tokens ?? 0) > 0 || (event.output_tokens ?? 0) > 0;

    return (
        <Box
            sx={(theme) => ({
                px: 2,
                py: 1,
                borderRadius: 2,
                backgroundColor: alpha(
                    color === "error" ? theme.palette.error.main
                        : color === "warning" ? theme.palette.warning.main
                        : color === "success" ? theme.palette.success.main
                        : theme.palette.info.main,
                    0.06
                ),
                borderLeft: `3px solid ${
                    color === "error" ? theme.palette.error.main
                        : color === "warning" ? theme.palette.warning.main
                        : color === "success" ? theme.palette.success.main
                        : theme.palette.info.main
                }`,
            })}
        >
            <Stack direction="row" spacing={1.5} alignItems="flex-start">
                {/* Index + delta column */}
                <Stack alignItems="flex-end" sx={{ minWidth: 64, pt: 0.2 }}>
                    <Typography variant="caption" color="text.disabled" sx={{ fontFamily: "monospace", fontSize: "0.68rem" }}>
                        #{index + 1}
                    </Typography>
                    {deltaMs !== null && (
                        <Typography variant="caption" color="text.disabled" sx={{ fontSize: "0.65rem" }}>
                            {formatDelta(deltaMs)}
                        </Typography>
                    )}
                </Stack>

                <Box flex={1}>
                    <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                        {bType && blockIcon(bType)}
                        {bType === "model" && modelRationale ? (
                            <Tooltip title={modelRationale}>
                                <Chip label={humanizeKey(event.event_type)} size="small" variant="outlined" />
                            </Tooltip>
                        ) : (
                            <Chip label={humanizeKey(event.event_type)} size="small" variant="outlined" />
                        )}
                        <Typography variant="body2" sx={{ flex: 1 }}>{event.message}</Typography>
                        {hasTokens && (
                            <Tooltip title={`In: ${event.input_tokens} / Out: ${event.output_tokens}`}>
                                <Chip
                                    label={`${(event.input_tokens ?? 0) + (event.output_tokens ?? 0)} tok`}
                                    size="small"
                                    color="secondary"
                                    variant="outlined"
                                    sx={{ fontSize: "0.65rem" }}
                                />
                            </Tooltip>
                        )}
                        {(event.cost_usd_micros ?? 0) > 0 && (
                            <Chip
                                label={`$${((event.cost_usd_micros ?? 0) / 1_000_000).toFixed(5)}`}
                                size="small"
                                variant="outlined"
                                sx={{ fontSize: "0.65rem" }}
                            />
                        )}
                        <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: "nowrap" }}>
                            {formatDateTime(event.created_at)}
                        </Typography>
                        {isCollapsible && (
                            <IconButton size="small" onClick={() => setOpen((v) => !v)} sx={{ p: 0.25 }}>
                                {open ? <ExpandLessIcon fontSize="small" /> : <ExpandMoreIcon fontSize="small" />}
                            </IconButton>
                        )}
                    </Stack>

                    <Collapse in={!isCollapsible || open}>
                        {hasPayload && (
                            <Typography
                                variant="caption"
                                color="text.secondary"
                                component="pre"
                                sx={{ mt: 0.5, whiteSpace: "pre-wrap", wordBreak: "break-all", maxHeight: 300, overflow: "auto" }}
                            >
                                {JSON.stringify(event.payload, null, 2)}
                            </Typography>
                        )}
                    </Collapse>
                </Box>
            </Stack>
        </Box>
    );
}

function ToolCallPair({ call, response }: { call: RunEvent; response: RunEvent | null }) {
    const [open, setOpen] = useState(false);
    return (
        <Paper
            sx={(theme) => ({
                p: 1.5,
                borderRadius: 3,
                border: `1px solid ${theme.palette.divider}`,
                ml: 4,
                mr: 0,
            })}
        >
            <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.5 }}>
                <ToolIcon fontSize="small" color="warning" />
                <Chip label="Tool call" size="small" color="warning" variant="outlined" />
                <Typography variant="caption" color="text.secondary" sx={{ ml: "auto" }}>
                    {formatDateTime(call.created_at)}
                </Typography>
                <IconButton size="small" onClick={() => setOpen((v) => !v)} sx={{ p: 0.25 }}>
                    {open ? <ExpandLessIcon fontSize="small" /> : <ExpandMoreIcon fontSize="small" />}
                </IconButton>
            </Stack>
            <Typography variant="body2">{call.message}</Typography>
            <Collapse in={open}>
                {call.payload && Object.keys(call.payload).length > 0 && (
                    <Typography variant="caption" component="pre" sx={{ display: "block", mt: 1, whiteSpace: "pre-wrap", wordBreak: "break-all" }}>
                        {JSON.stringify(call.payload, null, 2)}
                    </Typography>
                )}
                {response && (
                    <Box sx={{ mt: 1.5, pt: 1.5, borderTop: 1, borderColor: "divider" }}>
                        <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.5 }}>
                            <Chip label={humanizeKey(response.event_type)} size="small" variant="outlined" />
                            <Typography variant="caption" color="text.secondary">{formatDateTime(response.created_at)}</Typography>
                        </Stack>
                        <Typography variant="body2">{response.message}</Typography>
                        {response.payload && Object.keys(response.payload).length > 0 && (
                            <Typography variant="caption" component="pre" sx={{ display: "block", mt: 0.75, whiteSpace: "pre-wrap", wordBreak: "break-all" }}>
                                {JSON.stringify(response.payload, null, 2)}
                            </Typography>
                        )}
                    </Box>
                )}
            </Collapse>
        </Paper>
    );
}

/** Render the agent conversation: agent_message / llm_request / tool_call + tool_response pairs */
function ConversationViewer({ events, modelRationale }: { events: RunEvent[]; modelRationale?: string }) {
    const convoTypes = new Set(["agent_message", "agent_output", "llm_request", "llm_response", "model_response", "tool_call", "tool_result", "tool_response"]);
    const convo = events.filter((e) => convoTypes.has(e.event_type));

    if (convo.length === 0) {
        return (
            <Typography variant="body2" color="text.secondary">
                No agent conversation events recorded in this run.
            </Typography>
        );
    }

    type Row =
        | { kind: "tool_pair"; key: string; call: RunEvent; response: RunEvent | null }
        | { kind: "single"; event: RunEvent };

    const rows: Row[] = [];
    for (let i = 0; i < convo.length; i++) {
        const event = convo[i];
        if (event.event_type === "tool_call") {
            const next = convo[i + 1];
            if (next && (next.event_type === "tool_result" || next.event_type === "tool_response")) {
                rows.push({ kind: "tool_pair", key: `${event.id}-${next.id}`, call: event, response: next });
                i += 1;
            } else {
                rows.push({ kind: "tool_pair", key: event.id, call: event, response: null });
            }
            continue;
        }
        if (event.event_type === "tool_result" || event.event_type === "tool_response") {
            rows.push({ kind: "single", event });
            continue;
        }
        rows.push({ kind: "single", event });
    }

    return (
        <Stack spacing={1}>
            {rows.map((row) => {
                if (row.kind === "tool_pair") {
                    return <ToolCallPair key={row.key} call={row.call} response={row.response} />;
                }
                const event = row.event;
                const isAgent = event.event_type === "agent_message" || event.event_type === "agent_output";
                const isModel = event.event_type.startsWith("llm_") || event.event_type === "model_response";
                const isTool = event.event_type.startsWith("tool_");
                return (
                    <ConversationBubble
                        key={event.id}
                        event={event}
                        isAgent={isAgent}
                        isModel={isModel}
                        isTool={isTool}
                        modelRationale={modelRationale}
                    />
                );
            })}
        </Stack>
    );
}

function ConversationBubble({
    event,
    isAgent,
    isModel,
    isTool,
    modelRationale,
}: {
    event: RunEvent;
    isAgent: boolean;
    isModel: boolean;
    isTool: boolean;
    modelRationale?: string;
}) {
    const [open, setOpen] = useState(true);
    const hasPayload = event.payload && Object.keys(event.payload).length > 0;

    let bgKey: "primary" | "secondary" | "warning" = "secondary";
    let label = humanizeKey(event.event_type);
    let icon = <ModelIcon fontSize="small" />;
    if (isAgent) { bgKey = "primary"; icon = <AgentIcon fontSize="small" />; label = "Agent"; }
    if (isTool) { bgKey = "warning"; icon = <ToolIcon fontSize="small" />; label = humanizeKey(event.event_type); }

    return (
        <Paper
            sx={(theme) => ({
                p: 1.5,
                borderRadius: 3,
                border: `1px solid ${theme.palette.divider}`,
                ml: isAgent ? 0 : isModel ? 2 : 4,
                mr: isAgent ? 4 : 0,
            })}
        >
            <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: hasPayload ? 0.75 : 0 }}>
                {icon}
                {isModel && modelRationale ? (
                    <Tooltip title={modelRationale}>
                        <Chip label={label} size="small" color={bgKey} variant="outlined" />
                    </Tooltip>
                ) : (
                    <Chip label={label} size="small" color={bgKey} variant="outlined" />
                )}
                <Typography variant="caption" color="text.secondary" sx={{ ml: "auto" }}>
                    {formatDateTime(event.created_at)}
                </Typography>
                {(event.input_tokens ?? 0) + (event.output_tokens ?? 0) > 0 && (
                    <Chip
                        label={`${event.input_tokens ?? 0}↑ ${event.output_tokens ?? 0}↓`}
                        size="small"
                        variant="outlined"
                        sx={{ fontSize: "0.65rem" }}
                    />
                )}
                {hasPayload && (
                    <IconButton size="small" onClick={() => setOpen((v) => !v)} sx={{ p: 0.25 }}>
                        {open ? <ExpandLessIcon fontSize="small" /> : <ExpandMoreIcon fontSize="small" />}
                    </IconButton>
                )}
            </Stack>
            <Typography variant="body2" sx={{ mb: hasPayload ? 0.5 : 0 }}>{event.message}</Typography>
            <Collapse in={open}>
                {hasPayload && (
                    <Box
                        sx={(theme) => ({
                            p: 1,
                            borderRadius: 1.5,
                            bgcolor: alpha(theme.palette.background.default, 0.7),
                            fontFamily: "monospace",
                            fontSize: "0.75rem",
                            whiteSpace: "pre-wrap",
                            wordBreak: "break-all",
                            maxHeight: 250,
                            overflow: "auto",
                        })}
                    >
                        {JSON.stringify(event.payload, null, 2)}
                    </Box>
                )}
            </Collapse>
        </Paper>
    );
}

function RunMeta({ run, costSummary, selection }: { run: TaskRun; costSummary?: RunCostSummary | null; selection: ReturnType<typeof readOrchestrationSelectionMeta> }) {
    const costUsd = run.estimated_cost_micros > 0
        ? `$${(run.estimated_cost_micros / 1_000_000).toFixed(4)}`
        : "—";
    const workerWhy = selection.worker_agent_rationale;
    const modelWhy = selection.model_rationale;

    return (
        <Box
            sx={(theme) => ({
                p: 2,
                borderRadius: 4,
                border: `1px solid ${theme.palette.divider}`,
                backgroundColor: alpha(theme.palette.background.paper, 0.7),
            })}
        >
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                <RunStatusChip status={run.status} />
                <Chip label={humanizeKey(run.run_mode)} variant="outlined" size="small" />
                {run.worker_agent_id && (
                    <Tooltip title={workerWhy || "No routing notes were stored for this run."}>
                        <Chip icon={<AgentIcon fontSize="small" />} label="Worker agent" variant="outlined" size="small" />
                    </Tooltip>
                )}
                {run.model_name && (
                    <Tooltip title={modelWhy || "No model routing notes were stored for this run."}>
                        <Chip icon={<ModelIcon fontSize="small" />} label={run.model_name} variant="outlined" size="small" />
                    </Tooltip>
                )}
                {!run.model_name && (
                    <Tooltip title={modelWhy || "Model chosen at runtime."}>
                        <Chip icon={<ModelIcon fontSize="small" />} label="Model (runtime)" variant="outlined" size="small" />
                    </Tooltip>
                )}
                <Chip label={`${run.token_total.toLocaleString()} tokens`} variant="outlined" size="small" />
                <Chip label={run.latency_ms != null ? `${run.latency_ms} ms` : "—"} variant="outlined" size="small" />
                <Tooltip
                    title={
                        costSummary
                            ? `Run estimate: $${costSummary.estimated_cost_usd.toFixed(5)} · Sum of event costs: $${costSummary.event_cost_sum_usd.toFixed(5)}`
                            : "Estimated run cost (server-side)."
                    }
                >
                    <Chip label={costUsd} variant="outlined" size="small" />
                </Tooltip>
                {run.attempt_number > 1 && (
                    <Chip label={`Attempt ${run.attempt_number}`} color="warning" variant="outlined" size="small" />
                )}
            </Stack>
            <Stack direction="row" spacing={3} sx={{ mt: 1.5 }} flexWrap="wrap" useFlexGap>
                <Box>
                    <Typography variant="caption" color="text.secondary">Started</Typography>
                    <Typography variant="body2">{run.started_at ? formatDateTime(run.started_at) : "—"}</Typography>
                </Box>
                <Box>
                    <Typography variant="caption" color="text.secondary">Completed</Typography>
                    <Typography variant="body2">{run.completed_at ? formatDateTime(run.completed_at) : "—"}</Typography>
                </Box>
                <Box>
                    <Typography variant="caption" color="text.secondary">Input tokens</Typography>
                    <Typography variant="body2">{run.token_input.toLocaleString()}</Typography>
                </Box>
                <Box>
                    <Typography variant="caption" color="text.secondary">Output tokens</Typography>
                    <Typography variant="body2">{run.token_output.toLocaleString()}</Typography>
                </Box>
                {costSummary && (
                    <Box>
                        <Typography variant="caption" color="text.secondary">Cost (events sum)</Typography>
                        <Typography variant="body2">${costSummary.event_cost_sum_usd.toFixed(5)}</Typography>
                    </Box>
                )}
                {run.checkpoint_json && Object.keys(run.checkpoint_json).length > 0 && (
                    <Box>
                        <Typography variant="caption" color="text.secondary">Checkpoint</Typography>
                        <Typography variant="body2" sx={{ fontFamily: "monospace", fontSize: "0.75rem" }}>
                            {JSON.stringify(run.checkpoint_json)}
                        </Typography>
                    </Box>
                )}
            </Stack>
            {run.error_message && (
                <Alert severity="error" sx={{ mt: 1.5 }}>{run.error_message}</Alert>
            )}
        </Box>
    );
}

const TERMINAL = new Set(["completed", "failed", "cancelled", "blocked"]);

function readTraceSteps(snapshot: RunExecutionSnapshot | undefined, events: RunEvent[]): RunTraceStep[] {
    for (let i = events.length - 1; i >= 0; i -= 1) {
        const candidate = events[i]?.payload?.trace;
        if (Array.isArray(candidate)) {
            return candidate as RunTraceStep[];
        }
    }
    return snapshot?.trace ?? [];
}

function RunTraceView({ trace }: { trace: RunTraceStep[] }) {
    if (trace.length === 0) {
        return <Typography variant="body2" color="text.secondary">No durable trace recorded yet.</Typography>;
    }
    return (
        <Stack spacing={1}>
            {trace.map((step) => (
                <Paper
                    key={step.step_id}
                    variant="outlined"
                    sx={(theme) => ({
                        p: 1.5,
                        borderRadius: 2,
                        borderColor: step.is_current ? theme.palette.info.main : undefined,
                    })}
                >
                    <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={1}>
                        <Box>
                            <Typography variant="subtitle2">{step.sequence}. {step.title}</Typography>
                            <Typography variant="caption" color="text.secondary">
                                {humanizeKey(step.actor)} · attempts {step.attempts}
                            </Typography>
                        </Box>
                        <Chip
                            size="small"
                            color={
                                step.status === "completed"
                                    ? "success"
                                    : step.status === "failed"
                                      ? "error"
                                      : step.status === "blocked"
                                        ? "warning"
                                        : step.status === "in_progress"
                                          ? "info"
                                          : "default"
                            }
                            label={humanizeKey(step.status)}
                        />
                    </Stack>
                    {(step.started_at || step.completed_at || step.last_error) && (
                        <Stack spacing={0.5} sx={{ mt: 1 }}>
                            {step.started_at && (
                                <Typography variant="caption" color="text.secondary">
                                    Started {formatDateTime(step.started_at)}
                                </Typography>
                            )}
                            {step.completed_at && (
                                <Typography variant="caption" color="text.secondary">
                                    Completed {formatDateTime(step.completed_at)}
                                </Typography>
                            )}
                            {step.last_error && <Alert severity="warning">{step.last_error}</Alert>}
                        </Stack>
                    )}
                </Paper>
            ))}
        </Stack>
    );
}

function WorkflowGraphView({ trace }: { trace: RunTraceStep[] }) {
    if (trace.length === 0) {
        return <Typography variant="body2" color="text.secondary">No workflow steps recorded yet.</Typography>;
    }
    const edges = trace.slice(1).map((step, idx) => ({
        from: trace[idx],
        to: step,
    }));
    return (
        <Stack spacing={1}>
            {edges.map((edge, idx) => (
                <Paper key={`${edge.from.step_id}-${edge.to.step_id}-${idx}`} sx={{ p: 1.25, borderRadius: 2, border: 1, borderColor: "divider" }}>
                    <Typography variant="body2">
                        <strong>{humanizeKey(edge.from.step_id)}</strong> {" -> "} <strong>{humanizeKey(edge.to.step_id)}</strong>
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                        {humanizeKey(edge.from.status)} {" -> "} {humanizeKey(edge.to.status)}
                    </Typography>
                </Paper>
            ))}
        </Stack>
    );
}

export default function RunInspectorPage() {
    const { runId } = useParams<{ runId: string }>();
    const navigate = useNavigate();
    const queryClient = useQueryClient();
    const [events, setEvents] = useState<RunEvent[]>([]);
    const [streaming, setStreaming] = useState(false);
    const [streamError, setStreamError] = useState<string | null>(null);
    const [tab, setTab] = useState<"timeline" | "trace" | "graph" | "conversation">("timeline");
    const [replayModelName, setReplayModelName] = useState("");
    const bottomRef = useRef<HTMLDivElement>(null);
    const abortRef = useRef<AbortController | null>(null);

    const { data: run, isLoading } = useQuery({
        queryKey: ["orchestration", "run", runId],
        queryFn: () => getRun(runId!),
        enabled: !!runId,
        refetchInterval: (query) => {
            const r = query.state.data as TaskRun | undefined;
            return r && TERMINAL.has(r.status) ? false : 3000;
        },
    });

    const { data: costSummary } = useQuery({
        queryKey: ["orchestration", "run", runId, "cost"],
        queryFn: () => getRunCostSummary(runId!),
        enabled: Boolean(runId),
    });

    const { data: execSnapshot, isLoading: execSnapshotLoading } = useQuery({
        queryKey: ["orchestration", "run", runId, "execution-state"],
        queryFn: () => getRunExecutionState(runId!),
        enabled: Boolean(runId),
        refetchInterval: (query) => {
            const snap = query.state.data as RunExecutionSnapshot | undefined;
            const st = snap?.run?.status;
            return st && TERMINAL.has(st) ? false : 4000;
        },
    });
    const { data: runExplanation } = useQuery({
        queryKey: ["orchestration", "run", runId, "explanation"],
        queryFn: () => getRunExplanation(runId!),
        enabled: Boolean(runId),
    });

    const { data: workingMemory } = useQuery({
        queryKey: ["orchestration", "run", runId, "working-memory"],
        queryFn: () => getRunWorkingMemory(runId!),
        enabled: Boolean(runId),
    });

    const [wmObjective, setWmObjective] = useState("");
    const [wmFindings, setWmFindings] = useState("");
    const [wmQuestions, setWmQuestions] = useState("");

    useEffect(() => {
        if (!workingMemory) return;
        setWmObjective(workingMemory.objective);
        setWmFindings(workingMemory.latest_findings);
        setWmQuestions(workingMemory.open_questions);
    }, [workingMemory]);

    const wmPatchMutation = useMutation({
        mutationFn: (patch: Partial<Pick<WorkingMemory, "objective" | "latest_findings" | "open_questions">>) =>
            patchRunWorkingMemory(runId!, patch),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "run", runId, "working-memory"] });
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "run", runId, "execution-state"] });
        },
    });

    const cancelMutation = useMutation({
        mutationFn: () => cancelRun(runId!),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "run", runId] });
            await queryClient.invalidateQueries({
                queryKey: ["orchestration", "run", runId, "execution-state"],
            });
            await queryClient.invalidateQueries({
                queryKey: ["orchestration", "run", runId, "working-memory"],
            });
            abortRef.current?.abort();
        },
    });

    const replayMutation = useMutation({
        mutationFn: (fromIndex: number) => replayRun(runId!, {
            from_event_index: fromIndex,
            model_name: replayModelName.trim() || undefined,
        }),
        onSuccess: (newRun) => {
            navigate(`/runs/${newRun.id}`);
        },
    });

    const resumeMutation = useMutation({
        mutationFn: () => resumeRun(runId!),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "run", runId] });
            await queryClient.invalidateQueries({
                queryKey: ["orchestration", "run", runId, "execution-state"],
            });
        },
    });

    // SSE streaming via fetch (supports cookies + CSRF)
    useEffect(() => {
        if (!runId) return;
        if (run && TERMINAL.has(run.status)) {
            listRunEvents(runId).then(setEvents).catch(() => {});
            return;
        }

        const controller = new AbortController();
        abortRef.current = controller;
        setStreaming(true);
        setStreamError(null);

        const csrfToken = readCookie("csrf_token");
        const headers: Record<string, string> = {};
        if (csrfToken) headers["X-CSRF-Token"] = csrfToken;

        (async () => {
            try {
                const response = await fetch(`${API_BASE}/orchestration/runs/${runId}/stream`, {
                    credentials: "include",
                    headers,
                    signal: controller.signal,
                });
                if (!response.ok || !response.body) {
                    setStreamError("Live stream unavailable — showing snapshot.");
                    const snapshot = await listRunEvents(runId);
                    setEvents(snapshot);
                    setStreaming(false);
                    return;
                }
                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let buffer = "";
                const seen = new Set<string>();

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split("\n\n");
                    buffer = lines.pop() ?? "";
                    for (const block of lines) {
                        const inner = block.trim().split("\n").find((line) => line.startsWith("data:"));
                        if (!inner) continue;
                        const raw = inner.slice(5).trim();
                        if (!raw) continue;
                        try {
                            const parsed = JSON.parse(raw) as RunEvent & { event_type?: string; status?: string };
                            if (parsed.event_type === "stream_end") {
                                await queryClient.invalidateQueries({ queryKey: ["orchestration", "run", runId] });
                                setStreaming(false);
                                return;
                            }
                            if (!("id" in parsed) || !parsed.id) continue;
                            if (!seen.has(parsed.id)) {
                                seen.add(parsed.id);
                                setEvents((prev) => [...prev, parsed]);
                            }
                        } catch {
                            // ignore parse errors
                        }
                    }
                }
                setStreaming(false);
            } catch (err) {
                if ((err as Error).name !== "AbortError") {
                    setStreamError("Stream disconnected.");
                    setStreaming(false);
                }
            }
        })();

        return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [runId, run?.status]);

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [events.length]);

    if (isLoading) {
        return (
            <PageShell maxWidth="xl">
                <Stack spacing={2}>
                    <Skeleton variant="rounded" height={80} sx={{ borderRadius: 4 }} />
                    <Skeleton variant="rounded" height={400} sx={{ borderRadius: 4 }} />
                </Stack>
            </PageShell>
        );
    }

    if (!run) return null;

    const isLive = !TERMINAL.has(run.status);
    const isFailed = run.status === "failed";
    const isBlocked = run.status === "blocked";
    const wmEditable = ["queued", "in_progress", "blocked"].includes(run.status);
    const selectionMeta = readOrchestrationSelectionMeta(run);
    const modelRationale = selectionMeta.model_rationale;
    const traceSteps = readTraceSteps(execSnapshot, events);
    const canResume = Boolean(execSnapshot?.resumable) && (isFailed || isBlocked);

    // Build per-event timestamps for delta display
    const eventTimes = events.map((e) => new Date(e.created_at).getTime());

    return (
        <PageShell maxWidth="xl">
            <PageHeader
                eyebrow="Execution"
                title="Run Inspector"
                description={`Execution trace for run ${run.id.slice(0, 8)}…`}
                actions={
                    <Stack direction="row" spacing={1}>
                        <Button variant="outlined" onClick={() => navigate(-1)}>Back</Button>
                        <TextField
                            size="small"
                            label="Replay model override"
                            value={replayModelName}
                            onChange={(e) => setReplayModelName(e.target.value)}
                            placeholder={run.model_name || "Use original model"}
                            sx={{ minWidth: 220 }}
                        />
                        {isLive && (
                            <Button
                                variant="outlined"
                                color="error"
                                onClick={() => cancelMutation.mutate()}
                                disabled={cancelMutation.isPending}
                            >
                                Cancel run
                            </Button>
                        )}
                        {isFailed && (
                            <Button
                                variant="contained"
                                startIcon={replayMutation.isPending ? <CircularProgress size={16} /> : <ReplayIcon />}
                                disabled={replayMutation.isPending}
                                onClick={() => replayMutation.mutate(0)}
                            >
                                Replay from start
                            </Button>
                        )}
                        {isFailed && events.length > 0 && (
                            <Button
                                variant="outlined"
                                startIcon={<ReplayIcon />}
                                disabled={replayMutation.isPending}
                                onClick={() => replayMutation.mutate(Math.max(0, events.length - 3))}
                            >
                                Replay from checkpoint
                            </Button>
                        )}
                        {canResume && (
                            <Button
                                variant="contained"
                                color="warning"
                                disabled={resumeMutation.isPending}
                                onClick={() => resumeMutation.mutate()}
                            >
                                Resume from checkpoint
                            </Button>
                        )}
                    </Stack>
                }
            />

            <RunMeta run={run} costSummary={costSummary ?? null} selection={selectionMeta} />
            {runExplanation && (
                <SectionCard title="Explain this run" description="Plain-English narrative for stakeholders and audit reviews.">
                    <Typography variant="body2">{String(runExplanation.summary ?? "")}</Typography>
                </SectionCard>
            )}

            <SectionCard
                title="Execution snapshot"
                description={
                    execSnapshot
                        ? `Layer 1 · schema ${execSnapshot.meta.schema_version}`
                        : "Authoritative state from Postgres (no vector search)"
                }
            >
                {execSnapshotLoading && !execSnapshot ? (
                    <Skeleton variant="rounded" height={120} sx={{ borderRadius: 2 }} />
                ) : execSnapshot ? (
                    <Stack spacing={1.5}>
                        <Typography variant="body2" color="text.secondary">
                            {execSnapshot.meta.execution_truth}
                        </Typography>
                        <Stack direction="row" flexWrap="wrap" gap={0.5} useFlexGap>
                            {execSnapshot.meta.sources_read.map((s) => (
                                <Chip key={s} size="small" label={s} variant="outlined" />
                            ))}
                        </Stack>
                        {(execSnapshot.pending_approvals.length > 0 ||
                            execSnapshot.pending_github_sync.length > 0) && (
                            <Stack direction="row" flexWrap="wrap" gap={1} useFlexGap>
                                {execSnapshot.pending_approvals.length > 0 && (
                                    <Chip
                                        color="warning"
                                        size="small"
                                        label={`Pending approvals: ${execSnapshot.pending_approvals.length}`}
                                    />
                                )}
                                {execSnapshot.pending_github_sync.length > 0 && (
                                    <Chip
                                        color="info"
                                        size="small"
                                        label={`GitHub sync queue: ${execSnapshot.pending_github_sync.length}`}
                                    />
                                )}
                            </Stack>
                        )}
                        {Object.keys(execSnapshot.checkpoint_excerpt).length > 0 && (
                            <Box
                                component="pre"
                                sx={{
                                    m: 0,
                                    p: 1,
                                    typography: "caption",
                                    bgcolor: (t) => alpha(t.palette.text.primary, 0.04),
                                    overflow: "auto",
                                    maxHeight: 220,
                                }}
                            >
                                {JSON.stringify(execSnapshot.checkpoint_excerpt, null, 2)}
                            </Box>
                        )}
                        {execSnapshot.recent_events_tail.length > 0 && (
                            <Typography variant="caption" color="text.secondary">
                                Recent event types:{" "}
                                {execSnapshot.recent_events_tail.map((e) => e.event_type).join(" → ")}
                            </Typography>
                        )}
                    </Stack>
                ) : (
                    <Typography variant="body2" color="text.secondary">
                        Snapshot unavailable.
                    </Typography>
                )}
            </SectionCard>

            <SectionCard
                title="Working memory"
                description="Layer 2 · structured scratchpad stored on the run checkpoint (bounded fields)."
                sx={{ mt: 2 }}
            >
                <Stack spacing={2}>
                    {!wmEditable && (
                        <Typography variant="caption" color="text.secondary">
                            Editing is only allowed while the run is queued, in progress, or blocked.
                        </Typography>
                    )}
                    <TextField
                        label="Objective"
                        value={wmObjective}
                        onChange={(e) => setWmObjective(e.target.value)}
                        multiline
                        minRows={2}
                        fullWidth
                        disabled={!wmEditable}
                        size="small"
                    />
                    <TextField
                        label="Latest findings"
                        value={wmFindings}
                        onChange={(e) => setWmFindings(e.target.value)}
                        multiline
                        minRows={3}
                        fullWidth
                        disabled={!wmEditable}
                        size="small"
                    />
                    <TextField
                        label="Open questions"
                        value={wmQuestions}
                        onChange={(e) => setWmQuestions(e.target.value)}
                        multiline
                        minRows={2}
                        fullWidth
                        disabled={!wmEditable}
                        size="small"
                    />
                    {workingMemory && (
                        <Typography variant="caption" color="text.secondary">
                            Updated {formatDateTime(workingMemory.updated_at)}
                        </Typography>
                    )}
                    <Button
                        variant="outlined"
                        disabled={!wmEditable || wmPatchMutation.isPending}
                        onClick={() =>
                            wmPatchMutation.mutate({
                                objective: wmObjective,
                                latest_findings: wmFindings,
                                open_questions: wmQuestions,
                            })
                        }
                    >
                        Save working memory
                    </Button>
                </Stack>
            </SectionCard>

            <Box sx={{ borderBottom: 1, borderColor: "divider" }}>
                <Tabs value={tab} onChange={(_, v) => setTab(v)}>
                    <Tab label={`Timeline (${events.length})`} value="timeline" />
                    <Tab label={`Trace (${traceSteps.length})`} value="trace" />
                    <Tab label="Workflow graph" value="graph" />
                    <Tab label="Conversation" value="conversation" />
                </Tabs>
            </Box>

            {tab === "timeline" && (
                <SectionCard
                    title={
                        <Stack direction="row" spacing={1.5} alignItems="center">
                            <Typography variant="h6">Event timeline</Typography>
                            {isLive && streaming && (
                                <Stack direction="row" spacing={0.75} alignItems="center">
                                    <CircularProgress size={14} />
                                    <Typography variant="caption" color="text.secondary">Live</Typography>
                                </Stack>
                            )}
                            {!isLive && <Chip label="Completed" color="success" size="small" />}
                        </Stack>
                    }
                    description="Events emitted during execution with timing deltas and per-event token usage."
                >
                    {streamError && <Alert severity="warning" sx={{ mb: 2 }}>{streamError}</Alert>}
                    {events.length === 0 && !streaming && (
                        <Typography variant="body2" color="text.secondary">No events recorded yet.</Typography>
                    )}
                    <Stack spacing={0.75}>
                        {events.map((event, idx) => (
                            <RunEventRow
                                key={event.id}
                                event={event}
                                prevTime={idx > 0 ? eventTimes[idx - 1] : null}
                                index={idx}
                                modelRationale={modelRationale}
                            />
                        ))}
                        <div ref={bottomRef} />
                    </Stack>
                </SectionCard>
            )}

            {tab === "trace" && (
                <SectionCard
                    title="Execution trace"
                    description="Durable supervisor/worker workflow trace from checkpointed execution steps."
                >
                    <RunTraceView trace={traceSteps} />
                </SectionCard>
            )}

            {tab === "graph" && (
                <SectionCard
                    title="Workflow graph"
                    description="Step-to-step DAG derived from durable trace transitions."
                >
                    <WorkflowGraphView trace={traceSteps} />
                </SectionCard>
            )}

            {tab === "conversation" && (
                <SectionCard
                    title="Agent conversation"
                    description="Full agent ↔ model message exchange. Tool call/response pairs are foldable."
                >
                    <ConversationViewer events={events} modelRationale={modelRationale} />
                </SectionCard>
            )}

            <Divider />

            {run.output_payload && Object.keys(run.output_payload).length > 0 && (
                <SectionCard title="Output" description="Final payload produced by the run.">
                    <Paper
                        sx={(theme) => ({
                            p: 2,
                            borderRadius: 2,
                            backgroundColor: alpha(theme.palette.background.default, 0.6),
                            overflow: "auto",
                        })}
                    >
                        <Typography
                            variant="caption"
                            component="pre"
                            sx={{ whiteSpace: "pre-wrap", wordBreak: "break-all" }}
                        >
                            {JSON.stringify(run.output_payload, null, 2)}
                        </Typography>
                    </Paper>
                </SectionCard>
            )}

            {run.output_payload && Boolean((run.output_payload as Record<string, unknown>)["final_output"]) && (
                <SectionCard title="Agent output" description="Human-readable final output from the agent.">
                    <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>
                        {String((run.output_payload as Record<string, unknown>)["final_output"] ?? "")}
                    </Typography>
                </SectionCard>
            )}
        </PageShell>
    );
}
