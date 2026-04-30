import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
    Alert,
    Avatar,
    Box,
    Button,
    Chip,
    CircularProgress,
    Dialog,
    DialogActions,
    DialogContent,
    DialogTitle,
    Divider,
    Drawer,
    FormControlLabel,
    IconButton,
    Link,
    MenuItem,
    Paper,
    Stack,
    Switch,
    Tab,
    Tabs,
    TextField,
    Tooltip,
    Typography,
} from "@mui/material";
import { alpha, useTheme } from "@mui/material/styles";
import {
    Check as CheckSimpleIcon,
    CheckCircle as PassIcon,
    Cancel as FailIcon,
    CallSplit as DecomposeIcon,
    Close as CloseIcon,
    MoreVert as MoreIcon,
    PlayArrow as RunIcon,
    Upload as UploadIcon,
} from "@mui/icons-material";
import { Link as RouterLink, useNavigate } from "react-router-dom";
import {
    checkTaskAcceptance,
    createTaskArtifact,
    decomposeTask,
    deleteOrchestrationTask,
    getRunWorkingMemory,
    getTaskExecutionState,
    getTaskMemoryCoordination,
    getTaskTimeline,
    listSemanticMemory,
    listSubtasks,
    listTaskArtifacts,
    patchTaskMemoryCoordination,
    searchEpisodicMemory,
    updateOrchestrationTask,
} from "../api/orchestration";
import type { OrchestrationTask, TaskRun } from "../api/orchestration";
import { useSnackbar } from "../app/snackbarContext";
import { formatDateTime, humanizeKey } from "../utils/formatters";
import {
    EXCEPTION_TASK_COLUMNS,
    MAIN_KANBAN_COLUMNS,
    TASK_TRANSITION_MAP,
    type EvidenceBundleDraft,
    type ExecutionMode,
    type ExternalLinkRecord,
    buildEvidenceBundlePayload,
    buildTransitionOptions,
    createClientId,
    dueDateToTime,
    extractApiErrorMessage,
    getAcceptanceItems,
    milestoneStatusColor,
    readAcceptanceCheckerConfig,
    readEvidenceBundle,
    readExternalLinks,
    serializeExternalLinks,
} from "./orchestrationProjectDetail.shared";

export function MilestoneTimeline({ milestones }: { milestones: Array<{ id: string; title: string; due_date: string | null; status: string }> }) {
    const theme = useTheme();
    const sorted = useMemo(
        () =>
            [...milestones].sort(
                (a, b) =>
                    (a.due_date != null ? new Date(a.due_date).getTime() : Number.MAX_SAFE_INTEGER) -
                    (b.due_date != null ? new Date(b.due_date).getTime() : Number.MAX_SAFE_INTEGER),
            ),
        [milestones],
    );

    if (sorted.length === 0) return null;

    const dated = sorted.filter((item) => item.due_date);
    const firstDue = dueDateToTime(dated[0]?.due_date ?? null);
    const lastDue = dueDateToTime(dated[dated.length - 1]?.due_date ?? null);
    const range = firstDue != null && lastDue != null ? Math.max(lastDue - firstDue, 1) : null;

    return (
        <Box sx={{ display: "grid", gap: 1.25 }}>
            <Box sx={{ position: "relative", px: 1, pt: 1.5 }}>
                <Box sx={{ position: "absolute", top: 14, left: 16, right: 16, height: 2, backgroundColor: theme.palette.divider }} />
                <Box sx={{ display: "flex", gap: 1.5, overflowX: "auto", pb: 0.5 }}>
                    {sorted.map((milestone) => {
                        const due = milestone.due_date ? new Date(milestone.due_date) : null;
                        const position = firstDue != null && range != null && due
                            ? `${Math.min(100, Math.max(0, ((due.getTime() - firstDue) / range) * 100))}%`
                            : "50%";
                        return (
                            <Paper
                                key={milestone.id}
                                variant="outlined"
                                sx={{
                                    position: "relative",
                                    minWidth: 180,
                                    p: 1.5,
                                    borderRadius: 3,
                                    borderColor: milestone.status === "completed" ? theme.palette.success.main : theme.palette.divider,
                                    backgroundColor: alpha(
                                        milestone.status === "completed" ? theme.palette.success.main : theme.palette.primary.main,
                                        0.06,
                                    ),
                                }}
                            >
                                <Box
                                    sx={{
                                        position: "absolute",
                                        top: -10,
                                        left: `clamp(14px, ${position}, calc(100% - 14px))`,
                                        width: 12,
                                        height: 12,
                                        borderRadius: "50%",
                                        backgroundColor: milestone.status === "completed" ? theme.palette.success.main : theme.palette.primary.main,
                                        border: `2px solid ${theme.palette.background.paper}`,
                                        transform: "translateX(-50%)",
                                    }}
                                />
                                <Chip label={humanizeKey(milestone.status)} size="small" color={milestoneStatusColor(milestone.status)} sx={{ mb: 1 }} />
                                <Typography variant="subtitle2">{milestone.title}</Typography>
                                <Typography variant="caption" color="text.secondary">
                                    {due ? `Due ${due.toLocaleDateString()}` : "No due date"}
                                </Typography>
                            </Paper>
                        );
                    })}
                </Box>
            </Box>
        </Box>
    );
}

export function ExternalLinksEditor({
    links,
    onChange,
    compact = false,
}: {
    links: ExternalLinkRecord[];
    onChange: (links: ExternalLinkRecord[]) => void;
    compact?: boolean;
}) {
    return (
        <Stack spacing={1}>
            {links.length === 0 ? (
                <Typography variant="caption" color="text.secondary">
                    No external links yet.
                </Typography>
            ) : null}
            {links.map((link, index) => (
                <Paper key={link.id} variant="outlined" sx={{ p: compact ? 1 : 1.25, borderRadius: 2 }}>
                    <Stack spacing={1}>
                        <Stack direction={{ xs: "column", md: "row" }} spacing={1}>
                            <TextField
                                select
                                size="small"
                                label="Type"
                                value={link.kind}
                                onChange={(event) => onChange(links.map((item, itemIndex) => itemIndex === index ? { ...item, kind: event.target.value } : item))}
                                sx={{ minWidth: 120 }}
                            >
                                {EXTERNAL_LINK_KIND_OPTIONS.map((option) => (
                                    <MenuItem key={option.value} value={option.value}>{option.label}</MenuItem>
                                ))}
                            </TextField>
                            <TextField
                                size="small"
                                label="Label"
                                value={link.label}
                                onChange={(event) => onChange(links.map((item, itemIndex) => itemIndex === index ? { ...item, label: event.target.value } : item))}
                                fullWidth
                            />
                            <Button
                                size="small"
                                color="error"
                                onClick={() => onChange(links.filter((item) => item.id !== link.id))}
                            >
                                Remove
                            </Button>
                        </Stack>
                        <TextField
                            size="small"
                            label="URL"
                            value={link.url}
                            onChange={(event) => onChange(links.map((item, itemIndex) => itemIndex === index ? { ...item, url: event.target.value } : item))}
                            fullWidth
                        />
                        <TextField
                            size="small"
                            label="Notes"
                            value={link.notes}
                            onChange={(event) => onChange(links.map((item, itemIndex) => itemIndex === index ? { ...item, notes: event.target.value } : item))}
                            multiline
                            minRows={compact ? 2 : 1}
                            fullWidth
                        />
                    </Stack>
                </Paper>
            ))}
            <Button
                size="small"
                variant="outlined"
                onClick={() => onChange([...links, { id: createClientId("link"), kind: "doc", label: "", url: "", notes: "" }])}
            >
                Add link
            </Button>
        </Stack>
    );
}

// ── Acceptance Check Dialog ──────────────────────────────────

