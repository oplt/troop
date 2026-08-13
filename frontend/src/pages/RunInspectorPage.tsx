import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
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
    MenuItem,
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
    SmartToy as AgentIcon,
    Psychology as ModelIcon,
    Build as ToolIcon,
} from "@mui/icons-material";
import {
    getRun,
    getRunCostSummary,
    getRunExecutionState,
    getRunExplanation,
    getRunWorkingMemory,
    listRunEvents,
    patchRunWorkingMemory,
    signalRunWorkflow,
    type RunCostSummary,
    type RunEvent,
    type RunExecutionSnapshot,
    type RunTraceStep,
    type TaskRun,
    type WorkingMemory,
} from "../api/orchestration";
import { readOrchestrationSelectionMeta } from "../utils/orchestrationSelection";
import {
    CheckpointFriendlySummary,
    CollapsibleRawJson,
    EventPayloadFriendly,
    RunOutputFriendly,
    ShallowKeyValueList,
} from "../components/runInspector/RunInspectorDataViews";
import { PageShell } from "../components/ui/PageShell";
import { SectionCard } from "../components/ui/SectionCard";
import { formatDateTime, humanizeKey } from "../utils/formatters";
import { queryKeys } from "../config/queryKeys";
import { useSseStream } from "../hooks/useSseStream";
import { safeRunValue } from "../features/workflows/builderState";

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
                borderRadius: 1,
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
                            <Box sx={{ mt: 0.75 }}>
                                <EventPayloadFriendly payload={event.payload as Record<string, unknown>} />
                            </Box>
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
                borderRadius: 1,
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
                    <Box sx={{ mt: 1 }}>
                        <EventPayloadFriendly payload={call.payload as Record<string, unknown>} />
                    </Box>
                )}
                {response && (
                    <Box sx={{ mt: 1.5, pt: 1.5, borderTop: 1, borderColor: "divider" }}>
                        <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.5 }}>
                            <Chip label={humanizeKey(response.event_type)} size="small" variant="outlined" />
                            <Typography variant="caption" color="text.secondary">{formatDateTime(response.created_at)}</Typography>
                        </Stack>
                        <Typography variant="body2">{response.message}</Typography>
                        {response.payload && Object.keys(response.payload).length > 0 && (
                            <Box sx={{ mt: 0.75 }}>
                                <EventPayloadFriendly payload={response.payload as Record<string, unknown>} />
                            </Box>
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
                borderRadius: 1,
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
                            p: 1.25,
                            borderRadius: 1.5,
                            bgcolor: alpha(theme.palette.background.default, 0.7),
                            border: `1px solid ${theme.palette.divider}`,
                        })}
                    >
                        <EventPayloadFriendly payload={event.payload as Record<string, unknown>} />
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
                    <Box sx={{ minWidth: 0, maxWidth: "100%" }}>
                        <Typography variant="caption" color="text.secondary">Checkpoint</Typography>
                        <CheckpointFriendlySummary checkpoint={run.checkpoint_json as Record<string, unknown>} />
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
const MAX_RENDERED_EVENTS = 2_000;

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
                        borderRadius: 1,
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
                    {Object.keys(step.metadata ?? {}).length > 0 && (
                        <Box component="pre" sx={{ mt: 1, mb: 0, p: 1, bgcolor: "action.hover", borderRadius: 1, overflow: "auto", whiteSpace: "pre-wrap", fontSize: "0.72rem" }}>
                            {JSON.stringify(safeRunValue(step.metadata), null, 2)}
                        </Box>
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
                <Paper key={`${edge.from.step_id}-${edge.to.step_id}-${idx}`} sx={{ p: 1.25, borderRadius: 1, border: 1, borderColor: "divider" }}>
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
    const queryClient = useQueryClient();
    const [events, setEvents] = useState<RunEvent[]>([]);
    const [streamError, setStreamError] = useState<string | null>(null);
    const [tab, setTab] = useState<"timeline" | "trace" | "graph" | "conversation">("timeline");
    const bottomRef = useRef<HTMLDivElement>(null);

    const { data: run, isLoading } = useQuery({
        queryKey: queryKeys.runs.detail(runId ?? ""),
        queryFn: () => getRun(runId!),
        enabled: !!runId,
        refetchInterval: (query) => {
            const r = query.state.data as TaskRun | undefined;
            return r && TERMINAL.has(r.status) ? false : 3000;
        },
    });

    const { data: costSummary } = useQuery({
        queryKey: queryKeys.runs.cost(runId ?? ""),
        queryFn: () => getRunCostSummary(runId!),
        enabled: Boolean(runId),
    });

    const { data: execSnapshot, isLoading: execSnapshotLoading } = useQuery({
        queryKey: queryKeys.runs.executionState(runId ?? ""),
        queryFn: () => getRunExecutionState(runId!),
        enabled: Boolean(runId),
        refetchInterval: (query) => {
            const snap = query.state.data as RunExecutionSnapshot | undefined;
            const st = snap?.run?.status;
            return st && TERMINAL.has(st) ? false : 4000;
        },
    });
    const { data: runExplanation } = useQuery({
        queryKey: queryKeys.runs.explanation(runId ?? ""),
        queryFn: () => getRunExplanation(runId!),
        enabled: Boolean(runId),
    });

    const { data: workingMemory } = useQuery({
        queryKey: queryKeys.runs.workingMemory(runId ?? ""),
        queryFn: () => getRunWorkingMemory(runId!),
        enabled: Boolean(runId),
    });

    const [wmDraft, setWmDraft] = useState<Partial<Pick<WorkingMemory, "objective" | "latest_findings" | "open_questions">>>({});
    const [signalName, setSignalName] = useState("add_note");
    const [signalPayload, setSignalPayload] = useState("{\n  \"note\": \"\"\n}");

    const wmPatchMutation = useMutation({
        mutationFn: (patch: Partial<Pick<WorkingMemory, "objective" | "latest_findings" | "open_questions">>) =>
            patchRunWorkingMemory(runId!, patch),
        onSuccess: async () => {
            setWmDraft({});
            await queryClient.invalidateQueries({ queryKey: queryKeys.runs.workingMemory(runId ?? "") });
            await queryClient.invalidateQueries({ queryKey: queryKeys.runs.executionState(runId ?? "") });
        },
    });

    const signalMutation = useMutation({
        mutationFn: async () => {
            let parsedPayload: Record<string, unknown> = {};
            try {
                parsedPayload = signalPayload.trim() ? JSON.parse(signalPayload) as Record<string, unknown> : {};
            } catch {
                throw new Error("Signal payload must be valid JSON.");
            }
            return signalRunWorkflow(runId!, { signal_name: signalName, payload: parsedPayload });
        },
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: queryKeys.runs.executionState(runId ?? "") });
        },
    });

    const liveStream = useSseStream<RunEvent & { event_type?: string }>(
        runId && run && !TERMINAL.has(run.status) ? `/orchestration/runs/${runId}/stream` : null,
        {
            enabled: Boolean(runId && run && !TERMINAL.has(run.status)),
            onEvent: (event) => {
                if (!event.id) return;
                setEvents((previous) => {
                    if (previous.some((item) => item.id === event.id)) return previous;
                    const next = [...previous, event];
                    return next.length > MAX_RENDERED_EVENTS ? next.slice(-MAX_RENDERED_EVENTS) : next;
                });
            },
            onStreamEnd: () => {
                void queryClient.invalidateQueries({ queryKey: queryKeys.runs.detail(runId ?? "") });
            },
            onError: () => {
                setStreamError("Live stream unavailable — showing the latest saved events.");
                if (runId) void listRunEvents(runId).then((items) => setEvents(items.slice(-MAX_RENDERED_EVENTS))).catch(() => undefined);
            },
        },
    );
    const streaming = liveStream.status === "connecting" || liveStream.status === "open" || liveStream.status === "reconnecting";
    const runStatus = run?.status;

    useEffect(() => {
        if (!runId || !runStatus || !TERMINAL.has(runStatus)) return;
        void listRunEvents(runId).then((items) => setEvents(items.slice(-MAX_RENDERED_EVENTS))).catch(() => undefined);
    }, [runId, runStatus]);

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
    const wmEditable = ["queued", "in_progress", "blocked"].includes(run.status);
    const selectionMeta = readOrchestrationSelectionMeta(run);
    const modelRationale = selectionMeta.model_rationale;
    const traceSteps = readTraceSteps(execSnapshot, events);
    // Build per-event timestamps for delta display
    const eventTimes = events.map((e) => new Date(e.created_at).getTime());

    return (
        <PageShell maxWidth="xl">

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
                    <Skeleton variant="rounded" height={120} sx={{ borderRadius: 1 }} />
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
                            <Box sx={{ mt: 1 }}>
                                <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                                    Checkpoint excerpt
                                </Typography>
                                <ShallowKeyValueList
                                    data={execSnapshot.checkpoint_excerpt as Record<string, unknown>}
                                />
                                <CollapsibleRawJson
                                    value={execSnapshot.checkpoint_excerpt}
                                    summary="Raw checkpoint excerpt"
                                    maxHeight={240}
                                />
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

            {execSnapshot && (
                <SectionCard
                    title="Durable workflow"
                    description="Checkpoint-first durable state: workflow id, resume handle, queued signals, query snapshot, and migration posture."
                    sx={{ mt: 2 }}
                >
                    <Stack spacing={1.5}>
                        <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 1 }}>
                            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                                <Chip size="small" variant="outlined" label={String(execSnapshot.durable_workflow?.workflow_id || "no workflow id")} />
                                <Chip size="small" variant="outlined" label={String(execSnapshot.durable_workflow?.backend || "unknown backend")} />
                                <Chip size="small" variant="outlined" label={`resume ${Number(execSnapshot.durable_workflow?.resume_count || 0)}`} />
                                <Chip size="small" variant="outlined" label={`recovery ${Number(execSnapshot.durable_workflow?.recovery_count || 0)}`} />
                            </Stack>
                            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
                                Current step: {String(execSnapshot.durable_workflow?.current_step_id || "n/a")} • Last completed: {String(execSnapshot.durable_workflow?.last_completed_step_id || "n/a")}
                            </Typography>
                            <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
                                Handle: {String((execSnapshot.durable_workflow?.execution_handle as Record<string, unknown> | undefined)?.resume_token || "n/a")}
                            </Typography>
                        </Paper>
                        <Stack direction={{ xs: "column", lg: "row" }} spacing={2}>
                            <Box sx={{ flex: 1 }}>
                                <Typography variant="caption" color="text.secondary">Queued signals</Typography>
                                {Array.isArray(execSnapshot.durable_workflow?.signal_queue) && execSnapshot.durable_workflow.signal_queue.length > 0 ? (
                                    <Stack spacing={0.75} sx={{ mt: 0.75 }}>
                                        {execSnapshot.durable_workflow.signal_queue.map((signal) => (
                                            <Paper key={String(signal.id)} variant="outlined" sx={{ p: 1, borderRadius: 1 }}>
                                                <Typography variant="body2">{String(signal.name || signal.id)}</Typography>
                                                <Typography variant="caption" color="text.secondary">
                                                    {String(signal.created_at || "")}
                                                </Typography>
                                            </Paper>
                                        ))}
                                    </Stack>
                                ) : (
                                    <Typography variant="body2" color="text.secondary" sx={{ mt: 0.75 }}>No queued signals.</Typography>
                                )}
                            </Box>
                            <Box sx={{ flex: 1 }}>
                                <Typography variant="caption" color="text.secondary">Migration posture</Typography>
                                <Paper variant="outlined" sx={{ p: 1, borderRadius: 1, mt: 0.75 }}>
                                    <Typography variant="body2">
                                        {String((execSnapshot.durable_workflow?.migration as Record<string, unknown> | undefined)?.strategy || "checkpoint-first coexistence")}
                                    </Typography>
                                    <Typography variant="caption" color="text.secondary">
                                        schema {String((execSnapshot.durable_workflow?.migration as Record<string, unknown> | undefined)?.current_schema_version || "n/a")}
                                    </Typography>
                                </Paper>
                                <Typography variant="subtitle2" color="text.secondary" sx={{ display: "block", mt: 1 }}>
                                    Query snapshot
                                </Typography>
                                <Box sx={{ mt: 0.75 }}>
                                    <ShallowKeyValueList
                                        data={(execSnapshot.durable_workflow?.query_snapshot || {}) as Record<string, unknown>}
                                    />
                                    <CollapsibleRawJson
                                        value={execSnapshot.durable_workflow?.query_snapshot || {}}
                                        summary="Raw query snapshot"
                                        maxHeight={200}
                                    />
                                </Box>
                            </Box>
                        </Stack>
                        <Stack direction={{ xs: "column", md: "row" }} spacing={1.5}>
                            <TextField
                                select
                                size="small"
                                label="Signal"
                                value={signalName}
                                onChange={(event) => setSignalName(event.target.value)}
                                sx={{ minWidth: 180 }}
                            >
                                <MenuItem value="add_note">add_note</MenuItem>
                                <MenuItem value="update_objective">update_objective</MenuItem>
                                <MenuItem value="retry_step">retry_step</MenuItem>
                                <MenuItem value="pause">pause</MenuItem>
                                <MenuItem value="resume">resume</MenuItem>
                            </TextField>
                            <TextField
                                size="small"
                                label="Signal payload JSON"
                                value={signalPayload}
                                onChange={(event) => setSignalPayload(event.target.value)}
                                multiline
                                minRows={4}
                                fullWidth
                            />
                        </Stack>
                        <Button variant="outlined" disabled={signalMutation.isPending} onClick={() => signalMutation.mutate()}>
                            Queue workflow signal
                        </Button>
                        {signalMutation.isError ? (
                            <Alert severity="error">{signalMutation.error instanceof Error ? signalMutation.error.message : "Signal failed."}</Alert>
                        ) : null}
                    </Stack>
                </SectionCard>
            )}

            {execSnapshot && (
                <SectionCard
                    title="Delegation Flow"
                    description="Child runs, blocker queue, reviewer verdict, and GitHub action state for manager-worker execution."
                    sx={{ mt: 2 }}
                >
                    <Stack spacing={1.5}>
                        <Stack spacing={0.75}>
                            <Typography variant="caption" color="text.secondary">Child runs</Typography>
                            {execSnapshot.child_runs.length > 0 ? (
                                execSnapshot.child_runs.map((child) => (
                                    <Paper key={child.id} variant="outlined" sx={{ p: 1.25, borderRadius: 1 }}>
                                        <Stack direction={{ xs: "column", md: "row" }} spacing={1} justifyContent="space-between">
                                            <Box>
                                                <Typography variant="body2">
                                                    {String((child.input_payload?.subtask as Record<string, unknown> | undefined)?.title || child.id)}
                                                </Typography>
                                                <Typography variant="caption" color="text.secondary">
                                                    {child.status} • {child.worker_agent_id ?? "unassigned"}
                                                </Typography>
                                                <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
                                                    {String(((child.input_payload?.subtask as Record<string, unknown> | undefined)?.routing_reason) || "No routing reason captured.")}
                                                </Typography>
                                            </Box>
                                            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                                                <Chip size="small" variant="outlined" label={child.run_mode} />
                                                <Chip size="small" label={child.status} color={child.status === "completed" ? "success" : child.status === "blocked" ? "warning" : child.status === "failed" ? "error" : "default"} />
                                                <Chip size="small" variant="outlined" label={`${child.token_total} tokens`} />
                                                {Array.isArray((child.input_payload?.subtask as Record<string, unknown> | undefined)?.dependency_ids) && ((child.input_payload?.subtask as Record<string, unknown> | undefined)?.dependency_ids as unknown[]).length > 0 ? (
                                                    <Chip
                                                        size="small"
                                                        variant="outlined"
                                                        label={`deps ${(((child.input_payload?.subtask as Record<string, unknown> | undefined)?.dependency_ids) as unknown[]).length}`}
                                                    />
                                                ) : null}
                                            </Stack>
                                        </Stack>
                                    </Paper>
                                ))
                            ) : (
                                <Typography variant="body2" color="text.secondary">No child runs recorded.</Typography>
                            )}
                        </Stack>
                        <Stack direction={{ xs: "column", lg: "row" }} spacing={2}>
                            <Box sx={{ flex: 1 }}>
                                <Typography variant="caption" color="text.secondary">Blocker queue</Typography>
                                {execSnapshot.blocker_queue.length > 0 ? (
                                    <Stack spacing={0.75} sx={{ mt: 0.75 }}>
                                        {execSnapshot.blocker_queue.map((item, index) => (
                                            <Paper key={`${String(item.branch_id || index)}`} variant="outlined" sx={{ p: 1, borderRadius: 1 }}>
                                                <Typography variant="body2">{String(item.title || item.branch_id || `Blocker ${index + 1}`)}</Typography>
                                                <Typography variant="caption" color="text.secondary">
                                                    {String(item.blocker_reason || item.reason || "blocked")}
                                                </Typography>
                                            </Paper>
                                        ))}
                                    </Stack>
                                ) : (
                                    <Typography variant="body2" color="text.secondary" sx={{ mt: 0.75 }}>No active blockers.</Typography>
                                )}
                            </Box>
                            <Box sx={{ flex: 1 }}>
                                <Typography variant="caption" color="text.secondary">Review state</Typography>
                                <Paper variant="outlined" sx={{ p: 1.25, borderRadius: 1, mt: 0.75 }}>
                                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mb: 0.75 }}>
                                        <Chip size="small" label={String(execSnapshot.review_state?.decision || "pending")} color={execSnapshot.review_state?.decision === "approved" ? "success" : execSnapshot.review_state?.decision ? "warning" : "default"} />
                                        <Chip size="small" variant="outlined" label={`round ${String(execSnapshot.review_state?.round || 0)}`} />
                                    </Stack>
                                    <Typography variant="body2">{String(execSnapshot.review_state?.summary || "No review summary yet.")}</Typography>
                                </Paper>
                                <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>GitHub action state</Typography>
                                <Paper variant="outlined" sx={{ p: 1.25, borderRadius: 1, mt: 0.75 }}>
                                    <Typography variant="body2">
                                        {execSnapshot.github_action_state?.completed ? "completed" : "pending"}
                                    </Typography>
                                    <Typography variant="caption" color="text.secondary">
                                        {String(execSnapshot.github_action_state?.policy || execSnapshot.github_action_state?.mode || "No GitHub action policy captured.")}
                                    </Typography>
                                </Paper>
                            </Box>
                        </Stack>
                    </Stack>
                </SectionCard>
            )}

            {execSnapshot && (
                <SectionCard
                    title="Routing & Diff"
                    description="Selection explainability, previous-run diff, and artifacts produced by this run."
                    sx={{ mt: 2 }}
                >
                    <Stack spacing={1.5}>
                        <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 1 }}>
                            <Typography variant="caption" color="text.secondary">Agent selection</Typography>
                            <Typography variant="body2" sx={{ mb: 1 }}>
                                {String(execSnapshot.routing_explainability?.agent_selection_reason || selectionMeta.worker_agent_rationale || "No agent selection explanation stored.")}
                            </Typography>
                            <Typography variant="caption" color="text.secondary">Model selection</Typography>
                            <Typography variant="body2">
                                {String(execSnapshot.routing_explainability?.model_selection_reason || selectionMeta.model_rationale || "No model selection explanation stored.")}
                            </Typography>
                        </Paper>
                        <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 1 }}>
                            <Typography variant="caption" color="text.secondary">What changed since last run</Typography>
                            {String(execSnapshot.execution_memory?.since_last_run_unified_diff || "").trim() ? (
                                <Box component="pre" sx={{ m: 0, mt: 1, whiteSpace: "pre-wrap", typography: "caption" }}>
                                    {String(execSnapshot.execution_memory?.since_last_run_unified_diff || "")}
                                </Box>
                            ) : (
                                <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                                    No previous-run diff captured.
                                </Typography>
                            )}
                        </Paper>
                        <Stack spacing={0.75}>
                            <Typography variant="caption" color="text.secondary">Changed artifacts</Typography>
                            {execSnapshot.changed_artifacts.length > 0 ? (
                                execSnapshot.changed_artifacts.map((artifact) => (
                                    <Paper key={String(artifact.id)} variant="outlined" sx={{ p: 1, borderRadius: 1 }}>
                                        <Typography variant="body2">{String(artifact.title || artifact.id)}</Typography>
                                        <Typography variant="caption" color="text.secondary">
                                            {String(artifact.kind || "artifact")} {artifact.created_at ? `• ${formatDateTime(String(artifact.created_at))}` : ""}
                                        </Typography>
                                    </Paper>
                                ))
                            ) : (
                                <Typography variant="body2" color="text.secondary">No run artifacts recorded.</Typography>
                            )}
                        </Stack>
                    </Stack>
                </SectionCard>
            )}

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
                        value={wmDraft.objective ?? workingMemory?.objective ?? ""}
                        onChange={(e) => setWmDraft((prev) => ({ ...prev, objective: e.target.value }))}
                        multiline
                        minRows={2}
                        fullWidth
                        disabled={!wmEditable}
                        size="small"
                    />
                    <TextField
                        label="Latest findings"
                        value={wmDraft.latest_findings ?? workingMemory?.latest_findings ?? ""}
                        onChange={(e) => setWmDraft((prev) => ({ ...prev, latest_findings: e.target.value }))}
                        multiline
                        minRows={3}
                        fullWidth
                        disabled={!wmEditable}
                        size="small"
                    />
                    <TextField
                        label="Open questions"
                        value={wmDraft.open_questions ?? workingMemory?.open_questions ?? ""}
                        onChange={(e) => setWmDraft((prev) => ({ ...prev, open_questions: e.target.value }))}
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
                                objective: wmDraft.objective ?? workingMemory?.objective ?? "",
                                latest_findings: wmDraft.latest_findings ?? workingMemory?.latest_findings ?? "",
                                open_questions: wmDraft.open_questions ?? workingMemory?.open_questions ?? "",
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
                <SectionCard
                    title="Output"
                    description="Plan, tool results, structured JSON, and final text. Raw JSON stays behind “View raw JSON” for debugging."
                >
                    <Paper
                        sx={(theme) => ({
                            p: 2,
                            borderRadius: 1,
                            backgroundColor: alpha(theme.palette.background.default, 0.45),
                            border: `1px solid ${theme.palette.divider}`,
                        })}
                    >
                        <RunOutputFriendly output={run.output_payload as Record<string, unknown>} />
                    </Paper>
                </SectionCard>
            )}
        </PageShell>
    );
}