export function AcceptanceDialog({
    projectId,
    taskId,
    taskTitle,
    onClose,
}: {
    projectId: string;
    taskId: string;
    taskTitle: string;
    onClose: () => void;
}) {
    const { data, isLoading, error } = useQuery({
        queryKey: ["orchestration", "acceptance", taskId],
        queryFn: () => checkTaskAcceptance(projectId, taskId),
    });

    return (
        <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
            <DialogTitle>Acceptance check — {taskTitle}</DialogTitle>
            <DialogContent>
                {isLoading && <CircularProgress size={24} />}
                {error && <Alert severity="error">Check failed.</Alert>}
                {data && (
                    <Stack spacing={1.5} sx={{ mt: 1 }}>
                        <Chip
                            label={data.passed ? "All checks passed" : "Some checks failed"}
                            color={data.passed ? "success" : "error"}
                        />
                        <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                            {Array.isArray(data.config.required_artifact_kinds) && data.config.required_artifact_kinds.length > 0 ? (
                                <Chip size="small" variant="outlined" label={`Artifacts: ${data.config.required_artifact_kinds.join(", ")}`} />
                            ) : null}
                            {data.config.require_github_comment ? <Chip size="small" variant="outlined" label="Needs GitHub comment" /> : null}
                            {data.config.require_github_pr ? <Chip size="small" variant="outlined" label="Needs GitHub PR" /> : null}
                            {data.config.require_reviewer_approval ? <Chip size="small" variant="outlined" label="Needs reviewer approval" /> : null}
                        </Stack>
                        {data.checks.map((check) => {
                            const acceptanceItems = getAcceptanceItems(check as { name: string } & Record<string, unknown>);
                            return (
                            <Stack key={check.name} spacing={0.75}>
                                <Stack direction="row" spacing={1} alignItems="flex-start">
                                    {check.passed ? <PassIcon color="success" fontSize="small" /> : <FailIcon color="error" fontSize="small" />}
                                    <Box>
                                        <Typography variant="body2">{check.name}</Typography>
                                        <Typography variant="caption" color="text.secondary">{check.detail}</Typography>
                                    </Box>
                                </Stack>
                                {acceptanceItems.length > 0 ? (
                                    <Stack spacing={0.75} sx={{ ml: 3 }}>
                                        {acceptanceItems.map((item) => (
                                            <Paper key={item.item} variant="outlined" sx={{ p: 1, borderRadius: 2 }}>
                                                <Stack direction="row" spacing={1} alignItems="flex-start">
                                                    {item.passed ? <PassIcon color="success" fontSize="small" /> : <FailIcon color="error" fontSize="small" />}
                                                    <Box>
                                                        <Typography variant="body2">{item.item}</Typography>
                                                        {item.evidence_excerpt ? (
                                                            <Typography variant="caption" color="text.secondary">
                                                                Evidence: {item.evidence_excerpt}
                                                            </Typography>
                                                        ) : null}
                                                    </Box>
                                                </Stack>
                                            </Paper>
                                        ))}
                                    </Stack>
                                ) : null}
                            </Stack>
                        );})}
                    </Stack>
                )}
            </DialogContent>
            <DialogActions><Button onClick={onClose}>Close</Button></DialogActions>
        </Dialog>
    );
}

// ── Subtask Panel ────────────────────────────────────────────

export function SubtaskPanel({ projectId, taskId, taskTitle }: { projectId: string; taskId: string; taskTitle: string }) {
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();
    const [maxSubtasks, setMaxSubtasks] = useState("4");
    const [context, setContext] = useState("");

    const { data: subtasks = [], isLoading } = useQuery({
        queryKey: ["orchestration", "subtasks", taskId],
        queryFn: () => listSubtasks(projectId, taskId),
    });

    const decomposeMutation = useMutation({
        mutationFn: () => {
            const parsed = Number(maxSubtasks);
            return decomposeTask(projectId, taskId, {
                max_subtasks: Number.isFinite(parsed) && parsed > 0 ? Math.min(10, Math.max(1, parsed)) : 4,
                context: context.trim() || undefined,
            });
        },
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "subtasks", taskId] });
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "tasks"] });
            showToast({ message: "Task decomposed into subtasks.", severity: "success" });
        },
        onError: (error) => {
            showToast({ message: extractApiErrorMessage(error, "Couldn't break task into subtasks. Try again."), severity: "error" });
        },
    });

    return (
        <Box>
            <Stack spacing={1} sx={{ mb: 1.5 }}>
                <Typography variant="caption" color="text.secondary">Subtasks of: {taskTitle}</Typography>
                <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
                    <TextField
                        size="small"
                        label="Context"
                        value={context}
                        onChange={(e) => setContext(e.target.value)}
                        placeholder="payments, onboarding, migration..."
                        fullWidth
                    />
                    <TextField
                        size="small"
                        label="Max"
                        type="number"
                        value={maxSubtasks}
                        onChange={(e) => setMaxSubtasks(e.target.value)}
                        sx={{ width: { xs: "100%", sm: 96 } }}
                    />
                    <Button
                        size="small"
                        startIcon={decomposeMutation.isPending ? <CircularProgress size={12} /> : <DecomposeIcon />}
                        disabled={decomposeMutation.isPending}
                        onClick={() => decomposeMutation.mutate()}
                    >
                        Decompose
                    </Button>
                </Stack>
            </Stack>
            {isLoading ? (
                <CircularProgress size={16} />
            ) : subtasks.length === 0 ? (
                <Typography variant="caption" color="text.secondary">No subtasks yet.</Typography>
            ) : (
                <Stack spacing={0.5}>
                    {subtasks.map((sub) => (
                        <Stack key={sub.id} direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                            <Chip label={sub.status} size="small" variant="outlined" />
                            {sub.metadata.parallelizable ? <Chip label="parallel" size="small" color="info" variant="outlined" /> : null}
                            {typeof sub.metadata.blueprint_kind === "string" ? <Chip label={String(sub.metadata.blueprint_kind)} size="small" variant="outlined" /> : null}
                            <Typography variant="body2">{sub.title}</Typography>
                        </Stack>
                    ))}
                </Stack>
            )}
        </Box>
    );
}

// ── Artifact Panel ───────────────────────────────────────────

export function ArtifactPanel({ taskId }: { taskId: string }) {
    const queryClient = useQueryClient();
    const [title, setTitle] = useState("");
    const [content, setContent] = useState("");
    const fileRef = useRef<HTMLInputElement>(null);

    const { data: artifacts = [] } = useQuery({
        queryKey: ["orchestration", "artifacts", taskId],
        queryFn: () => listTaskArtifacts(taskId),
    });

    const createMutation = useMutation({
        mutationFn: () => createTaskArtifact(taskId, { title, content, kind: "summary" }),
        onSuccess: async () => {
            setTitle(""); setContent("");
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "artifacts", taskId] });
        },
    });

    async function handleFileUpload(file: File) {
        const text = await file.text();
        await createTaskArtifact(taskId, { title: file.name, content: text, kind: "file" });
        await queryClient.invalidateQueries({ queryKey: ["orchestration", "artifacts", taskId] });
    }

    return (
        <Stack spacing={1.5}>
            {artifacts.map((artifact) => (
                <Paper key={artifact.id} sx={{ p: 1.5, borderRadius: 2 }}>
                    <Stack direction="row" spacing={1} alignItems="center">
                        <Chip label={artifact.kind} size="small" variant="outlined" />
                        <Typography variant="subtitle2">{artifact.title}</Typography>
                        <Typography variant="caption" color="text.secondary">{formatDateTime(artifact.created_at)}</Typography>
                    </Stack>
                    {artifact.content && (
                        <Typography variant="caption" component="pre" sx={{ mt: 0.5, whiteSpace: "pre-wrap", wordBreak: "break-all", maxHeight: 120, overflow: "auto" }}>
                            {artifact.content.slice(0, 500)}
                        </Typography>
                    )}
                </Paper>
            ))}
            <Stack spacing={1}>
                <TextField size="small" label="Title" value={title} onChange={(e) => setTitle(e.target.value)} />
                <TextField size="small" label="Content" multiline minRows={2} value={content} onChange={(e) => setContent(e.target.value)} />
                <Stack direction="row" spacing={1}>
                    <Button size="small" variant="outlined" disabled={!title.trim()} onClick={() => createMutation.mutate()}>
                        Add artifact
                    </Button>
                    <Button size="small" variant="outlined" startIcon={<UploadIcon />} component="label">
                        Upload file
                        <input hidden type="file" ref={fileRef} onChange={(e) => {
                            const file = e.target.files?.[0];
                            if (file) void handleFileUpload(file);
                        }} />
                    </Button>
                </Stack>
            </Stack>
        </Stack>
    );
}

export function TaskMemoryInspector({
    projectId,
    taskId,
    lastRunId,
}: {
    projectId: string;
    taskId: string;
    lastRunId?: string;
}) {
    const navigate = useNavigate();
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();
    const [sharedDraft, setSharedDraft] = useState("");
    const [privateJsonDraft, setPrivateJsonDraft] = useState("{}");

    const { data: episodic } = useQuery({
        queryKey: ["orchestration", "task-episodic", projectId, taskId],
        queryFn: () => searchEpisodicMemory(projectId, { task_id: taskId, limit: 40 }),
        enabled: Boolean(projectId && taskId),
    });
    const { data: semanticRows = [] } = useQuery({
        queryKey: ["orchestration", "task-semantic", projectId, taskId],
        queryFn: () => listSemanticMemory(projectId, { source_task_id: taskId, limit: 50 }),
        enabled: Boolean(projectId && taskId),
    });
    const { data: coord } = useQuery({
        queryKey: ["orchestration", "task-coord", projectId, taskId],
        queryFn: () => getTaskMemoryCoordination(projectId, taskId),
        enabled: Boolean(projectId && taskId),
    });
    const { data: wm } = useQuery({
        queryKey: ["orchestration", "run-wm", lastRunId],
        queryFn: () => getRunWorkingMemory(lastRunId!),
        enabled: Boolean(lastRunId),
    });

    useEffect(() => {
        if (!coord) return;
        setSharedDraft(coord.shared ?? "");
        try {
            setPrivateJsonDraft(JSON.stringify(coord.private ?? {}, null, 2));
        } catch {
            setPrivateJsonDraft("{}");
        }
    }, [coord]);

    const patchCoordMut = useMutation({
        mutationFn: async () => {
            let priv: Record<string, string> = {};
            try {
                const parsed = JSON.parse(privateJsonDraft) as unknown;
                if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
                    priv = Object.fromEntries(
                        Object.entries(parsed as Record<string, unknown>).map(([k, v]) => [k, String(v)]),
                    );
                }
            } catch {
                throw new Error("INVALID_JSON");
            }
            return patchTaskMemoryCoordination(projectId, taskId, { shared: sharedDraft, private: priv });
        },
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "task-coord", projectId, taskId] });
            showToast({ message: "Task memory coordination saved.", severity: "success" });
        },
        onError: (error: unknown) => {
            const msg =
                error instanceof Error && error.message === "INVALID_JSON"
                    ? "Private scratchpad JSON is invalid."
                    : extractApiErrorMessage(error, "Could not save coordination.");
            showToast({ message: msg, severity: "error" });
        },
    });

    const hits = episodic?.hits ?? [];

    return (
        <Stack spacing={1.25} sx={{ mt: 1 }}>
            <Typography variant="subtitle2">Task memory</Typography>
            <Typography variant="caption" color="text.secondary">
                Working snapshot from the latest run (if any). Blackboard = shared coordination; private JSON = per-agent
                scratchpad keys.
            </Typography>
            {lastRunId ? (
                <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                    <Button size="small" variant="outlined" onClick={() => navigate(`/runs/${lastRunId}`)}>
                        Open run {lastRunId.slice(0, 8)}…
                    </Button>
                    <Typography variant="caption" color="text.secondary">
                        Updated {wm ? formatDateTime(wm.updated_at) : "…"}
                    </Typography>
                </Stack>
            ) : (
                <Typography variant="caption" color="text.secondary">
                    No run yet — start a run to populate working memory.
                </Typography>
            )}
            {wm ? (
                <Paper variant="outlined" sx={{ p: 1, borderRadius: 2, maxHeight: 160, overflow: "auto" }}>
                    <Typography variant="caption" component="pre" sx={{ whiteSpace: "pre-wrap", wordBreak: "break-word", m: 0 }}>
                        {JSON.stringify(
                            {
                                objective: wm.objective,
                                accepted_plan: wm.accepted_plan,
                                latest_findings: wm.latest_findings,
                                temp_notes: wm.temp_notes,
                                open_questions: wm.open_questions,
                            },
                            null,
                            2,
                        )}
                    </Typography>
                </Paper>
            ) : null}
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
                Blackboard (shared)
            </Typography>
            <TextField
                size="small"
                multiline
                minRows={2}
                value={sharedDraft}
                onChange={(e) => setSharedDraft(e.target.value)}
                fullWidth
                placeholder="Visible to all agents on this task…"
            />
            <Typography variant="caption" color="text.secondary">
                Private scratchpad (JSON object: agent_id → text)
            </Typography>
            <TextField
                size="small"
                multiline
                minRows={3}
                value={privateJsonDraft}
                onChange={(e) => setPrivateJsonDraft(e.target.value)}
                fullWidth
            />
            <Button size="small" variant="contained" disabled={patchCoordMut.isPending} onClick={() => patchCoordMut.mutate()}>
                Save blackboard / scratchpad
            </Button>
            <Divider sx={{ my: 0.5 }} />
            <Typography variant="caption" color="text.secondary">
                Episodic timeline (indexed rows for this task)
            </Typography>
            <Stack spacing={0.5} sx={{ maxHeight: 180, overflow: "auto" }}>
                {hits.length === 0 ? (
                    <Typography variant="caption" color="text.secondary">
                        No episodic hits yet.
                    </Typography>
                ) : (
                    hits.slice(0, 20).map((hit, i) => (
                        <Paper key={`${String(hit.kind)}-${String(hit.id)}-${i}`} variant="outlined" sx={{ p: 0.75, borderRadius: 1 }}>
                            <Typography variant="caption" color="text.secondary">
                                {String(hit.kind)} · {formatDateTime(String(hit.created_at))}
                            </Typography>
                            <Typography variant="caption" sx={{ display: "block", whiteSpace: "pre-wrap" }}>
                                {String(hit.snippet ?? "").slice(0, 280)}
                            </Typography>
                        </Paper>
                    ))
                )}
            </Stack>
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
                Promoted semantic entries (source_task_id)
            </Typography>
            <Stack spacing={0.5} sx={{ maxHeight: 140, overflow: "auto" }}>
                {semanticRows.length === 0 ? (
                    <Typography variant="caption" color="text.secondary">
                        None linked to this task.
                    </Typography>
                ) : (
                    semanticRows.map((row) => (
                        <Typography key={row.id} variant="caption" sx={{ display: "block" }}>
                            <Link component={RouterLink} to={`/agent-projects/${projectId}/memory`} underline="hover">
                                [{row.entry_type}]
                            </Link>{" "}
                            {row.title} · {(row.confidence * 100).toFixed(0)}%
                        </Typography>
                    ))
                )}
            </Stack>
        </Stack>
    );
}

// ── Kanban Board ─────────────────────────────────────────────

export function KanbanBoard({
    projectId,
    tasks,
    allAgents,
    lastRunByTaskId,
    onRunTask,
    onAcceptanceCheck,
    isRunPending,
    selectedTaskId,
    taskRunModes,
    taskPrModes,
    onModeChange,
    onPrModeChange,
}: {
    projectId: string;
    tasks: OrchestrationTask[];
    allAgents: Array<{ id: string; name: string }>;
    lastRunByTaskId: Record<string, TaskRun>;
    onRunTask: (taskId: string, mode: ExecutionMode, createPr: boolean) => void;
    onAcceptanceCheck: (taskId: string) => void;
    isRunPending: boolean;
    selectedTaskId: string;
    taskRunModes: Record<string, ExecutionMode>;
    taskPrModes: Record<string, boolean>;
    onModeChange: (taskId: string, mode: ExecutionMode) => void;
    onPrModeChange: (taskId: string, enabled: boolean) => void;
}) {
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();
    const [expandedTask, setExpandedTask] = useState<string | null>(null);
    const [taskLinkDrafts, setTaskLinkDrafts] = useState<Record<string, ExternalLinkRecord[]>>({});
    const [evidenceDrafts, setEvidenceDrafts] = useState<Record<string, EvidenceBundleDraft>>({});
    const [nextStatusByTask, setNextStatusByTask] = useState<Record<string, string>>({});
    const [draggingTaskId, setDraggingTaskId] = useState<string | null>(null);
    const [dropHoverColumn, setDropHoverColumn] = useState<string | null>(null);

    const clearKanbanDragState = useCallback(() => {
        setDraggingTaskId(null);
        setDropHoverColumn(null);
    }, []);

    const handleKanbanColumnDragOverCapture = useCallback(
        (event: DragEvent<HTMLDivElement>, columnStatus: string) => {
            if (!draggingTaskId) return;
            event.preventDefault();
            event.dataTransfer.dropEffect = "move";
            setDropHoverColumn(columnStatus);
        },
        [draggingTaskId],
    );

    const taskUpdateMutation = useMutation({
        mutationFn: ({ taskId, payload }: { taskId: string; payload: Record<string, unknown> }) =>
            updateOrchestrationTask(projectId, taskId, payload),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "tasks"] });
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "task-exec", expandedTask] });
        },
        onError: (error) => {
            showToast({ message: extractApiErrorMessage(error, "Task update failed."), severity: "error" });
        },
    });

    const handleKanbanColumnDrop = useCallback(
        (event: DragEvent<HTMLDivElement>, columnStatus: string) => {
            event.preventDefault();
            const raw = event.dataTransfer.getData("application/json") || "";
            let parsed: { taskId?: string };
            try {
                parsed = JSON.parse(raw || "{}") as { taskId?: string };
            } catch {
                clearKanbanDragState();
                return;
            }
            const taskId = parsed.taskId;
            if (!taskId) {
                clearKanbanDragState();
                return;
            }
            const task = tasks.find((t) => t.id === taskId);
            if (!task) {
                clearKanbanDragState();
                return;
            }
            if (task.status === columnStatus) {
                clearKanbanDragState();
                return;
            }
            if (!TASK_TRANSITION_MAP[task.status]?.includes(columnStatus)) {
                showToast({ message: "That column is not valid for this task.", severity: "warning" });
                clearKanbanDragState();
                return;
            }
            if (columnStatus === "in_progress") {
                const incomplete = tasks.filter(
                    (c) => (task.dependency_ids ?? []).includes(c.id)
                        && !["approved", "completed", "synced_to_github", "archived"].includes(c.status),
                );
                if (incomplete.length) {
                    showToast({ message: "Finish dependency tasks before moving to In Progress.", severity: "warning" });
                    clearKanbanDragState();
                    return;
                }
            }
            if (taskUpdateMutation.isPending && taskUpdateMutation.variables?.taskId === taskId) {
                clearKanbanDragState();
                return;
            }
            taskUpdateMutation.mutate({ taskId, payload: { status: columnStatus } });
            clearKanbanDragState();
        },
        [tasks, taskUpdateMutation, showToast, clearKanbanDragState],
    );

    const acceptanceConfigMutation = useMutation({
        mutationFn: ({ taskId, metadata }: { taskId: string; metadata: Record<string, unknown> }) =>
            updateOrchestrationTask(projectId, taskId, { metadata }),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "tasks"] });
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "task-exec", expandedTask] });
            showToast({ message: "Acceptance checker updated.", severity: "success" });
        },
        onError: (error) => {
            showToast({ message: extractApiErrorMessage(error, "Couldn't save acceptance checker. Try again."), severity: "error" });
        },
    });
    const deleteTaskMutation = useMutation({
        mutationFn: (taskId: string) => deleteOrchestrationTask(projectId, taskId),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "tasks"] });
            showToast({ message: "Task deleted.", severity: "success" });
        },
        onError: (error) => {
            showToast({ message: extractApiErrorMessage(error, "Couldn't delete task. Try again."), severity: "error" });
        },
    });

    function handleDeleteTask(taskId: string, title: string) {
        if (!window.confirm(`Delete task "${title}"? This cannot be undone.`)) return;
        deleteTaskMutation.mutate(taskId);
    }
    const { data: timeline = [] } = useQuery({
        queryKey: ["orchestration", "project", projectId, "tasks", expandedTask, "timeline"],
        queryFn: () => (expandedTask ? getTaskTimeline(projectId, expandedTask) : Promise.resolve([])),
        enabled: Boolean(expandedTask),
    });
    const { data: expandedExecSnapshot } = useQuery({
        queryKey: ["orchestration", "project", projectId, "task-exec", expandedTask],
        queryFn: () => (expandedTask ? getTaskExecutionState(projectId, expandedTask) : Promise.resolve(null)),
        enabled: Boolean(expandedTask),
    });
    const { data: expandedArtifacts = [] } = useQuery({
        queryKey: ["orchestration", "project", projectId, "task-artifacts", expandedTask],
        queryFn: () => (expandedTask ? listTaskArtifacts(expandedTask) : Promise.resolve([])),
        enabled: Boolean(expandedTask),
    });

    function updateAcceptanceConfig(task: OrchestrationTask, patch: Partial<AcceptanceCheckerConfig>) {
        acceptanceConfigMutation.mutate({
            taskId: task.id,
            metadata: {
                ...task.metadata,
                acceptance_checker: {
                    ...readAcceptanceCheckerConfig(task),
                    ...patch,
                },
            },
        });
    }

    const tasksByStatus = useMemo(() => {
        const map: Record<string, OrchestrationTask[]> = {};
        for (const col of MAIN_KANBAN_COLUMNS) map[col.status] = [];
        for (const task of tasks) {
            const col = MAIN_KANBAN_COLUMNS.find((c) => c.status === task.status);
            if (col) map[col.status].push(task);
        }
        return map;
    }, [tasks]);

    const exceptionTasks = useMemo(
        () => EXCEPTION_TASK_COLUMNS.map((column) => ({ ...column, tasks: tasks.filter((task) => task.status === column.status) })),
        [tasks],
    );

    return (
        <Stack spacing={2}>
            {exceptionTasks.some((group) => group.tasks.length > 0) ? (
                <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 3 }}>
                    <Typography variant="subtitle2" sx={{ mb: 1 }}>Off-path tasks</Typography>
                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                        {exceptionTasks.map((group) => group.tasks.length > 0 ? (
                            <Chip key={group.status} label={`${group.label} · ${group.tasks.length}`} color={group.color} variant="outlined" />
                        ) : null)}
                    </Stack>
                </Paper>
            ) : null}
            <Box sx={{ display: "flex", gap: 0.75, overflowX: "auto", pb: 1, minHeight: 400 }}>
            {MAIN_KANBAN_COLUMNS.map((col) => (
                <Box
                    key={col.status}
                    onDragOverCapture={(event) => handleKanbanColumnDragOverCapture(event, col.status)}
                    onDrop={(event) => handleKanbanColumnDrop(event, col.status)}
                    sx={(theme) => ({
                        minWidth: 150,
                        flex: "1 1 0",
                        borderRadius: 2,
                        p: 0.75,
                        backgroundColor: alpha(theme.palette.background.paper, 0.6),
                        border: `1px solid ${
                            dropHoverColumn === col.status && draggingTaskId
                                ? theme.palette.primary.main
                                : theme.palette.divider
                        }`,
                        boxShadow:
                            dropHoverColumn === col.status && draggingTaskId
                                ? `0 0 0 2px ${alpha(theme.palette.primary.main, 0.28)}`
                                : "none",
                        transition: theme.transitions.create(["border-color", "box-shadow"], { duration: 120 }),
                    })}
                >
                    <Stack direction="row" spacing={0.5} alignItems="center" sx={{ mb: 0.75 }}>
                        <Chip label={col.label} color={col.color} size="small" sx={{ height: 20, fontSize: "0.7rem", "& .MuiChip-label": { px: 0.75 } }} />
                        <Typography variant="caption" color="text.secondary" sx={{ fontSize: "0.7rem" }}>{tasksByStatus[col.status]?.length ?? 0}</Typography>
                    </Stack>
                    <Stack spacing={0.75}>
                        {(tasksByStatus[col.status] ?? []).map((task) => {
                            const agent = allAgents.find((a) => a.id === task.assigned_agent_id);
                            const isExpanded = expandedTask === task.id;
                            const lastRun = lastRunByTaskId[task.id];
                            const runMeta = readOrchestrationSelectionMeta(lastRun);
                            const acceptanceConfig = readAcceptanceCheckerConfig(task);
                            const taskLinks = taskLinkDrafts[task.id] ?? readExternalLinks(task.metadata?.external_links);
                            const evidenceDraft = evidenceDrafts[task.id] ?? readEvidenceBundle(task);
                            const dependencyTasks = tasks.filter((candidate) => (task.dependency_ids ?? []).includes(candidate.id));
                            const incompleteDependencies = dependencyTasks.filter((candidate) => !["approved", "completed", "synced_to_github", "archived"].includes(candidate.status));
                            const acceptancePassed = Boolean(expandedExecSnapshot?.acceptance_summary?.passed);
                            const acceptedArtifactsCount = evidenceDraft.accepted_artifact_ids.filter((artifactId) => expandedArtifacts.some((artifact) => artifact.id === artifactId)).length;
                            const acceptedLinksCount = evidenceDraft.accepted_external_link_ids.filter((linkId) => taskLinks.some((link) => link.id === linkId)).length;
                            const evidenceReadyForSync =
                                acceptedArtifactsCount > 0 &&
                                acceptedLinksCount > 0 &&
                                Boolean(evidenceDraft.reviewer_decision_status) &&
                                Boolean(evidenceDraft.sync_summary.trim());
                            const evidenceReadyForArchive =
                                (acceptedArtifactsCount > 0 &&
                                    acceptedLinksCount > 0 &&
                                    Boolean(evidenceDraft.reviewer_decision_status) &&
                                    (Boolean(evidenceDraft.sync_summary.trim()) || task.status === "synced_to_github"))
                                || task.status === "archived";
                            const transitionOptions = buildTransitionOptions({
                                task,
                                acceptancePassed,
                                evidenceReadyForSync,
                                evidenceReadyForArchive,
                                hasIncompleteDependencies: incompleteDependencies.length > 0,
                            });
                            const selectedNextStatus = nextStatusByTask[task.id] ?? transitionOptions[0]?.status ?? "";
                            const workerTip =
                                runMeta.worker_agent_rationale
                                || "The worker comes from the task assignment, an explicit run payload, or automatic routing. Run again to capture a fresh routing note.";
                            const isDraggingCard = draggingTaskId === task.id;
                            const isStatusUpdatePending = taskUpdateMutation.isPending && taskUpdateMutation.variables?.taskId === task.id;
                            return (
                                <Paper
                                    key={task.id}
                                    draggable={!isStatusUpdatePending}
                                    onDragStart={(event) => {
                                        setDraggingTaskId(task.id);
                                        const payload = JSON.stringify({ taskId: task.id, fromStatus: task.status });
                                        event.dataTransfer.setData("application/json", payload);
                                        event.dataTransfer.setData("text/plain", task.id);
                                        event.dataTransfer.effectAllowed = "move";
                                    }}
                                    onDragEnd={clearKanbanDragState}
                                    sx={(theme) => {
                                        const priorityAccent = task.priority === "urgent"
                                            ? theme.palette.error.main
                                            : task.priority === "high"
                                                ? theme.palette.warning.main
                                                : task.priority === "low"
                                                    ? theme.palette.divider
                                                    : theme.palette.info.main;
                                        return {
                                            position: "relative",
                                            p: 0.75,
                                            pl: 1,
                                            minHeight: 170,
                                            display: "flex",
                                            flexDirection: "column",
                                            borderRadius: 2,
                                            border: `1px solid ${theme.palette.divider}`,
                                            borderLeft: `3px solid ${priorityAccent}`,
                                            "&:hover": { borderColor: theme.palette.primary.main, borderLeftColor: priorityAccent },
                                            cursor: isStatusUpdatePending ? "default" : "grab",
                                            opacity: isDraggingCard ? 0.88 : 1,
                                            ...(isDraggingCard ? { boxShadow: theme.shadows[6] } : {}),
                                        };
                                    }}
                                >
                                    <IconButton
                                        size="small"
                                        aria-label={`Delete ${task.title}`}
                                        onMouseDown={(event) => event.stopPropagation()}
                                        onClick={(event) => {
                                            event.stopPropagation();
                                            handleDeleteTask(task.id, task.title);
                                        }}
                                        disabled={deleteTaskMutation.isPending && deleteTaskMutation.variables === task.id}
                                        sx={{
                                            position: "absolute",
                                            top: 2,
                                            right: 2,
                                            p: 0.25,
                                            color: "text.secondary",
                                            "&:hover": { color: "error.main" },
                                        }}
                                    >
                                        <CloseIcon sx={{ fontSize: 14 }} />
                                    </IconButton>
                                    <Typography
                                        variant="subtitle2"
                                        sx={{
                                            wordBreak: "break-word",
                                            pr: 2.5,
                                            fontSize: "0.78rem",
                                            lineHeight: 1.25,
                                            mb: 0.5,
                                            display: "-webkit-box",
                                            WebkitLineClamp: 3,
                                            WebkitBoxOrient: "vertical",
                                            overflow: "hidden",
                                        }}
                                    >
                                        {task.title}
                                    </Typography>
                                    {(() => {
                                        const priorityLetter = task.priority === "urgent" ? "U" : task.priority === "high" ? "H" : task.priority === "low" ? "L" : "N";
                                        const priorityChipColor: "default" | "error" | "warning" | "info" = task.priority === "urgent" ? "error" : task.priority === "high" ? "warning" : task.priority === "low" ? "default" : "info";
                                        const sourceRaw = (task.source || "manual").toLowerCase();
                                        const sourceKind = sourceRaw === "github" || sourceRaw === "github_issue"
                                            ? "github"
                                            : sourceRaw === "manual"
                                                ? "manual"
                                                : "generated";
                                        const SourceIcon = sourceKind === "github" ? GitHubIcon : sourceKind === "generated" ? GeneratedIcon : ManualIcon;
                                        const runStatusRaw = lastRun?.status ?? "";
                                        let runLabel = "idle";
                                        let runDotColor = "text.disabled";
                                        if (["running", "pending", "queued", "in_progress"].includes(runStatusRaw)) { runLabel = "running"; runDotColor = "info.main"; }
                                        else if (["awaiting_approval", "needs_approval", "waiting_approval"].includes(runStatusRaw)) { runLabel = "waiting approval"; runDotColor = "warning.main"; }
                                        else if (["failed", "error"].includes(runStatusRaw)) { runLabel = "failed"; runDotColor = "error.main"; }
                                        else if (runStatusRaw === "cancelled") { runLabel = "cancelled"; runDotColor = "error.light"; }
                                        else if (["completed", "succeeded", "done"].includes(runStatusRaw)) { runLabel = "idle"; runDotColor = "success.main"; }
                                        const depCount = task.dependency_ids?.length ?? 0;
                                        const prNumber = (task.result_payload.github_pr as Record<string, unknown> | undefined)?.number;
                                        const dueMeta = task.due_date ? (() => {
                                            const diffDays = Math.ceil((new Date(task.due_date as string).getTime() - Date.now()) / 86_400_000);
                                            if (diffDays < 0) return { label: `${Math.abs(diffDays)}d late`, color: "error" as const };
                                            if (diffDays === 0) return { label: "today", color: "warning" as const };
                                            if (diffDays <= 3) return { label: `${diffDays}d`, color: "warning" as const };
                                            return { label: `${diffDays}d`, color: "default" as const };
                                        })() : null;
                                        const chipSx = { height: 18, fontSize: "0.62rem", "& .MuiChip-label": { px: 0.6 } } as const;
                                        const avatarSx = { width: 16, height: 16, fontSize: "0.58rem" } as const;
                                        const ownerInitial = (agent?.name ?? "?").trim().charAt(0).toUpperCase() || "?";
                                        const reviewerName = task.reviewer_agent_id ? getAgentLabel(task.reviewer_agent_id, allAgents) : "";
                                        const reviewerInitial = reviewerName.trim().charAt(0).toUpperCase() || "?";
                                        return (
                                            <Stack spacing={0.5}>
                                                <Stack direction="row" spacing={0.5} alignItems="center" flexWrap="wrap" useFlexGap>
                                                    <Tooltip title={`Priority: ${task.priority}`}>
                                                        <Chip label={priorityLetter} size="small" color={priorityChipColor} sx={{ ...chipSx, width: 22, justifyContent: "center" }} />
                                                    </Tooltip>
                                                    <Tooltip title={`Source: ${sourceKind}`}>
                                                        <Box sx={{ display: "inline-flex", alignItems: "center", color: sourceKind === "github" ? "info.main" : sourceKind === "generated" ? "secondary.main" : "text.secondary" }}>
                                                            <SourceIcon sx={{ fontSize: 14 }} />
                                                        </Box>
                                                    </Tooltip>
                                                    <Tooltip title={`Run: ${runLabel}${lastRun?.completed_at ? ` · ${new Date(lastRun.completed_at).toLocaleString()}` : ""}`}>
                                                        <Stack direction="row" spacing={0.3} alignItems="center">
                                                            <Box sx={{ width: 8, height: 8, borderRadius: "50%", bgcolor: runDotColor, flexShrink: 0 }} />
                                                            <Typography variant="caption" sx={{ fontSize: "0.6rem", lineHeight: 1, color: "text.secondary" }}>
                                                                {runLabel}
                                                            </Typography>
                                                        </Stack>
                                                    </Tooltip>
                                                    {prNumber != null && (
                                                        <Tooltip title={`PR #${String(prNumber)}`}>
                                                            <Chip label={`#${String(prNumber)}`} size="small" color="success" variant="outlined" sx={chipSx} />
                                                        </Tooltip>
                                                    )}
                                                </Stack>
                                                {(agent || task.reviewer_agent_id) && (
                                                    <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap alignItems="center">
                                                        {agent && (
                                                            <Tooltip title={workerTip}>
                                                                <Stack direction="row" spacing={0.4} alignItems="center" sx={{ maxWidth: "100%", minWidth: 0 }}>
                                                                    <Avatar sx={{ ...avatarSx, bgcolor: "secondary.main" }}>{ownerInitial}</Avatar>
                                                                    <Typography variant="caption" noWrap sx={{ fontSize: "0.62rem", lineHeight: 1, color: "text.primary" }}>
                                                                        {agent.name}
                                                                    </Typography>
                                                                </Stack>
                                                            </Tooltip>
                                                        )}
                                                        {task.reviewer_agent_id && (
                                                            <Tooltip title={`Reviewer: ${reviewerName}`}>
                                                                <Stack direction="row" spacing={0.4} alignItems="center" sx={{ maxWidth: "100%", minWidth: 0 }}>
                                                                    <Avatar sx={{ ...avatarSx, bgcolor: "primary.main" }}>{reviewerInitial}</Avatar>
                                                                    <Typography variant="caption" noWrap sx={{ fontSize: "0.62rem", lineHeight: 1, color: "text.secondary" }}>
                                                                        {reviewerName}
                                                                    </Typography>
                                                                </Stack>
                                                            </Tooltip>
                                                        )}
                                                    </Stack>
                                                )}
                                                {(dueMeta || depCount > 0) && (
                                                    <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                                                        {dueMeta && (
                                                            <Tooltip title={`Due ${new Date(task.due_date as string).toLocaleString()}`}>
                                                                <Chip label={dueMeta.label} size="small" color={dueMeta.color} variant={dueMeta.color === "default" ? "outlined" : "filled"} sx={chipSx} />
                                                            </Tooltip>
                                                        )}
                                                        {depCount > 0 && (
                                                            <Tooltip title={`${incompleteDependencies.length} blocking · ${depCount} total`}>
                                                                <Chip
                                                                    label={`⛓ ${incompleteDependencies.length}/${depCount}`}
                                                                    size="small"
                                                                    color={incompleteDependencies.length > 0 ? "warning" : "success"}
                                                                    variant="outlined"
                                                                    sx={chipSx}
                                                                />
                                                            </Tooltip>
                                                        )}
                                                    </Stack>
                                                )}
                                            </Stack>
                                        );
                                    })()}
                                    <Stack
                                        direction="row"
                                        spacing={0.25}
                                        sx={{ mt: "auto", pt: 0.5, borderTop: 1, borderColor: "divider" }}
                                        alignItems="center"
                                    >
                                        <Tooltip title="Run">
                                            <span>
                                                <IconButton
                                                    size="small"
                                                    disabled={isRunPending && selectedTaskId === task.id}
                                                    onMouseDown={(event) => event.stopPropagation()}
                                                    onClick={() => onRunTask(task.id, taskRunModes[task.id] ?? "single_agent", taskPrModes[task.id] ?? false)}
                                                    sx={{ p: 0.25 }}
                                                >
                                                    <RunIcon sx={{ fontSize: 16 }} />
                                                </IconButton>
                                            </span>
                                        </Tooltip>
                                        <Tooltip title="Acceptance check">
                                            <IconButton
                                                size="small"
                                                onMouseDown={(event) => event.stopPropagation()}
                                                onClick={() => onAcceptanceCheck(task.id)}
                                                sx={{ p: 0.25 }}
                                            >
                                                <CheckSimpleIcon sx={{ fontSize: 16 }} />
                                            </IconButton>
                                        </Tooltip>
                                        <Tooltip title={isExpanded ? "Collapse" : "More details"}>
                                            <IconButton
                                                size="small"
                                                onMouseDown={(event) => event.stopPropagation()}
                                                onClick={() => setExpandedTask(isExpanded ? null : task.id)}
                                                sx={{ p: 0.25, ml: "auto" }}
                                            >
                                                <MoreIcon sx={{ fontSize: 16 }} />
                                            </IconButton>
                                        </Tooltip>
                                    </Stack>
                                    {isExpanded && (
                                        <Box sx={{ mt: 1.5 }}>
                                            <Divider sx={{ mb: 1 }} />
                                            <Stack spacing={1.25}>
                                                <TextField
                                                    select
                                                    size="small"
                                                    label="Owner agent"
                                                    value={task.assigned_agent_id ?? ""}
                                                    onChange={(event) => taskUpdateMutation.mutate({
                                                        taskId: task.id,
                                                        payload: { assigned_agent_id: event.target.value || null },
                                                    })}
                                                    fullWidth
                                                >
                                                    <MenuItem value="">Unassigned</MenuItem>
                                                    {allAgents.map((currentAgent) => (
                                                        <MenuItem key={currentAgent.id} value={currentAgent.id}>{currentAgent.name}</MenuItem>
                                                    ))}
                                                </TextField>
                                                <TextField
                                                    select
                                                    size="small"
                                                    label="Reviewer agent"
                                                    value={task.reviewer_agent_id ?? ""}
                                                    onChange={(event) => taskUpdateMutation.mutate({
                                                        taskId: task.id,
                                                        payload: { reviewer_agent_id: event.target.value || null },
                                                    })}
                                                    fullWidth
                                                >
                                                    <MenuItem value="">None</MenuItem>
                                                    {allAgents.map((currentAgent) => (
                                                        <MenuItem key={`review-${currentAgent.id}`} value={currentAgent.id}>{currentAgent.name}</MenuItem>
                                                    ))}
                                                </TextField>
                                                <TextField
                                                    select
                                                    SelectProps={{ multiple: true }}
                                                    size="small"
                                                    label="Blocked by"
                                                    value={task.dependency_ids ?? []}
                                                    onChange={(event) => {
                                                        const nextValue = event.target.value;
                                                        taskUpdateMutation.mutate({
                                                            taskId: task.id,
                                                            payload: {
                                                                dependency_ids: Array.isArray(nextValue) ? nextValue : String(nextValue).split(",").filter(Boolean),
                                                            },
                                                        });
                                                    }}
                                                    helperText="Main task flow dependencies. DAG drawer no longer required for this."
                                                    fullWidth
                                                >
                                                    {tasks.filter((candidate) => candidate.id !== task.id).map((candidate) => (
                                                        <MenuItem key={`dep-${candidate.id}`} value={candidate.id}>
                                                            {candidate.title} · {humanizeKey(candidate.status)}
                                                        </MenuItem>
                                                    ))}
                                                </TextField>
                                                {dependencyTasks.length > 0 ? (
                                                    <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                                                        {dependencyTasks.map((dependencyTask) => (
                                                            <Chip
                                                                key={dependencyTask.id}
                                                                label={`${dependencyTask.title} · ${humanizeKey(dependencyTask.status)}`}
                                                                size="small"
                                                                color={incompleteDependencies.some((item) => item.id === dependencyTask.id) ? "warning" : "success"}
                                                                variant="outlined"
                                                            />
                                                        ))}
                                                    </Stack>
                                                ) : null}
                                                <TextField
                                                    select
                                                    size="small"
                                                    label="Execution mode"
                                                    value={taskRunModes[task.id] ?? "single_agent"}
                                                    onChange={(event) => onModeChange(task.id, event.target.value as ExecutionMode)}
                                                    fullWidth
                                                >
                                                    <MenuItem value="single_agent">Single agent: fast, cheap</MenuItem>
                                                    <MenuItem value="manager_worker">Managed team: manager routes work</MenuItem>
                                                    <MenuItem value="debate">Debate: two agents propose, moderator resolves</MenuItem>
                                                </TextField>
                                                <Button
                                                    size="small"
                                                    variant={taskPrModes[task.id] ? "contained" : "outlined"}
                                                    onClick={() => onPrModeChange(task.id, !(taskPrModes[task.id] ?? false))}
                                                >
                                                    {taskPrModes[task.id] ? "PR generation on" : "Generate PR"}
                                                </Button>
                                            </Stack>
                                            <TextField
                                                size="small"
                                                select
                                                label="Next valid status"
                                                value={selectedNextStatus}
                                                onChange={(event) => setNextStatusByTask((current) => ({ ...current, [task.id]: event.target.value }))}
                                                fullWidth
                                                sx={{ mt: 1.25 }}
                                            >
                                                {transitionOptions.map((option) => (
                                                    <MenuItem key={`${task.id}-${option.status}`} value={option.status} disabled={option.blocked}>
                                                        {humanizeKey(option.status)}{option.reason ? ` — ${option.reason}` : ""}
                                                    </MenuItem>
                                                ))}
                                            </TextField>
                                            {transitionOptions.filter((option) => option.blocked).map((option) => (
                                                <Alert key={`${task.id}-${option.status}-blocked`} severity="warning">
                                                    {humanizeKey(option.status)} blocked: {option.reason}
                                                </Alert>
                                            ))}
                                            <Button
                                                size="small"
                                                variant="contained"
                                                disabled={!selectedNextStatus || transitionOptions.find((option) => option.status === selectedNextStatus)?.blocked}
                                                onClick={() => taskUpdateMutation.mutate({
                                                    taskId: task.id,
                                                    payload: { status: selectedNextStatus },
                                                })}
                                            >
                                                Apply transition
                                            </Button>
                                            <TaskMemoryInspector
                                                projectId={projectId}
                                                taskId={task.id}
                                                lastRunId={lastRun?.id}
                                            />
                                            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                                                Task timeline (comments + approvals + GitHub sync)
                                            </Typography>
                                            <Stack spacing={0.75} sx={{ mb: 1.5, maxHeight: 220, overflow: "auto" }}>
                                                {timeline.length === 0 ? (
                                                    <Typography variant="caption" color="text.secondary">
                                                        No comments or GitHub sync events yet.
                                                    </Typography>
                                                ) : (
                                                    timeline.map((row) => (
                                                        <Paper key={`${row.kind}-${row.id}`} variant="outlined" sx={{ p: 1, borderRadius: 2 }}>
                                                            <Typography variant="caption" color="text.secondary">
                                                                {formatDateTime(row.created_at)} · {row.kind}
                                                            </Typography>
                                                            <Typography variant="body2">{row.title}</Typography>
                                                            {row.body ? (
                                                                <Typography variant="caption" sx={{ display: "block", whiteSpace: "pre-wrap" }}>
                                                                    {row.body}
                                                                </Typography>
                                                            ) : null}
                                                            {row.detail ? (
                                                                <Typography variant="caption" color="text.secondary">{row.detail}</Typography>
                                                            ) : null}
                                                            {typeof row.payload.issue_number === "number" && task.github_repository_full_name && (
                                                                <Link
                                                                    href={`https://github.com/${task.github_repository_full_name}/issues/${String(row.payload.issue_number)}`}
                                                                    target="_blank"
                                                                    rel="noreferrer"
                                                                    underline="hover"
                                                                    sx={{ display: "block", typography: "caption", mt: 0.5 }}
                                                                >
                                                                    GitHub issue #{String(row.payload.issue_number)}
                                                                </Link>
                                                            )}
                                                            {typeof row.payload.pr_number === "number" && task.github_repository_full_name && (
                                                                <Link
                                                                    href={`https://github.com/${task.github_repository_full_name}/pull/${String(row.payload.pr_number)}`}
                                                                    target="_blank"
                                                                    rel="noreferrer"
                                                                    underline="hover"
                                                                    sx={{ display: "block", typography: "caption", mt: 0.5 }}
                                                                >
                                                                    Pull request #{String(row.payload.pr_number)}
                                                                </Link>
                                                            )}
                                                            {typeof row.payload.branch === "string" && task.github_repository_full_name && (
                                                                <Link
                                                                    href={`https://github.com/${task.github_repository_full_name}/tree/${encodeURIComponent(String(row.payload.branch))}`}
                                                                    target="_blank"
                                                                    rel="noreferrer"
                                                                    underline="hover"
                                                                    sx={{ display: "block", typography: "caption", mt: 0.5 }}
                                                                >
                                                                    Branch {String(row.payload.branch)}
                                                                </Link>
                                                            )}
                                                            {(typeof row.payload.head_sha === "string" || typeof row.payload.merge_commit_sha === "string") && task.github_repository_full_name && (
                                                                <Link
                                                                    href={`https://github.com/${task.github_repository_full_name}/commit/${String(row.payload.merge_commit_sha || row.payload.head_sha)}`}
                                                                    target="_blank"
                                                                    rel="noreferrer"
                                                                    underline="hover"
                                                                    sx={{ display: "block", typography: "caption", mt: 0.5 }}
                                                                >
                                                                    Commit {String(row.payload.merge_commit_sha || row.payload.head_sha).slice(0, 12)}
                                                                </Link>
                                                            )}
                                                        </Paper>
                                                    ))
                                                )}
                                            </Stack>
                                            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                                                Routing explainability
                                            </Typography>
                                            <Paper variant="outlined" sx={{ p: 1, borderRadius: 2, mb: 1.5 }}>
                                                <Typography variant="caption" color="text.secondary">Agent selection</Typography>
                                                <Typography variant="body2" sx={{ mb: 1 }}>
                                                    {String(expandedExecSnapshot?.routing_explainability?.agent_selection_reason || workerTip)}
                                                </Typography>
                                                <Typography variant="caption" color="text.secondary">Model selection</Typography>
                                                <Typography variant="body2">
                                                    {String(expandedExecSnapshot?.routing_explainability?.model_selection_reason || runMeta.model_rationale || "No explicit model explanation captured yet.")}
                                                </Typography>
                                                {expandedExecSnapshot?.routing_explainability?.routing_policy_snapshot ? (
                                                    <Box
                                                        component="pre"
                                                        sx={{ m: 0, mt: 1, p: 1, typography: "caption", bgcolor: (theme) => alpha(theme.palette.text.primary, 0.04), whiteSpace: "pre-wrap" }}
                                                    >
                                                        {JSON.stringify(expandedExecSnapshot.routing_explainability.routing_policy_snapshot, null, 2)}
                                                    </Box>
                                                ) : null}
                                            </Paper>
                                            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                                                Acceptance checker
                                            </Typography>
                                            <Stack spacing={1} sx={{ mb: 1.5 }}>
                                                <TextField
                                                    key={`${task.id}-acceptance-artifacts`}
                                                    size="small"
                                                    label="Required artifact kinds"
                                                    defaultValue={acceptanceConfig.required_artifact_kinds.join(", ")}
                                                    helperText="Comma-separated kinds enforced before approve/complete."
                                                    onBlur={(event) => updateAcceptanceConfig(task, {
                                                        required_artifact_kinds: event.target.value.split(",").map((item) => item.trim()).filter(Boolean),
                                                    })}
                                                    fullWidth
                                                />
                                                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                                                    <FormControlLabel
                                                        control={<Switch checked={acceptanceConfig.require_github_comment} onChange={(_, checked) => updateAcceptanceConfig(task, { require_github_comment: checked })} />}
                                                        label="Need GitHub comment"
                                                    />
                                                    <FormControlLabel
                                                        control={<Switch checked={acceptanceConfig.require_github_pr} onChange={(_, checked) => updateAcceptanceConfig(task, { require_github_pr: checked })} />}
                                                        label="Need GitHub PR"
                                                    />
                                                    <FormControlLabel
                                                        control={<Switch checked={acceptanceConfig.require_reviewer_approval} onChange={(_, checked) => updateAcceptanceConfig(task, { require_reviewer_approval: checked })} />}
                                                        label="Need reviewer approval"
                                                    />
                                                </Stack>
                                                {expandedExecSnapshot?.acceptance_summary ? (
                                                    <Alert severity={expandedExecSnapshot.acceptance_summary.passed ? "success" : "warning"}>
                                                        {expandedExecSnapshot.acceptance_summary.passed ? "Acceptance gate currently passes." : "Acceptance gate currently fails."}
                                                    </Alert>
                                                ) : null}
                                                {Array.isArray(expandedExecSnapshot?.acceptance_summary?.checks) ? (
                                                    expandedExecSnapshot.acceptance_summary.checks.map((check) => (
                                                        <Typography key={`${task.id}-${String(check.name)}`} variant="caption" color="text.secondary">
                                                            {String(check.name)}: {String(check.detail ?? check.passed)}
                                                        </Typography>
                                                    ))
                                                ) : null}
                                            </Stack>
                                            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                                                External links
                                            </Typography>
                                            <ExternalLinksEditor
                                                links={taskLinks}
                                                onChange={(links) => setTaskLinkDrafts((current) => ({ ...current, [task.id]: links }))}
                                                compact
                                            />
                                            <Button
                                                size="small"
                                                variant="outlined"
                                                sx={{ mt: 1 }}
                                                onClick={() => taskUpdateMutation.mutate({
                                                    taskId: task.id,
                                                    payload: {
                                                        metadata: {
                                                            ...task.metadata,
                                                            external_links: serializeExternalLinks(taskLinks),
                                                            evidence_bundle: buildEvidenceBundlePayload(evidenceDraft),
                                                        },
                                                    },
                                                })}
                                            >
                                                Save links
                                            </Button>
                                            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5, mt: 1 }}>
                                                Final evidence bundle
                                            </Typography>
                                            <Stack spacing={1} sx={{ mb: 1.5 }}>
                                                <TextField
                                                    select
                                                    SelectProps={{ multiple: true }}
                                                    size="small"
                                                    label="Accepted artifacts"
                                                    value={evidenceDraft.accepted_artifact_ids}
                                                    onChange={(event) => {
                                                        const nextValue = event.target.value;
                                                        setEvidenceDrafts((current) => ({
                                                            ...current,
                                                            [task.id]: {
                                                                ...evidenceDraft,
                                                                accepted_artifact_ids: Array.isArray(nextValue) ? nextValue : String(nextValue).split(",").filter(Boolean),
                                                            },
                                                        }));
                                                    }}
                                                    fullWidth
                                                >
                                                    {expandedArtifacts.map((artifact) => (
                                                        <MenuItem key={artifact.id} value={artifact.id}>{artifact.title} · {artifact.kind}</MenuItem>
                                                    ))}
                                                </TextField>
                                                <TextField
                                                    select
                                                    SelectProps={{ multiple: true }}
                                                    size="small"
                                                    label="Accepted external links"
                                                    value={evidenceDraft.accepted_external_link_ids}
                                                    onChange={(event) => {
                                                        const nextValue = event.target.value;
                                                        setEvidenceDrafts((current) => ({
                                                            ...current,
                                                            [task.id]: {
                                                                ...evidenceDraft,
                                                                accepted_external_link_ids: Array.isArray(nextValue) ? nextValue : String(nextValue).split(",").filter(Boolean),
                                                            },
                                                        }));
                                                    }}
                                                    fullWidth
                                                >
                                                    {taskLinks.map((link) => (
                                                        <MenuItem key={`accepted-link-${link.id}`} value={link.id}>{link.label} · {humanizeKey(link.kind)}</MenuItem>
                                                    ))}
                                                </TextField>
                                                <TextField
                                                    select
                                                    size="small"
                                                    label="Reviewer decision"
                                                    value={evidenceDraft.reviewer_decision_status}
                                                    onChange={(event) => setEvidenceDrafts((current) => ({
                                                        ...current,
                                                        [task.id]: {
                                                            ...evidenceDraft,
                                                            reviewer_decision_status: event.target.value,
                                                        },
                                                    }))}
                                                    fullWidth
                                                >
                                                    <MenuItem value="">Not recorded</MenuItem>
                                                    <MenuItem value="approved">Approved</MenuItem>
                                                    <MenuItem value="changes_requested">Changes requested</MenuItem>
                                                    <MenuItem value="rejected">Rejected</MenuItem>
                                                </TextField>
                                                <TextField
                                                    size="small"
                                                    label="Reviewer notes"
                                                    value={evidenceDraft.reviewer_decision_notes}
                                                    onChange={(event) => setEvidenceDrafts((current) => ({
                                                        ...current,
                                                        [task.id]: {
                                                            ...evidenceDraft,
                                                            reviewer_decision_notes: event.target.value,
                                                        },
                                                    }))}
                                                    multiline
                                                    minRows={2}
                                                    fullWidth
                                                />
                                                <TextField
                                                    size="small"
                                                    label="Sync summary"
                                                    value={evidenceDraft.sync_summary}
                                                    onChange={(event) => setEvidenceDrafts((current) => ({
                                                        ...current,
                                                        [task.id]: {
                                                            ...evidenceDraft,
                                                            sync_summary: event.target.value,
                                                        },
                                                    }))}
                                                    multiline
                                                    minRows={2}
                                                    helperText="Required before `synced_to_github`; reused for archive notes."
                                                    fullWidth
                                                />
                                                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                                                    <Chip label={evidenceReadyForSync ? "Ready for sync" : "Sync evidence incomplete"} size="small" color={evidenceReadyForSync ? "success" : "warning"} />
                                                    <Chip label={evidenceReadyForArchive ? "Ready for archive" : "Archive evidence incomplete"} size="small" color={evidenceReadyForArchive ? "success" : "warning"} />
                                                </Stack>
                                                <Button
                                                    size="small"
                                                    variant="outlined"
                                                    onClick={() => taskUpdateMutation.mutate({
                                                        taskId: task.id,
                                                        payload: {
                                                            metadata: {
                                                                ...task.metadata,
                                                                external_links: serializeExternalLinks(taskLinks),
                                                                evidence_bundle: buildEvidenceBundlePayload(evidenceDraft),
                                                            },
                                                        },
                                                    })}
                                                >
                                                    Save evidence bundle
                                                </Button>
                                            </Stack>
                                            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                                                What changed since last run
                                            </Typography>
                                            <Paper variant="outlined" sx={{ p: 1, borderRadius: 2, mb: 1.5 }}>
                                                {String(expandedExecSnapshot?.execution_memory?.since_last_run_unified_diff || "").trim() ? (
                                                    <Box component="pre" sx={{ m: 0, whiteSpace: "pre-wrap", typography: "caption" }}>
                                                        {String(expandedExecSnapshot?.execution_memory?.since_last_run_unified_diff || "")}
                                                    </Box>
                                                ) : (
                                                    <Typography variant="body2" color="text.secondary">
                                                        No diff captured yet.
                                                    </Typography>
                                                )}
                                                <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
                                                    {expandedExecSnapshot?.last_run_id ? (
                                                        <Link href={`/runs/${expandedExecSnapshot.last_run_id}`} underline="hover">Latest run</Link>
                                                    ) : null}
                                                    {typeof expandedExecSnapshot?.execution_memory?.last_run_id === "string" ? (
                                                        <Link href={`/runs/${String(expandedExecSnapshot.execution_memory.last_run_id)}`} underline="hover">Execution memory source</Link>
                                                    ) : null}
                                                </Stack>
                                            </Paper>
                                            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                                                Changed artifacts
                                            </Typography>
                                            <Stack spacing={0.75} sx={{ mb: 1.5 }}>
                                                {(expandedExecSnapshot?.changed_artifacts as Array<Record<string, unknown>> | undefined)?.length ? (
                                                    (expandedExecSnapshot?.changed_artifacts as Array<Record<string, unknown>>).map((artifact) => (
                                                        <Paper key={String(artifact.id)} variant="outlined" sx={{ p: 1, borderRadius: 2 }}>
                                                            <Typography variant="body2">{String(artifact.title || artifact.id)}</Typography>
                                                            <Typography variant="caption" color="text.secondary">
                                                                {String(artifact.kind || "artifact")} • {artifact.created_at ? formatDateTime(String(artifact.created_at)) : "no timestamp"}
                                                            </Typography>
                                                        </Paper>
                                                    ))
                                                ) : expandedArtifacts.length > 0 ? (
                                                    expandedArtifacts.slice(0, 4).map((artifact) => (
                                                        <Paper key={artifact.id} variant="outlined" sx={{ p: 1, borderRadius: 2 }}>
                                                            <Typography variant="body2">{artifact.title}</Typography>
                                                            <Typography variant="caption" color="text.secondary">
                                                                {artifact.kind} • {formatDateTime(artifact.created_at)}
                                                            </Typography>
                                                        </Paper>
                                                    ))
                                                ) : (
                                                    <Typography variant="caption" color="text.secondary">No artifacts yet.</Typography>
                                                )}
                                            </Stack>
                                            <SubtaskPanel projectId={projectId} taskId={task.id} taskTitle={task.title} />
                                            <Divider sx={{ my: 1 }} />
                                            <ArtifactPanel taskId={task.id} />
                                        </Box>
                                    )}
                                </Paper>
                            );
                        })}
                    </Stack>
                </Box>
            ))}
            </Box>
        </Stack>
    );
}

// ── DAG View ─────────────────────────────────────────────────

export function DagView({
    tasks,
    selectedDagTaskId,
    onSelectTask,
}: {
    tasks: OrchestrationTask[];
    selectedDagTaskId: string | null;
    onSelectTask: (taskId: string) => void;
}) {
    const theme = useTheme();
    const STATUS_COLORS: Record<string, string> = {
        completed: "#4caf50",
        approved: "#2e7d32",
        synced_to_github: "#4caf50",
        failed: "#f44336",
        in_progress: "#2196f3",
        queued: "#ff9800",
        planned: "#607d8b",
        blocked: "#9c27b0",
        backlog: "#9e9e9e",
        needs_review: "#ff9800",
    };

    const taskIndex = useMemo(() => Object.fromEntries(tasks.map((t, i) => [t.id, i])), [tasks]);

    const COLS = Math.min(4, tasks.length);
    const NODE_W = 160;
    const NODE_H = 50;
    const GAP_X = 60;
    const GAP_Y = 40;
    const PADDING = 20;

    const positions = useMemo(() => {
        return tasks.map((_, i) => ({
            x: PADDING + (i % COLS) * (NODE_W + GAP_X),
            y: PADDING + Math.floor(i / COLS) * (NODE_H + GAP_Y),
        }));
    }, [tasks, COLS]);

    const svgW = PADDING * 2 + COLS * (NODE_W + GAP_X) - GAP_X;
    const svgH = PADDING * 2 + Math.ceil(tasks.length / COLS) * (NODE_H + GAP_Y) - GAP_Y;

    const edges = useMemo(() => {
        const result: Array<{ x1: number; y1: number; x2: number; y2: number }> = [];
        for (const task of tasks) {
            for (const depId of task.dependency_ids ?? []) {
                const srcIdx = taskIndex[depId];
                const dstIdx = taskIndex[task.id];
                if (srcIdx === undefined || dstIdx === undefined) continue;
                const src = positions[srcIdx];
                const dst = positions[dstIdx];
                result.push({
                    x1: src.x + NODE_W / 2,
                    y1: src.y + NODE_H,
                    x2: dst.x + NODE_W / 2,
                    y2: dst.y,
                });
            }
        }
        return result;
    }, [tasks, positions, taskIndex]);

    if (tasks.length === 0) {
        return <EmptyState icon={<DagIcon />} title="No tasks yet" description="Add tasks to see the dependency graph." />;
    }

    return (
        <Box sx={{ overflow: "auto" }}>
            <svg width={svgW} height={svgH} style={{ display: "block" }}>
                <defs>
                    <marker id="arrow" markerWidth="8" markerHeight="8" refX="4" refY="4" orient="auto">
                        <path d="M0,0 L0,8 L8,4 z" fill="#999" />
                    </marker>
                </defs>
                {edges.map((edge, i) => (
                    <line
                        key={i}
                        x1={edge.x1} y1={edge.y1} x2={edge.x2} y2={edge.y2}
                        stroke="#999" strokeWidth={1.5} markerEnd="url(#arrow)"
                    />
                ))}
                {tasks.map((task, i) => {
                    const pos = positions[i];
                    const color = STATUS_COLORS[task.status] ?? "#9e9e9e";
                    const selected = task.id === selectedDagTaskId;
                    return (
                        <g
                            key={task.id}
                            role="button"
                            tabIndex={0}
                            style={{ cursor: "pointer" }}
                            onClick={() => onSelectTask(task.id)}
                            onKeyDown={(e) => {
                                if (e.key === "Enter" || e.key === " ") {
                                    e.preventDefault();
                                    onSelectTask(task.id);
                                }
                            }}
                        >
                            <rect
                                x={pos.x} y={pos.y} width={NODE_W} height={NODE_H}
                                rx={8} ry={8}
                                fill={color + "22"}
                                stroke={selected ? theme.palette.primary.main : color}
                                strokeWidth={selected ? 3 : 1.5}
                            />
                            <text
                                x={pos.x + NODE_W / 2} y={pos.y + 18}
                                textAnchor="middle" fontSize={11} fontWeight="600" fill={color}
                            >
                                {task.title.length > 20 ? task.title.slice(0, 19) + "…" : task.title}
                            </text>
                            <text
                                x={pos.x + NODE_W / 2} y={pos.y + 34}
                                textAnchor="middle" fontSize={10} fill="#888"
                            >
                                {task.status}
                            </text>
                        </g>
                    );
                })}
            </svg>
        </Box>
    );
}

// ── Main Page ────────────────────────────────────────────────

