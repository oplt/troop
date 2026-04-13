import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
    Alert,
    Box,
    Button,
    Chip,
    CircularProgress,
    Collapse,
    Dialog,
    DialogActions,
    DialogContent,
    DialogTitle,
    Divider,
    Drawer,
    IconButton,
    LinearProgress,
    Link,
    MenuItem,
    Paper,
    Stack,
    Switch,
    FormControlLabel,
    Tab,
    Tabs,
    TextField,
    Tooltip,
    Typography,
} from "@mui/material";
import { alpha, useTheme } from "@mui/material/styles";
import {
    AccountTree as DagIcon,
    CheckCircle as PassIcon,
    Cancel as FailIcon,
    CallSplit as DecomposeIcon,
    ExpandMore as ExpandMoreIcon,
    ExpandLess as ExpandLessIcon,
    OpenInNew as OpenInNewIcon,
    PlayArrow as RunIcon,
    Upload as UploadIcon,
} from "@mui/icons-material";
import { useNavigate, useParams } from "react-router-dom";
import {
    addProjectAgent,
    checkTaskAcceptance,
    createBrainstorm,
    createOrchestrationTask,
    createProjectDecision,
    createProjectMilestone,
    createTaskArtifact,
    decideApproval,
    deleteProjectDocument,
    deleteProjectMemoryEntry,
    decomposeTask,
    getOrchestrationProject,
    listAgents,
    listApprovals,
    listBrainstorms,
    listGithubIssueLinks,
    listGithubSyncEvents,
    listOrchestrationTasks,
    listProjectAgents,
    listProjectDecisions,
    listProjectDocuments,
    listProjectMemory,
    listProjectMilestones,
    listProviders,
    listRuns,
    searchProjectKnowledge,
    listSubtasks,
    listTaskArtifacts,
    startBrainstorm,
    startTaskRun,
    updateOrchestrationTask,
    updateOrchestrationProject,
    updateProjectAgent,
    updateProjectMilestone,
    uploadProjectDocument,
    getGateConfig,
    getTaskTimeline,
    listDagReadyTasks,
    listWorkflowTemplates,
    startDagParallelReady,
    startMergeResolutionRun,
    updateGateConfig,
} from "../api/orchestration";
import type { GateConfig, OrchestrationTask, ProviderConfig, TaskRun } from "../api/orchestration";
import { readOrchestrationSelectionMeta } from "../utils/orchestrationSelection";
import { useSnackbar } from "../app/snackbarContext";
import { EmptyState } from "../components/ui/EmptyState";
import { PageHeader } from "../components/ui/PageHeader";
import { PageShell } from "../components/ui/PageShell";
import { SectionCard } from "../components/ui/SectionCard";
import { formatDateTime, humanizeKey } from "../utils/formatters";

type DetailTab = "overview" | "board" | "dag" | "agents" | "brainstorms" | "decisions" | "github" | "knowledge" | "activity";
type ExecutionMode = "single_agent" | "manager_worker" | "debate";

const KANBAN_COLUMNS: { status: string; label: string; color: "default" | "warning" | "info" | "success" | "error" }[] = [
    { status: "backlog", label: "Backlog", color: "default" },
    { status: "queued", label: "Queued", color: "warning" },
    { status: "in_progress", label: "In Progress", color: "info" },
    { status: "needs_review", label: "Review", color: "warning" },
    { status: "completed", label: "Done", color: "success" },
    { status: "failed", label: "Failed", color: "error" },
];

// ── Acceptance Check Dialog ──────────────────────────────────

function AcceptanceDialog({
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
                        {data.checks.map((check) => (
                            <Stack key={check.name} direction="row" spacing={1} alignItems="flex-start">
                                {check.passed ? <PassIcon color="success" fontSize="small" /> : <FailIcon color="error" fontSize="small" />}
                                <Box>
                                    <Typography variant="body2">{check.name}</Typography>
                                    <Typography variant="caption" color="text.secondary">{check.detail}</Typography>
                                </Box>
                            </Stack>
                        ))}
                    </Stack>
                )}
            </DialogContent>
            <DialogActions><Button onClick={onClose}>Close</Button></DialogActions>
        </Dialog>
    );
}

// ── Subtask Panel ────────────────────────────────────────────

function SubtaskPanel({ projectId, taskId, taskTitle }: { projectId: string; taskId: string; taskTitle: string }) {
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();

    const { data: subtasks = [], isLoading } = useQuery({
        queryKey: ["orchestration", "subtasks", taskId],
        queryFn: () => listSubtasks(projectId, taskId),
    });

    const decomposeMutation = useMutation({
        mutationFn: () => decomposeTask(projectId, taskId),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "subtasks", taskId] });
            showToast({ message: "Task decomposed into subtasks.", severity: "success" });
        },
    });

    return (
        <Box>
            <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
                <Typography variant="caption" color="text.secondary">Subtasks of: {taskTitle}</Typography>
                <Button
                    size="small"
                    startIcon={decomposeMutation.isPending ? <CircularProgress size={12} /> : <DecomposeIcon />}
                    disabled={decomposeMutation.isPending}
                    onClick={() => decomposeMutation.mutate()}
                >
                    Decompose
                </Button>
            </Stack>
            {isLoading ? (
                <CircularProgress size={16} />
            ) : subtasks.length === 0 ? (
                <Typography variant="caption" color="text.secondary">No subtasks yet.</Typography>
            ) : (
                <Stack spacing={0.5}>
                    {subtasks.map((sub) => (
                        <Stack key={sub.id} direction="row" spacing={1} alignItems="center">
                            <Chip label={sub.status} size="small" variant="outlined" />
                            <Typography variant="body2">{sub.title}</Typography>
                        </Stack>
                    ))}
                </Stack>
            )}
        </Box>
    );
}

// ── Artifact Panel ───────────────────────────────────────────

function ArtifactPanel({ taskId }: { taskId: string }) {
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

// ── Kanban Board ─────────────────────────────────────────────

function KanbanBoard({
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
    const [dragging, setDragging] = useState<string | null>(null);
    const [expandedTask, setExpandedTask] = useState<string | null>(null);

    const moveMutation = useMutation({
        mutationFn: ({ taskId, status }: { taskId: string; status: string }) =>
            updateOrchestrationTask(projectId, taskId, { status }),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "tasks"] });
        },
    });
    const assignMutation = useMutation({
        mutationFn: ({
            taskId,
            assigned_agent_id,
        }: { taskId: string; assigned_agent_id: string | null }) =>
            updateOrchestrationTask(projectId, taskId, { assigned_agent_id }),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "tasks"] });
        },
    });
    const { data: timeline = [] } = useQuery({
        queryKey: ["orchestration", "project", projectId, "tasks", expandedTask, "timeline"],
        queryFn: () => (expandedTask ? getTaskTimeline(projectId, expandedTask) : Promise.resolve([])),
        enabled: Boolean(expandedTask),
    });

    function handleDragStart(e: React.DragEvent, taskId: string) {
        e.dataTransfer.setData("taskId", taskId);
        setDragging(taskId);
    }

    function handleDrop(e: React.DragEvent, status: string) {
        e.preventDefault();
        const taskId = e.dataTransfer.getData("taskId");
        if (taskId && tasks.find((t) => t.id === taskId)?.status !== status) {
            moveMutation.mutate({ taskId, status });
        }
        setDragging(null);
    }

    function handleDragOver(e: React.DragEvent) {
        e.preventDefault();
    }

    const tasksByStatus = useMemo(() => {
        const map: Record<string, OrchestrationTask[]> = {};
        for (const col of KANBAN_COLUMNS) map[col.status] = [];
        for (const task of tasks) {
            const col = KANBAN_COLUMNS.find((c) => c.status === task.status);
            if (col) map[col.status].push(task);
            else {
                if (!map["backlog"]) map["backlog"] = [];
                map["backlog"].push(task);
            }
        }
        return map;
    }, [tasks]);

    return (
        <Box sx={{ display: "flex", gap: 1.5, overflowX: "auto", pb: 1, minHeight: 400 }}>
            {KANBAN_COLUMNS.map((col) => (
                <Box
                    key={col.status}
                    onDrop={(e) => handleDrop(e, col.status)}
                    onDragOver={handleDragOver}
                    sx={(theme) => ({
                        minWidth: 260,
                        flex: "0 0 260px",
                        borderRadius: 3,
                        p: 1.5,
                        backgroundColor: alpha(theme.palette.background.paper, 0.6),
                        border: `1px solid ${theme.palette.divider}`,
                    })}
                >
                    <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1.5 }}>
                        <Chip label={col.label} color={col.color} size="small" />
                        <Typography variant="caption" color="text.secondary">{tasksByStatus[col.status]?.length ?? 0}</Typography>
                    </Stack>
                    <Stack spacing={1}>
                        {(tasksByStatus[col.status] ?? []).map((task) => {
                            const agent = allAgents.find((a) => a.id === task.assigned_agent_id);
                            const isExpanded = expandedTask === task.id;
                            const lastRun = lastRunByTaskId[task.id];
                            const runMeta = readOrchestrationSelectionMeta(lastRun);
                            const workerTip =
                                runMeta.worker_agent_rationale
                                || "The worker comes from the task assignment, an explicit run payload, or automatic routing. Run again to capture a fresh routing note.";
                            return (
                                <Paper
                                    key={task.id}
                                    draggable
                                    onDragStart={(e) => handleDragStart(e, task.id)}
                                    onDragEnd={() => setDragging(null)}
                                    sx={(theme) => ({
                                        p: 1.5,
                                        borderRadius: 3,
                                        cursor: "grab",
                                        opacity: dragging === task.id ? 0.4 : 1,
                                        border: `1px solid ${theme.palette.divider}`,
                                        "&:hover": { borderColor: theme.palette.primary.main },
                                    })}
                                >
                                    <Typography variant="subtitle2" sx={{ wordBreak: "break-word" }}>{task.title}</Typography>
                                    <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap sx={{ mt: 0.5 }}>
                                        <Chip label={task.priority} size="small" variant="outlined" />
                                        {agent && (
                                            <Tooltip title={workerTip}>
                                                <Chip label={agent.name} size="small" color="secondary" variant="outlined" />
                                            </Tooltip>
                                        )}
                                        {Boolean((task.result_payload.github_pr as Record<string, unknown> | undefined)?.number) && (
                                            <Chip
                                                label={`PR #${String((task.result_payload.github_pr as Record<string, unknown>).number)} · ${String(((task.result_payload.github_pr as Record<string, unknown>).state as string | undefined) || "open")}`}
                                                size="small"
                                                color="success"
                                                variant="outlined"
                                            />
                                        )}
                                        {task.due_date && (
                                            <Chip label={new Date(task.due_date).toLocaleDateString()} size="small" variant="outlined" />
                                        )}
                                    </Stack>
                                    {task.github_issue_number != null && (task.github_issue_url || task.github_repository_full_name) && (
                                        <Chip
                                            component={Link}
                                            href={
                                                task.github_issue_url
                                                || `https://github.com/${task.github_repository_full_name}/issues/${task.github_issue_number}`
                                            }
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            clickable
                                            size="small"
                                            variant="outlined"
                                            icon={<OpenInNewIcon sx={{ "&.MuiChip-icon": { fontSize: 16 } }} />}
                                            label={`#${task.github_issue_number}${task.github_repository_full_name ? ` · ${task.github_repository_full_name}` : ""}`}
                                            sx={{ mt: 0.5, maxWidth: "100%" }}
                                        />
                                    )}
                                    <Stack direction="row" spacing={0.5} sx={{ mt: 1 }}>
                                        <Button
                                            size="small"
                                            variant="text"
                                            startIcon={<RunIcon />}
                                            disabled={isRunPending && selectedTaskId === task.id}
                                            onClick={() => onRunTask(task.id, taskRunModes[task.id] ?? "single_agent", taskPrModes[task.id] ?? false)}
                                        >
                                            Run
                                        </Button>
                                        <Button size="small" variant="text" onClick={() => onAcceptanceCheck(task.id)}>
                                            Check
                                        </Button>
                                        <Button size="small" variant="text" onClick={() => setExpandedTask(isExpanded ? null : task.id)}>
                                            {isExpanded ? "Less" : "More"}
                                        </Button>
                                    </Stack>
                                    {isExpanded && (
                                        <Box sx={{ mt: 1.5 }}>
                                            <Divider sx={{ mb: 1 }} />
                                            <TextField
                                                select
                                                size="small"
                                                label="Assigned worker"
                                                value={task.assigned_agent_id ?? ""}
                                                onChange={(event) => assignMutation.mutate({
                                                    taskId: task.id,
                                                    assigned_agent_id: event.target.value || null,
                                                })}
                                                fullWidth
                                                sx={{ mb: 1 }}
                                            >
                                                <MenuItem value="">Unassigned</MenuItem>
                                                {allAgents.map((agent) => (
                                                    <MenuItem key={agent.id} value={agent.id}>{agent.name}</MenuItem>
                                                ))}
                                            </TextField>
                                            <TextField
                                                select
                                                size="small"
                                                label="Execution mode"
                                                value={taskRunModes[task.id] ?? "single_agent"}
                                                onChange={(event) => onModeChange(task.id, event.target.value as ExecutionMode)}
                                                fullWidth
                                                sx={{ mb: 1 }}
                                            >
                                                <MenuItem value="single_agent">Single agent: fast, cheap</MenuItem>
                                                <MenuItem value="manager_worker">Managed team: manager routes work</MenuItem>
                                                <MenuItem value="debate">Debate: two agents propose, moderator resolves</MenuItem>
                                            </TextField>
                                            <Button
                                                size="small"
                                                variant={taskPrModes[task.id] ? "contained" : "outlined"}
                                                onClick={() => onPrModeChange(task.id, !(taskPrModes[task.id] ?? false))}
                                                sx={{ mb: 1 }}
                                            >
                                                {taskPrModes[task.id] ? "PR generation on" : "Generate PR"}
                                            </Button>
                                            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                                                Task timeline (comments + GitHub sync)
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
                                                        </Paper>
                                                    ))
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
    );
}

// ── DAG View ─────────────────────────────────────────────────

function DagView({
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
        synced_to_github: "#4caf50",
        failed: "#f44336",
        in_progress: "#2196f3",
        queued: "#ff9800",
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
        return <EmptyState icon={<DagIcon />} title="No tasks yet" description="Create tasks to see the dependency graph." />;
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

export default function OrchestrationProjectDetailPage() {
    const { projectId = "" } = useParams();
    const navigate = useNavigate();
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();
    const [tab, setTab] = useState<DetailTab>("overview");
    const [taskForm, setTaskForm] = useState({
        title: "",
        description: "",
        priority: "normal",
        acceptance_criteria: "",
        due_date: "",
        response_sla_hours: "",
    });
    const [selectedTaskId, setSelectedTaskId] = useState<string>("");
    const [selectedAgentId, setSelectedAgentId] = useState("");
    const [brainstormTopic, setBrainstormTopic] = useState("");
    const [brainstormParticipants, setBrainstormParticipants] = useState("");
    const [milestoneForm, setMilestoneForm] = useState({ title: "", description: "", due_date: "" });
    const [decisionForm, setDecisionForm] = useState({ title: "", decision: "", rationale: "", author_label: "" });
    const [knowledgeQuery, setKnowledgeQuery] = useState("");
    const [documentTtlDays, setDocumentTtlDays] = useState("30");
    const [expandedDocumentId, setExpandedDocumentId] = useState<string | null>(null);
    const [githubForm, setGithubForm] = useState({
        branch_prefix: "troop/{task_id}-{slug}",
        auto_post_progress: false,
        auto_review_on_pr_review: false,
    });
    const [hitlForm, setHitlForm] = useState({
        sandbox_note: "",
        secret_scope: "project_default",
    });
    const [acceptanceTaskId, setAcceptanceTaskId] = useState<string | null>(null);
    const [taskRunModes, setTaskRunModes] = useState<Record<string, ExecutionMode>>({});
    const [taskPrModes, setTaskPrModes] = useState<Record<string, boolean>>({});
    const [dagDrawerTaskId, setDagDrawerTaskId] = useState<string | null>(null);
    const [projectTeamSettings, setProjectTeamSettings] = useState<null | {
        manager_agent_id: string;
        reviewer_agent_ids: string[];
        autonomy_level: string;
        provider_config_id: string;
        model_name: string;
        fallback_model: string;
        stuck_for_minutes: string;
        cost_exceeds_usd: string;
        no_consensus_after_rounds: string;
        routing_mode: string;
        sibling_load_balance: string;
        skip_unhealthy_worker_providers: boolean;
        sla_enabled: boolean;
        sla_warn_hours: string;
        sla_escalate_after_due_hours: string;
    }>(null);

    const { data: project } = useQuery({
        queryKey: ["orchestration", "project", projectId],
        queryFn: () => getOrchestrationProject(projectId),
        enabled: Boolean(projectId),
    });
    const { data: tasks = [] } = useQuery({
        queryKey: ["orchestration", "project", projectId, "tasks"],
        queryFn: () => listOrchestrationTasks(projectId),
        enabled: Boolean(projectId),
    });
    const { data: allAgents = [] } = useQuery({
        queryKey: ["orchestration", "agents"],
        queryFn: () => listAgents(),
    });
    const { data: providers = [] } = useQuery({
        queryKey: ["orchestration", "providers"],
        queryFn: () => listProviders(),
    });
    const { data: projectAgents = [] } = useQuery({
        queryKey: ["orchestration", "project", projectId, "agents"],
        queryFn: () => listProjectAgents(projectId),
        enabled: Boolean(projectId),
    });
    const { data: brainstorms = [] } = useQuery({
        queryKey: ["orchestration", "project", projectId, "brainstorms"],
        queryFn: () => listBrainstorms(projectId),
        enabled: Boolean(projectId),
    });
    const { data: runs = [] } = useQuery({
        queryKey: ["orchestration", "project", projectId, "runs"],
        queryFn: () => listRuns(projectId),
        enabled: Boolean(projectId),
    });
    const lastRunByTaskId = useMemo(() => {
        const m: Record<string, TaskRun> = {};
        for (const r of runs) {
            if (r.task_id && m[r.task_id] === undefined) {
                m[r.task_id] = r;
            }
        }
        return m;
    }, [runs]);
    const { data: docs = [] } = useQuery({
        queryKey: ["orchestration", "project", projectId, "documents"],
        queryFn: () => listProjectDocuments(projectId),
        enabled: Boolean(projectId),
    });
    const { data: knowledgeResults = [] } = useQuery({
        queryKey: ["orchestration", "project", projectId, "knowledge", knowledgeQuery],
        queryFn: () => searchProjectKnowledge(projectId, knowledgeQuery),
        enabled: Boolean(projectId) && knowledgeQuery.trim().length >= 3,
    });
    const { data: memoryEntries = [] } = useQuery({
        queryKey: ["orchestration", "project", projectId, "memory"],
        queryFn: () => listProjectMemory(projectId),
        enabled: Boolean(projectId),
    });
    const { data: approvals = [] } = useQuery({
        queryKey: ["orchestration", "approvals"],
        queryFn: () => listApprovals(),
    });
    const { data: issueLinks = [] } = useQuery({
        queryKey: ["orchestration", "project", projectId, "issues"],
        queryFn: () => listGithubIssueLinks(projectId),
        enabled: Boolean(projectId),
    });
    const { data: syncEvents = [] } = useQuery({
        queryKey: ["orchestration", "project", projectId, "sync-events"],
        queryFn: () => listGithubSyncEvents(projectId),
        enabled: Boolean(projectId),
    });
    const { data: milestones = [] } = useQuery({
        queryKey: ["orchestration", "project", projectId, "milestones"],
        queryFn: () => listProjectMilestones(projectId),
        enabled: Boolean(projectId),
    });
    const { data: decisions = [] } = useQuery({
        queryKey: ["orchestration", "project", projectId, "decisions"],
        queryFn: () => listProjectDecisions(projectId),
        enabled: Boolean(projectId),
    });
    const { data: gateConfig } = useQuery<GateConfig>({
        queryKey: ["orchestration", "project", projectId, "gate-config"],
        queryFn: () => getGateConfig(projectId),
        enabled: Boolean(projectId),
    });
    const { data: workflowTemplates = [] } = useQuery({
        queryKey: ["orchestration", "workflow-templates"],
        queryFn: () => listWorkflowTemplates(),
    });

    useEffect(() => {
        if (!project) return;
        const gh = (project.settings?.github as Record<string, unknown> | undefined) ?? {};
        setGithubForm({
            branch_prefix: String(gh.branch_prefix ?? "troop/{task_id}-{slug}"),
            auto_post_progress: Boolean(gh.auto_post_progress),
            auto_review_on_pr_review: Boolean(gh.auto_review_on_pr_review),
        });
        const hitl = (project.settings?.hitl as Record<string, unknown> | undefined) ?? {};
        setHitlForm({
            sandbox_note: String(hitl.sandbox_note ?? ""),
            secret_scope: String(hitl.secret_scope ?? "project_default"),
        });
    }, [project?.id, project?.updated_at, project]);

    const { data: dagReadyList = [] } = useQuery({
        queryKey: ["orchestration", "project", projectId, "dag-ready"],
        queryFn: () => listDagReadyTasks(projectId),
        enabled: Boolean(projectId) && tab === "dag",
    });

    const projectAgentMap = useMemo(() => new Set(projectAgents.map((item) => item.agent_id)), [projectAgents]);
    const availableAgents = allAgents.filter((agent) => !projectAgentMap.has(agent.id));
    const activeRuns = runs.filter((item) => ["queued", "in_progress"].includes(item.status));
    const dagTask = useMemo(
        () => (dagDrawerTaskId ? tasks.find((t) => t.id === dagDrawerTaskId) ?? null : null),
        [tasks, dagDrawerTaskId],
    );
    const dagTaskLatestRun = useMemo(() => {
        if (!dagTask) return null;
        const forTask = [...runs].filter((r) => r.task_id === dagTask.id);
        forTask.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
        return forTask[0] ?? null;
    }, [runs, dagTask]);
    const dagTaskSubtasks = useMemo(() => {
        if (!dagTask) return [];
        return tasks.filter((t) => t.parent_task_id === dagTask.id);
    }, [tasks, dagTask]);
    const executionSettings = ((project?.settings?.execution as Record<string, unknown> | undefined) ?? {}) as Record<string, unknown>;
    const resolvedProjectTeamSettings = projectTeamSettings ?? {
        manager_agent_id: String((executionSettings.manager_agent_id as string | undefined) ?? ""),
        reviewer_agent_ids: Array.isArray(executionSettings.reviewer_agent_ids) ? executionSettings.reviewer_agent_ids as string[] : [],
        autonomy_level: String((executionSettings.autonomy_level as string | undefined) ?? "semi-autonomous"),
        provider_config_id: String((executionSettings.provider_config_id as string | undefined) ?? ""),
        model_name: String((executionSettings.model_name as string | undefined) ?? ""),
        fallback_model: String((executionSettings.fallback_model as string | undefined) ?? ""),
        stuck_for_minutes: String((((executionSettings.escalation_rules as Array<Record<string, unknown>> | undefined) ?? []).find((item) => item.condition === "stuck_for_minutes")?.value as number | undefined) ?? 30),
        cost_exceeds_usd: String((((executionSettings.escalation_rules as Array<Record<string, unknown>> | undefined) ?? []).find((item) => item.condition === "cost_exceeds_usd")?.value as number | undefined) ?? 10),
        no_consensus_after_rounds: String((((executionSettings.escalation_rules as Array<Record<string, unknown>> | undefined) ?? []).find((item) => item.condition === "no_consensus_after_rounds")?.value as number | undefined) ?? 3),
        routing_mode: String((executionSettings.routing_mode as string | undefined) ?? "balanced"),
        sibling_load_balance: String((executionSettings.sibling_load_balance as string | undefined) ?? "queue_depth"),
        skip_unhealthy_worker_providers: executionSettings.skip_unhealthy_worker_providers !== false,
        sla_enabled: ((executionSettings.sla as Record<string, unknown> | undefined)?.enabled as boolean | undefined) !== false,
        sla_warn_hours: String(((executionSettings.sla as Record<string, unknown> | undefined)?.warn_hours_before_due as number | undefined) ?? 24),
        sla_escalate_after_due_hours: String(((executionSettings.sla as Record<string, unknown> | undefined)?.escalate_hours_after_due as number | undefined) ?? 0),
    };

    const milestoneProgress = milestones.length === 0 ? 0
        : Math.round((milestones.filter((m) => m.status === "completed").length / milestones.length) * 100);

    const addAgentMutation = useMutation({
        mutationFn: (payload: Record<string, unknown>) => addProjectAgent(projectId, payload),
        onSuccess: async () => {
            setSelectedAgentId("");
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "agents"] });
            showToast({ message: "Agent assigned to project.", severity: "success" });
        },
    });
    const createTaskMutation = useMutation({
        mutationFn: (payload: Record<string, unknown>) => createOrchestrationTask(projectId, payload),
        onSuccess: async () => {
            setTaskForm({
                title: "",
                description: "",
                priority: "normal",
                acceptance_criteria: "",
                due_date: "",
                response_sla_hours: "",
            });
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "tasks"] });
            showToast({ message: "Task created.", severity: "success" });
        },
    });
    const runMutation = useMutation({
        mutationFn: ({ taskId, runMode, createPr }: { taskId: string; runMode: ExecutionMode; createPr: boolean }) =>
            startTaskRun(projectId, taskId, { run_mode: runMode, input_payload: { create_pr: createPr, draft_pr: true } }),
        onSuccess: async (run) => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "runs"] });
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "tasks"] });
            showToast({ message: "Run started.", severity: "success" });
            navigate(`/runs/${run.id}`);
        },
    });
    const dagParallelMutation = useMutation({
        mutationFn: () =>
            startDagParallelReady(projectId, {
                run_mode: "single_agent",
                limit: 12,
                input_payload: { dag_parallel_wave: true },
            }),
        onSuccess: async (res) => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "runs"] });
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "tasks"] });
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "dag-ready"] });
            showToast({
                message: `Started ${res.started_run_ids.length} parallel run(s).${res.skipped_task_ids.length ? ` ${res.skipped_task_ids.length} skipped (see messages).` : ""}`,
                severity: res.started_run_ids.length ? "success" : "warning",
            });
        },
    });
    const mergeResolutionMutation = useMutation({
        mutationFn: (parentTaskId: string) =>
            startMergeResolutionRun(projectId, parentTaskId, { notes: "Merge branches from project DAG." }),
        onSuccess: async (run) => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "runs"] });
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "tasks"] });
            showToast({ message: "Merge resolution run queued.", severity: "success" });
            navigate(`/runs/${run.id}`);
        },
    });
    const updateMembershipMutation = useMutation({
        mutationFn: ({ membershipId, payload }: { membershipId: string; payload: Record<string, unknown> }) =>
            updateProjectAgent(projectId, membershipId, payload),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "agents"] });
            showToast({ message: "Project team updated.", severity: "success" });
        },
    });
    const saveProjectSettingsMutation = useMutation({
        mutationFn: (payload: Record<string, unknown>) => updateOrchestrationProject(projectId, payload),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId] });
            showToast({ message: "Project execution settings saved.", severity: "success" });
        },
    });
    const updateGateConfigMutation = useMutation({
        mutationFn: (payload: Partial<GateConfig>) => updateGateConfig(projectId, payload),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "gate-config"] });
            showToast({ message: "Gate configuration saved.", severity: "success" });
        },
    });
    const brainstormMutation = useMutation({
        mutationFn: (payload: Record<string, unknown>) => createBrainstorm(payload),
        onSuccess: async (brainstorm) => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "brainstorms"] });
            showToast({ message: "Brainstorm created.", severity: "success" });
            await startBrainstorm(brainstorm.id);
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "runs"] });
        },
    });
    const milestoneMutation = useMutation({
        mutationFn: (payload: Record<string, unknown>) => createProjectMilestone(projectId, payload),
        onSuccess: async () => {
            setMilestoneForm({ title: "", description: "", due_date: "" });
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "milestones"] });
            showToast({ message: "Milestone created.", severity: "success" });
        },
    });
    const toggleMilestoneMutation = useMutation({
        mutationFn: ({ id, status }: { id: string; status: string }) =>
            updateProjectMilestone(projectId, id, { status }),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "milestones"] });
        },
    });
    const decisionMutation = useMutation({
        mutationFn: (payload: Record<string, unknown>) => createProjectDecision(projectId, payload),
        onSuccess: async () => {
            setDecisionForm({ title: "", decision: "", rationale: "", author_label: "" });
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "decisions"] });
            showToast({ message: "Decision recorded.", severity: "success" });
        },
    });
    const uploadDocumentMutation = useMutation({
        mutationFn: (file: File) =>
            uploadProjectDocument(
                projectId,
                file,
                undefined,
                Number(documentTtlDays || 0) || undefined,
            ),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "documents"] });
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "knowledge"] });
            showToast({ message: "Knowledge document uploaded.", severity: "success" });
        },
    });
    const deleteDocumentMutation = useMutation({
        mutationFn: (documentId: string) => deleteProjectDocument(projectId, documentId),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "documents"] });
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "knowledge"] });
            showToast({ message: "Knowledge document removed.", severity: "success" });
        },
    });
    const deleteMemoryMutation = useMutation({
        mutationFn: (memoryId: string) => deleteProjectMemoryEntry(projectId, memoryId),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "memory"] });
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "approvals"] });
            showToast({ message: "Memory entry removed.", severity: "success" });
        },
    });
    const memoryApprovalMutation = useMutation({
        mutationFn: ({ approvalId, status }: { approvalId: string; status: "approved" | "rejected" }) =>
            decideApproval(approvalId, { status }),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "memory"] });
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "approvals"] });
            showToast({ message: "Memory review updated.", severity: "success" });
        },
    });
    const pendingMemoryApprovals = approvals.filter(
        (approval) => approval.project_id === projectId && approval.approval_type === "agent_memory_write" && approval.status === "pending",
    );

    const providerOptions: ProviderConfig[] = providers;
    const saveProjectExecutionSettings = () => {
        const escalationRules = [
            {
                condition: "stuck_for_minutes",
                value: Number(resolvedProjectTeamSettings.stuck_for_minutes || 0),
                escalate_to: resolvedProjectTeamSettings.manager_agent_id || null,
            },
            {
                condition: "cost_exceeds_usd",
                value: Number(resolvedProjectTeamSettings.cost_exceeds_usd || 0),
                escalate_to: resolvedProjectTeamSettings.manager_agent_id || null,
            },
            {
                condition: "no_consensus_after_rounds",
                value: Number(resolvedProjectTeamSettings.no_consensus_after_rounds || 0),
                escalate_to: resolvedProjectTeamSettings.manager_agent_id || null,
            },
        ];
        saveProjectSettingsMutation.mutate({
            settings: {
                ...(project?.settings ?? {}),
                execution: {
                    ...executionSettings,
                    manager_agent_id: resolvedProjectTeamSettings.manager_agent_id || null,
                    reviewer_agent_ids: resolvedProjectTeamSettings.reviewer_agent_ids,
                    autonomy_level: resolvedProjectTeamSettings.autonomy_level,
                    provider_config_id: resolvedProjectTeamSettings.provider_config_id || null,
                    model_name: resolvedProjectTeamSettings.model_name || null,
                    fallback_model: resolvedProjectTeamSettings.fallback_model || null,
                    escalation_rules: escalationRules,
                    routing_mode: resolvedProjectTeamSettings.routing_mode || "balanced",
                    sibling_load_balance: resolvedProjectTeamSettings.sibling_load_balance || "queue_depth",
                    skip_unhealthy_worker_providers: resolvedProjectTeamSettings.skip_unhealthy_worker_providers,
                    sla: {
                        enabled: resolvedProjectTeamSettings.sla_enabled,
                        warn_hours_before_due: Number(resolvedProjectTeamSettings.sla_warn_hours || 24),
                        escalate_hours_after_due: Number(resolvedProjectTeamSettings.sla_escalate_after_due_hours || 0),
                    },
                },
            },
        });
    };

    const saveGithubIntegration = () => {
        saveProjectSettingsMutation.mutate({
            settings: {
                ...(project?.settings ?? {}),
                github: {
                    ...((project?.settings?.github as Record<string, unknown> | undefined) ?? {}),
                    branch_prefix: githubForm.branch_prefix,
                    auto_post_progress: githubForm.auto_post_progress,
                    auto_review_on_pr_review: githubForm.auto_review_on_pr_review,
                },
            },
        });
    };

    const saveHitlSettings = () => {
        saveProjectSettingsMutation.mutate({
            settings: {
                ...(project?.settings ?? {}),
                hitl: {
                    ...((project?.settings?.hitl as Record<string, unknown> | undefined) ?? {}),
                    sandbox_note: hitlForm.sandbox_note,
                    secret_scope: hitlForm.secret_scope,
                },
            },
        });
    };

    if (!project) {
        return (
            <PageShell maxWidth="xl">
                <Typography color="text.secondary">Loading project...</Typography>
            </PageShell>
        );
    }

    return (
        <PageShell maxWidth="xl">
            <PageHeader
                eyebrow="Project"
                title={project.name}
                description={project.description || "No project description yet."}
                meta={
                    <Typography variant="body2" color="text.secondary">
                        {tasks.length} tasks • {projectAgents.length} agents • {activeRuns.length} active runs
                    </Typography>
                }
                actions={
                    <Stack direction="row" spacing={1}>
                        <Button
                            variant="outlined"
                            size="small"
                            onClick={() => navigate(`/agent-projects/${projectId}/memory`)}
                        >
                            Memory
                        </Button>
                        <Button variant="outlined" size="small" onClick={() => navigate(`/agent-projects/${projectId}/benchmark`)}>
                            Benchmarks
                        </Button>
                    </Stack>
                }
            />

            <Paper sx={{ mb: 2, borderRadius: 4, p: 1 }}>
                <Tabs value={tab} onChange={(_, value) => setTab(value)} variant="scrollable" scrollButtons="auto">
                    <Tab label="Overview" value="overview" />
                    <Tab label="Board" value="board" />
                    <Tab label="DAG" value="dag" />
                    <Tab label="Agents" value="agents" />
                    <Tab label="Brainstorms" value="brainstorms" />
                    <Tab label="Decisions" value="decisions" />
                    <Tab label="GitHub" value="github" />
                    <Tab label="Knowledge" value="knowledge" />
                    <Tab label="Activity" value="activity" />
                </Tabs>
            </Paper>

            {/* ── Overview ── */}
            {tab === "overview" && (
                <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", xl: "1.2fr 1fr" } }}>
                    <Stack spacing={2}>
                        <SectionCard title="Goals" description="High-level objectives and context for prompt assembly.">
                            <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>{project.goals_markdown || "No goals recorded yet."}</Typography>
                        </SectionCard>
                        <SectionCard
                            title={`Milestones ${milestones.length > 0 ? `(${milestoneProgress}% complete)` : ""}`}
                            description="Track project milestones and overall progress."
                        >
                            {milestones.length > 0 && (
                                <Box sx={{ mb: 2 }}>
                                    <LinearProgress variant="determinate" value={milestoneProgress} sx={{ height: 6, borderRadius: 3 }} />
                                    <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: "block" }}>
                                        {milestones.filter((m) => m.status === "completed").length} / {milestones.length} completed
                                    </Typography>
                                </Box>
                            )}
                            <Stack spacing={1}>
                                {milestones.map((m) => (
                                    <Stack key={m.id} direction="row" spacing={1} alignItems="center">
                                        <Chip
                                            label={m.status}
                                            color={m.status === "completed" ? "success" : "default"}
                                            size="small"
                                            onClick={() => toggleMilestoneMutation.mutate({
                                                id: m.id,
                                                status: m.status === "completed" ? "open" : "completed",
                                            })}
                                            sx={{ cursor: "pointer" }}
                                        />
                                        <Box flex={1}>
                                            <Typography variant="body2">{m.title}</Typography>
                                            {m.due_date && <Typography variant="caption" color="text.secondary">Due {new Date(m.due_date).toLocaleDateString()}</Typography>}
                                        </Box>
                                    </Stack>
                                ))}
                            </Stack>
                            <Divider sx={{ my: 1.5 }} />
                            <Stack spacing={1}>
                                <TextField size="small" label="Milestone title" value={milestoneForm.title} onChange={(e) => setMilestoneForm((f) => ({ ...f, title: e.target.value }))} />
                                <TextField
                                    size="small" type="date" label="Due date"
                                    InputLabelProps={{ shrink: true }}
                                    value={milestoneForm.due_date}
                                    onChange={(e) => setMilestoneForm((f) => ({ ...f, due_date: e.target.value }))}
                                />
                                <Button
                                    size="small" variant="outlined"
                                    disabled={!milestoneForm.title.trim()}
                                    onClick={() => milestoneMutation.mutate({
                                        title: milestoneForm.title,
                                        due_date: milestoneForm.due_date || null,
                                    })}
                                >
                                    Add milestone
                                </Button>
                            </Stack>
                        </SectionCard>
                    </Stack>
                    <Stack spacing={2}>
                        <SectionCard title="Status" description="Operational summary.">
                            <Stack spacing={1.25}>
                                <Chip label={project.status} color="primary" variant="outlined" />
                                <Typography variant="body2" color="text.secondary">Memory scope: {project.memory_scope}</Typography>
                                <Typography variant="body2" color="text.secondary">{project.knowledge_summary || "No knowledge summary yet."}</Typography>
                                <Divider />
                                <Typography variant="subtitle2">Execution policy</Typography>
                                <Typography variant="body2" color="text.secondary">
                                    Autonomy: {String(executionSettings.autonomy_level ?? "semi-autonomous")}
                                </Typography>
                                <Typography variant="body2" color="text.secondary">
                                    Manager: {allAgents.find((agent) => agent.id === executionSettings.manager_agent_id)?.name || "not configured"}
                                </Typography>
                                <Divider />
                                <Typography variant="subtitle2">Recent runs</Typography>
                                {runs.slice(0, 4).map((run) => {
                                    const rm = readOrchestrationSelectionMeta(run);
                                    const tip = [rm.worker_agent_rationale, rm.model_rationale].filter(Boolean).join("\n\n");
                                    return (
                                        <Tooltip
                                            key={run.id}
                                            title={tip || "Open the run inspector for routing details and the full event log."}
                                        >
                                            <Stack direction="row" spacing={1} alignItems="center">
                                                <Box flex={1}>
                                                    <Typography variant="body2">{humanizeKey(run.run_mode)} • {humanizeKey(run.status)}</Typography>
                                                    <Typography variant="caption" color="text.secondary">{formatDateTime(run.created_at)}</Typography>
                                                </Box>
                                                <Button size="small" variant="text" onClick={() => navigate(`/runs/${run.id}`)}>Inspect</Button>
                                            </Stack>
                                        </Tooltip>
                                    );
                                })}
                            </Stack>
                        </SectionCard>
                        <SectionCard
                            title="Operating mode behavior"
                            description="How execution autonomy (project execution) interacts with approval gates (gate config). Tune both under Agents → Execution settings and Approval gates."
                        >
                            <Stack spacing={1}>
                                <Typography variant="caption" color="text.secondary">
                                    Execution autonomy: {String(executionSettings.autonomy_level ?? "semi-autonomous")}
                                    {" · "}
                                    Gate autonomy: {String(gateConfig?.autonomy_level ?? "assisted")}
                                </Typography>
                                <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 2 }}>
                                    <Typography variant="subtitle2" sx={{ mb: 0.5 }}>Assisted</Typography>
                                    <Typography variant="body2" color="text.secondary">
                                        Human gates stay on; agents propose plans, diffs, and comments. Best for production systems and external writes.
                                    </Typography>
                                </Paper>
                                <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 2 }}>
                                    <Typography variant="subtitle2" sx={{ mb: 0.5 }}>Semi-autonomous</Typography>
                                    <Typography variant="body2" color="text.secondary">
                                        Default mix: routine tool calls and runs proceed with telemetry, risky actions still hit approval gates when configured.
                                    </Typography>
                                </Paper>
                                <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 2 }}>
                                    <Typography variant="subtitle2" sx={{ mb: 0.5 }}>Autonomous</Typography>
                                    <Typography variant="body2" color="text.secondary">
                                        Gate config can short-circuit approvals; combine only with read-only or tightly scoped agents and budgets.
                                    </Typography>
                                </Paper>
                            </Stack>
                        </SectionCard>
                        <SectionCard
                            title="Workflow templates"
                            description="Starter playbooks for portfolio-scale work. Suggested settings are hints — apply from Execution settings after you pick a lane."
                        >
                            <Stack spacing={1}>
                                {workflowTemplates.map((tpl) => (
                                    <Paper key={tpl.id} variant="outlined" sx={{ p: 1.5, borderRadius: 2 }}>
                                        <Typography variant="subtitle2">{tpl.name}</Typography>
                                        <Typography variant="body2" color="text.secondary">{tpl.description}</Typography>
                                        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
                                            Suggested: {JSON.stringify(tpl.suggested_execution)}
                                        </Typography>
                                    </Paper>
                                ))}
                            </Stack>
                        </SectionCard>
                    </Stack>
                </Box>
            )}

            {/* ── Board ── */}
            {tab === "board" && (
                <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", xl: "340px minmax(0,1fr)" }, alignItems: "start" }}>
                    <SectionCard title="Create task" description="Add a task to the board directly.">
                        <Stack spacing={2}>
                            <TextField label="Title" value={taskForm.title} onChange={(e) => setTaskForm((f) => ({ ...f, title: e.target.value }))} />
                            <TextField label="Description" value={taskForm.description} onChange={(e) => setTaskForm((f) => ({ ...f, description: e.target.value }))} multiline minRows={3} />
                            <TextField select label="Priority" value={taskForm.priority} onChange={(e) => setTaskForm((f) => ({ ...f, priority: e.target.value }))}>
                                {["low", "normal", "high", "urgent"].map((p) => <MenuItem key={p} value={p}>{p}</MenuItem>)}
                            </TextField>
                            <TextField label="Acceptance criteria" value={taskForm.acceptance_criteria} onChange={(e) => setTaskForm((f) => ({ ...f, acceptance_criteria: e.target.value }))} multiline minRows={2} />
                            <TextField
                                label="Due date (ISO)"
                                helperText="Optional. Used with SLA scan and routing."
                                value={taskForm.due_date}
                                onChange={(e) => setTaskForm((f) => ({ ...f, due_date: e.target.value }))}
                                placeholder="2026-12-31T17:00:00Z"
                            />
                            <TextField
                                label="Response SLA (hours)"
                                helperText="Optional. Counted from task creation if no due date; otherwise earliest of due date vs created + hours."
                                value={taskForm.response_sla_hours}
                                onChange={(e) => setTaskForm((f) => ({ ...f, response_sla_hours: e.target.value }))}
                                type="number"
                            />
                            <Button
                                variant="contained"
                                disabled={!taskForm.title.trim()}
                                onClick={() => {
                                    const n = Number(taskForm.response_sla_hours);
                                    createTaskMutation.mutate({
                                        title: taskForm.title,
                                        description: taskForm.description,
                                        priority: taskForm.priority,
                                        acceptance_criteria: taskForm.acceptance_criteria || null,
                                        due_date: taskForm.due_date.trim() ? taskForm.due_date.trim() : null,
                                        response_sla_hours: taskForm.response_sla_hours.trim() && !Number.isNaN(n) && n > 0 ? n : null,
                                    });
                                }}
                            >
                                Create task
                            </Button>
                            {createTaskMutation.isError && <Alert severity="error">Failed to create task.</Alert>}
                        </Stack>
                    </SectionCard>
                    <Box>
                        <KanbanBoard
                            projectId={projectId}
                            tasks={tasks}
                            allAgents={allAgents}
                            lastRunByTaskId={lastRunByTaskId}
                            onRunTask={(taskId, mode, createPr) => { setSelectedTaskId(taskId); runMutation.mutate({ taskId, runMode: mode, createPr }); }}
                            onAcceptanceCheck={(taskId) => setAcceptanceTaskId(taskId)}
                            isRunPending={runMutation.isPending}
                            selectedTaskId={selectedTaskId}
                            taskRunModes={taskRunModes}
                            taskPrModes={taskPrModes}
                            onModeChange={(taskId, mode) => setTaskRunModes((current) => ({ ...current, [taskId]: mode }))}
                            onPrModeChange={(taskId, enabled) => setTaskPrModes((current) => ({ ...current, [taskId]: enabled }))}
                        />
                    </Box>
                </Box>
            )}

            {/* ── DAG ── */}
            {tab === "dag" && (
                <Stack spacing={2}>
                    <SectionCard
                        title="Parallel DAG execution"
                        description="Start a run for every task whose dependencies are satisfied (backlog or planned, no active run). Celery executes runs concurrently. Use merge when several subtasks under one parent finished with different assignees."
                    >
                        <Stack spacing={1.5}>
                            <Typography variant="body2" color="text.secondary">
                                Ready now: {dagReadyList.length} task{dagReadyList.length === 1 ? "" : "s"}
                            </Typography>
                            {dagParallelMutation.data?.messages?.length ? (
                                <Alert severity="info">
                                    {dagParallelMutation.data.messages.slice(0, 4).join(" · ")}
                                </Alert>
                            ) : null}
                            <Button
                                variant="contained"
                                disabled={dagParallelMutation.isPending || dagReadyList.length === 0}
                                onClick={() => dagParallelMutation.mutate()}
                            >
                                Start parallel runs for ready tasks
                            </Button>
                        </Stack>
                    </SectionCard>
                    <SectionCard title="Task dependency graph" description="Nodes represent tasks; click a node for details and shortcuts. Arrows point from dependency → dependent. Drag tasks on the board tab to change status.">
                        <DagView
                            tasks={tasks}
                            selectedDagTaskId={dagDrawerTaskId}
                            onSelectTask={(id) => setDagDrawerTaskId(id)}
                        />
                    </SectionCard>
                </Stack>
            )}

            {/* ── Agents ── */}
            {tab === "agents" && (
                <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", xl: "340px minmax(0, 1fr)" } }}>
                    <SectionCard title="Assign agent" description="Attach global or project agents to the project hierarchy.">
                        <Stack spacing={2}>
                            <TextField select label="Agent" value={selectedAgentId} onChange={(e) => setSelectedAgentId(e.target.value)}>
                                {availableAgents.map((agent) => <MenuItem key={agent.id} value={agent.id}>{agent.name}</MenuItem>)}
                            </TextField>
                            <Button variant="contained" onClick={() => addAgentMutation.mutate({ agent_id: selectedAgentId, role: "member" })} disabled={!selectedAgentId}>
                                Add agent
                            </Button>
                        </Stack>
                    </SectionCard>
                    <Stack spacing={2}>
                        <SectionCard title="Project team" description="Assigned agents define who can execute, review, and moderate work inside this project.">
                            <Stack spacing={1.5}>
                                {projectAgents.map((membership) => {
                                    const agent = allAgents.find((item) => item.id === membership.agent_id);
                                    return (
                                        <Paper key={membership.id} sx={{ p: 2, borderRadius: 4 }}>
                                            <Stack direction={{ xs: "column", md: "row" }} spacing={2} alignItems={{ xs: "stretch", md: "center" }}>
                                                <Box sx={{ flex: 1 }}>
                                                    <Typography variant="subtitle2">{agent?.name || membership.agent_id}</Typography>
                                                    <Typography variant="body2" color="text.secondary">{agent?.slug || membership.agent_id}</Typography>
                                                </Box>
                                                <TextField
                                                    select
                                                    size="small"
                                                    label="Role"
                                                    value={membership.role}
                                                    onChange={(event) => updateMembershipMutation.mutate({
                                                        membershipId: membership.id,
                                                        payload: { role: event.target.value },
                                                    })}
                                                    sx={{ minWidth: 170 }}
                                                >
                                                    <MenuItem value="member">Member</MenuItem>
                                                    <MenuItem value="manager">Manager</MenuItem>
                                                    <MenuItem value="reviewer">Reviewer</MenuItem>
                                                    <MenuItem value="moderator">Moderator</MenuItem>
                                                </TextField>
                                                <Button
                                                    size="small"
                                                    variant={membership.is_default_manager ? "contained" : "outlined"}
                                                    onClick={() => updateMembershipMutation.mutate({
                                                        membershipId: membership.id,
                                                        payload: { is_default_manager: !membership.is_default_manager },
                                                    })}
                                                >
                                                    {membership.is_default_manager ? "Default manager" : "Make manager"}
                                                </Button>
                                            </Stack>
                                        </Paper>
                                    );
                                })}
                            </Stack>
                        </SectionCard>
                        <SectionCard title="Execution settings" description="Configure per-project team routing, autonomy, model policy, and escalation rules.">
                            <Stack spacing={2}>
                                <TextField
                                    select
                                    label="Manager agent"
                                    value={resolvedProjectTeamSettings.manager_agent_id}
                                    onChange={(event) => setProjectTeamSettings((current) => ({ ...(current ?? resolvedProjectTeamSettings), manager_agent_id: event.target.value }))}
                                >
                                    <MenuItem value="">None</MenuItem>
                                    {projectAgents.map((membership) => {
                                        const agent = allAgents.find((item) => item.id === membership.agent_id);
                                        return <MenuItem key={membership.id} value={membership.agent_id}>{agent?.name || membership.agent_id}</MenuItem>;
                                    })}
                                </TextField>
                                <TextField
                                    select
                                    SelectProps={{ multiple: true }}
                                    label="Reviewer agents"
                                    value={resolvedProjectTeamSettings.reviewer_agent_ids}
                                    onChange={(event) => setProjectTeamSettings((current) => ({
                                        ...(current ?? resolvedProjectTeamSettings),
                                        reviewer_agent_ids: typeof event.target.value === "string" ? [event.target.value] : event.target.value,
                                    }))}
                                >
                                    {projectAgents.map((membership) => {
                                        const agent = allAgents.find((item) => item.id === membership.agent_id);
                                        return <MenuItem key={`reviewer-${membership.id}`} value={membership.agent_id}>{agent?.name || membership.agent_id}</MenuItem>;
                                    })}
                                </TextField>
                                <TextField
                                    select
                                    label="Autonomy level"
                                    value={resolvedProjectTeamSettings.autonomy_level}
                                    onChange={(event) => setProjectTeamSettings((current) => ({ ...(current ?? resolvedProjectTeamSettings), autonomy_level: event.target.value }))}
                                >
                                    <MenuItem value="assisted">Assisted</MenuItem>
                                    <MenuItem value="semi-autonomous">Semi-autonomous</MenuItem>
                                    <MenuItem value="autonomous">Autonomous</MenuItem>
                                </TextField>
                                <TextField
                                    select
                                    label="Provider override"
                                    value={resolvedProjectTeamSettings.provider_config_id}
                                    onChange={(event) => setProjectTeamSettings((current) => ({ ...(current ?? resolvedProjectTeamSettings), provider_config_id: event.target.value }))}
                                >
                                    <MenuItem value="">Project default</MenuItem>
                                    {providerOptions.map((provider) => (
                                        <MenuItem key={provider.id} value={provider.id}>{provider.name} · {provider.default_model}</MenuItem>
                                    ))}
                                </TextField>
                                <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                                    <TextField
                                        label="Model override"
                                        value={resolvedProjectTeamSettings.model_name}
                                        onChange={(event) => setProjectTeamSettings((current) => ({ ...(current ?? resolvedProjectTeamSettings), model_name: event.target.value }))}
                                        fullWidth
                                    />
                                    <TextField
                                        label="Fallback model"
                                        value={resolvedProjectTeamSettings.fallback_model}
                                        onChange={(event) => setProjectTeamSettings((current) => ({ ...(current ?? resolvedProjectTeamSettings), fallback_model: event.target.value }))}
                                        fullWidth
                                    />
                                </Stack>
                                <Divider />
                                <Typography variant="subtitle2">Worker routing</Typography>
                                <Typography variant="body2" color="text.secondary">
                                    Auto-assignment uses required_tools coverage, queue depth, task due_date when routing_mode is SLA-aware, and provider health when a health check has marked a provider unhealthy.
                                    User-pinned workers (task or project execution) still win over auto-selection.
                                </Typography>
                                <TextField
                                    select
                                    label="Routing mode"
                                    value={resolvedProjectTeamSettings.routing_mode}
                                    onChange={(event) => setProjectTeamSettings((current) => ({ ...(current ?? resolvedProjectTeamSettings), routing_mode: event.target.value }))}
                                    helperText="sla_priority weights queue depth more as due_date approaches."
                                >
                                    <MenuItem value="balanced">Balanced (default)</MenuItem>
                                    <MenuItem value="sla_priority">SLA / due-date priority</MenuItem>
                                    <MenuItem value="throughput">Throughput (lighter queue weight)</MenuItem>
                                </TextField>
                                <TextField
                                    select
                                    label="Sibling load balance"
                                    value={resolvedProjectTeamSettings.sibling_load_balance}
                                    onChange={(event) => setProjectTeamSettings((current) => ({ ...(current ?? resolvedProjectTeamSettings), sibling_load_balance: event.target.value }))}
                                    helperText="Among tied workers under the same manager, round_robin spreads work deterministically per task."
                                >
                                    <MenuItem value="queue_depth">Queue depth first</MenuItem>
                                    <MenuItem value="round_robin">Round robin among siblings</MenuItem>
                                </TextField>
                                <Stack direction="row" alignItems="center" spacing={1}>
                                    <Switch
                                        checked={resolvedProjectTeamSettings.skip_unhealthy_worker_providers}
                                        onChange={(_, checked) => setProjectTeamSettings((current) => ({
                                            ...(current ?? resolvedProjectTeamSettings),
                                            skip_unhealthy_worker_providers: checked,
                                        }))}
                                    />
                                    <Typography variant="body2">Deprioritize workers whose provider failed the last health check</Typography>
                                </Stack>
                                <Divider />
                                <Typography variant="subtitle2">Task SLA (deadline scan)</Typography>
                                <Typography variant="body2" color="text.secondary">
                                    Background job flags tasks approaching deadline and opens approvals when past due (plus grace hours). Uses each task due_date and/or response SLA hours from task creation.
                                </Typography>
                                <Stack direction="row" alignItems="center" spacing={1}>
                                    <Switch
                                        checked={resolvedProjectTeamSettings.sla_enabled}
                                        onChange={(_, checked) => setProjectTeamSettings((current) => ({
                                            ...(current ?? resolvedProjectTeamSettings),
                                            sla_enabled: checked,
                                        }))}
                                    />
                                    <Typography variant="body2">Enable SLA deadline scan</Typography>
                                </Stack>
                                <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                                    <TextField
                                        label="Warn within (hours before due)"
                                        value={resolvedProjectTeamSettings.sla_warn_hours}
                                        onChange={(event) => setProjectTeamSettings((current) => ({
                                            ...(current ?? resolvedProjectTeamSettings),
                                            sla_warn_hours: event.target.value,
                                        }))}
                                        fullWidth
                                    />
                                    <TextField
                                        label="Escalate after due (hours)"
                                        value={resolvedProjectTeamSettings.sla_escalate_after_due_hours}
                                        onChange={(event) => setProjectTeamSettings((current) => ({
                                            ...(current ?? resolvedProjectTeamSettings),
                                            sla_escalate_after_due_hours: event.target.value,
                                        }))}
                                        helperText="0 = escalate as soon as the effective deadline passes."
                                        fullWidth
                                    />
                                </Stack>
                                <Divider />
                                <Typography variant="subtitle2">Escalation rules</Typography>
                                <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                                    <TextField
                                        label="Stuck for minutes"
                                        value={resolvedProjectTeamSettings.stuck_for_minutes}
                                        onChange={(event) => setProjectTeamSettings((current) => ({ ...(current ?? resolvedProjectTeamSettings), stuck_for_minutes: event.target.value }))}
                                        fullWidth
                                    />
                                    <TextField
                                        label="Cost exceeds USD"
                                        value={resolvedProjectTeamSettings.cost_exceeds_usd}
                                        onChange={(event) => setProjectTeamSettings((current) => ({ ...(current ?? resolvedProjectTeamSettings), cost_exceeds_usd: event.target.value }))}
                                        fullWidth
                                    />
                                    <TextField
                                        label="No consensus after rounds"
                                        value={resolvedProjectTeamSettings.no_consensus_after_rounds}
                                        onChange={(event) => setProjectTeamSettings((current) => ({ ...(current ?? resolvedProjectTeamSettings), no_consensus_after_rounds: event.target.value }))}
                                        fullWidth
                                    />
                                </Stack>
                                <Button variant="contained" onClick={saveProjectExecutionSettings} disabled={saveProjectSettingsMutation.isPending}>
                                    Save execution settings
                                </Button>
                            </Stack>
                        </SectionCard>

                        {/* ── Gate config ── */}
                        <SectionCard
                            title="Approval gates"
                            description="Choose which agent actions pause for human review. Autonomous mode bypasses all gates."
                        >
                            <Stack spacing={2}>
                                <TextField
                                    select
                                    label="Autonomy level"
                                    value={gateConfig?.autonomy_level ?? "assisted"}
                                    onChange={(e) => updateGateConfigMutation.mutate({ autonomy_level: e.target.value })}
                                    disabled={updateGateConfigMutation.isPending}
                                    helperText={
                                        gateConfig?.autonomy_level === "autonomous"
                                            ? "All gates are short-circuited — the agent acts without human approval."
                                            : "Agent actions in the list below will pause for your review."
                                    }
                                >
                                    <MenuItem value="assisted">Assisted — all gates active</MenuItem>
                                    <MenuItem value="semi_autonomous">Semi-autonomous — critical gates only</MenuItem>
                                    <MenuItem value="supervised">Supervised — everything gated</MenuItem>
                                    <MenuItem value="autonomous">Autonomous — no gates</MenuItem>
                                </TextField>
                                {gateConfig?.autonomy_level !== "autonomous" && (
                                    <>
                                        <Typography variant="subtitle2" color="text.secondary">
                                            Gated actions
                                        </Typography>
                                        {([
                                            { key: "post_to_github", label: "Post to GitHub", description: "Post comments or results to a GitHub issue" },
                                            { key: "open_pr", label: "Open pull request", description: "Create a PR from generated code" },
                                            { key: "mark_complete", label: "Mark complete", description: "Transition a task to completed status" },
                                            { key: "write_memory", label: "Write to memory", description: "Persist information to project memory" },
                                            { key: "use_expensive_model", label: "Use expensive model", description: "Switch to a higher-cost model mid-run" },
                                            { key: "run_tool", label: "Run external tool", description: "Execute code or call an external tool" },
                                        ] as const).map(({ key, label, description }) => {
                                            const isGated = gateConfig?.approval_gates.includes(key) ?? true;
                                            return (
                                                <Paper key={key} sx={{ p: 1.5, borderRadius: 2, border: 1, borderColor: "divider" }}>
                                                    <FormControlLabel
                                                        sx={{ m: 0, width: "100%", justifyContent: "space-between" }}
                                                        labelPlacement="start"
                                                        control={
                                                            <Switch
                                                                checked={isGated}
                                                                disabled={updateGateConfigMutation.isPending}
                                                                onChange={(e) => {
                                                                    const current = gateConfig?.approval_gates ?? [];
                                                                    const next = e.target.checked
                                                                        ? [...current, key]
                                                                        : current.filter((g) => g !== key);
                                                                    updateGateConfigMutation.mutate({ approval_gates: next });
                                                                }}
                                                                size="small"
                                                            />
                                                        }
                                                        label={
                                                            <Box>
                                                                <Typography variant="subtitle2">{label}</Typography>
                                                                <Typography variant="caption" color="text.secondary">{description}</Typography>
                                                            </Box>
                                                        }
                                                    />
                                                </Paper>
                                            );
                                        })}
                                    </>
                                )}
                            </Stack>
                        </SectionCard>
                    </Stack>
                </Box>
            )}

            {/* ── Brainstorms ── */}
            {tab === "brainstorms" && (
                <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", xl: "340px minmax(0, 1fr)" } }}>
                    <SectionCard title="Start brainstorm" description="Pick participants and queue a structured multi-agent discussion.">
                        <Stack spacing={2}>
                            <TextField label="Topic" value={brainstormTopic} onChange={(e) => setBrainstormTopic(e.target.value)} />
                            <TextField label="Participant agent IDs" helperText="Comma-separated" value={brainstormParticipants} onChange={(e) => setBrainstormParticipants(e.target.value)} multiline minRows={3} />
                            <Button
                                variant="contained"
                                onClick={() =>
                                    brainstormMutation.mutate({
                                        project_id: projectId,
                                        topic: brainstormTopic,
                                        participant_agent_ids: brainstormParticipants.split(",").map((item) => item.trim()).filter(Boolean),
                                    })
                                }
                            >
                                Launch brainstorm
                            </Button>
                        </Stack>
                    </SectionCard>
                    <SectionCard title="Brainstorms" description="Structured multi-agent discussions and their recommendations.">
                        <Stack spacing={1.5}>
                            {brainstorms.map((brainstorm) => (
                                <Paper key={brainstorm.id} sx={{ p: 2, borderRadius: 4 }}>
                                    <Typography variant="subtitle2">{brainstorm.topic}</Typography>
                                    <Typography variant="body2" color="text.secondary">{brainstorm.summary || brainstorm.final_recommendation || "Run pending or no summary yet."}</Typography>
                                    <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 1 }}>
                                        <Typography variant="caption" color="text.secondary">
                                            {humanizeKey(brainstorm.status)} • {formatDateTime(brainstorm.updated_at)}
                                        </Typography>
                                        <Button size="small" variant="text" onClick={() => navigate(`/brainstorms/${brainstorm.id}`)}>
                                            Open room
                                        </Button>
                                        {brainstorm.final_recommendation && (
                                            <Button
                                                size="small" variant="text"
                                                onClick={() => decisionMutation.mutate({
                                                    title: brainstorm.topic,
                                                    decision: brainstorm.final_recommendation!,
                                                    rationale: brainstorm.summary || "",
                                                    author_label: "Brainstorm",
                                                    brainstorm_id: brainstorm.id,
                                                })}
                                            >
                                                Promote to decision
                                            </Button>
                                        )}
                                    </Stack>
                                </Paper>
                            ))}
                        </Stack>
                    </SectionCard>
                </Box>
            )}

            {/* ── Decisions ── */}
            {tab === "decisions" && (
                <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", xl: "380px minmax(0, 1fr)" } }}>
                    <SectionCard title="Record decision" description="Architectural decisions, policy choices, and key agreements.">
                        <Stack spacing={2}>
                            <TextField label="Title" value={decisionForm.title} onChange={(e) => setDecisionForm((f) => ({ ...f, title: e.target.value }))} />
                            <TextField label="Decision" multiline minRows={3} value={decisionForm.decision} onChange={(e) => setDecisionForm((f) => ({ ...f, decision: e.target.value }))} />
                            <TextField label="Rationale" multiline minRows={2} value={decisionForm.rationale} onChange={(e) => setDecisionForm((f) => ({ ...f, rationale: e.target.value }))} />
                            <TextField label="Author" value={decisionForm.author_label} onChange={(e) => setDecisionForm((f) => ({ ...f, author_label: e.target.value }))} />
                            <Button
                                variant="contained"
                                disabled={!decisionForm.title.trim() || !decisionForm.decision.trim()}
                                onClick={() => decisionMutation.mutate({ ...decisionForm })}
                            >
                                Record
                            </Button>
                        </Stack>
                    </SectionCard>
                    <SectionCard title="Decision log" description="Architectural decision records (ADRs) for this project.">
                        {decisions.length === 0 ? (
                            <Typography color="text.secondary">No decisions recorded yet.</Typography>
                        ) : (
                            <Stack spacing={1.5}>
                                {decisions.map((d) => (
                                    <Paper key={d.id} sx={{ p: 2, borderRadius: 4 }}>
                                        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap sx={{ mb: 0.5 }}>
                                            <Typography variant="subtitle2">{d.title}</Typography>
                                            {d.author_label && <Chip label={d.author_label} size="small" variant="outlined" />}
                                            {d.brainstorm_id && <Chip label="from brainstorm" size="small" color="secondary" variant="outlined" />}
                                        </Stack>
                                        <Typography variant="body2">{d.decision}</Typography>
                                        {d.rationale && <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>{d.rationale}</Typography>}
                                        <Typography variant="caption" color="text.secondary">{formatDateTime(d.created_at)}</Typography>
                                    </Paper>
                                ))}
                            </Stack>
                        )}
                    </SectionCard>
                </Box>
            )}

            {/* ── GitHub ── */}
            {tab === "github" && (
                <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", xl: "1fr 1fr" } }}>
                    <SectionCard
                        title="GitHub integration"
                        description="Branch naming for auto-PRs, optional progress comments, and PR-review triggered review runs."
                    >
                        <Stack spacing={2}>
                            <TextField
                                label="Branch name template"
                                size="small"
                                fullWidth
                                value={githubForm.branch_prefix}
                                onChange={(e) => setGithubForm((f) => ({ ...f, branch_prefix: e.target.value }))}
                                helperText="Placeholders: {task_id}, {slug} (from task title). Used when generating PR branches."
                            />
                            <FormControlLabel
                                control={(
                                    <Switch
                                        checked={githubForm.auto_post_progress}
                                        onChange={(_, checked) => setGithubForm((f) => ({ ...f, auto_post_progress: checked }))}
                                    />
                                )}
                                label="Post agent progress notes to GitHub (when enabled server-side)"
                            />
                            <FormControlLabel
                                control={(
                                    <Switch
                                        checked={githubForm.auto_review_on_pr_review}
                                        onChange={(_, checked) => setGithubForm((f) => ({ ...f, auto_review_on_pr_review: checked }))}
                                    />
                                )}
                                label="Queue a Troop review run when a GitHub PR review is submitted"
                            />
                            <Button variant="contained" onClick={saveGithubIntegration} disabled={saveProjectSettingsMutation.isPending}>
                                Save GitHub settings
                            </Button>
                        </Stack>
                    </SectionCard>
                    <SectionCard
                        title="Sandbox & secret scoping (beta)"
                        description="Document operational intent for HITL. Enforcement still follows agent permissions, tool allowlists, and provider configuration."
                    >
                        <Stack spacing={2}>
                            <TextField
                                select
                                label="Secret scope posture"
                                size="small"
                                value={hitlForm.secret_scope}
                                onChange={(e) => setHitlForm((f) => ({ ...f, secret_scope: e.target.value }))}
                                fullWidth
                            >
                                <MenuItem value="project_default">Project default (env + provider keys)</MenuItem>
                                <MenuItem value="repo_scoped">Prefer repository-scoped tokens when available</MenuItem>
                                <MenuItem value="agent_scoped">Prefer per-agent secret slots (manual rotation)</MenuItem>
                            </TextField>
                            <TextField
                                label="Sandbox / runner notes"
                                size="small"
                                multiline
                                minRows={2}
                                fullWidth
                                value={hitlForm.sandbox_note}
                                onChange={(e) => setHitlForm((f) => ({ ...f, sandbox_note: e.target.value }))}
                                placeholder="e.g. Dedicated worker queue, CPU seconds cap, egress deny list…"
                            />
                            <Button variant="outlined" onClick={saveHitlSettings} disabled={saveProjectSettingsMutation.isPending}>
                                Save HITL notes
                            </Button>
                        </Stack>
                    </SectionCard>
                    <SectionCard title="Imported issues" description="Internal tasks linked to external GitHub work.">
                        <Stack spacing={1.5}>
                            {issueLinks.map((item) => (
                                <Paper key={item.id} sx={{ p: 2, borderRadius: 4 }}>
                                    <Typography variant="subtitle2">#{item.issue_number} {item.title}</Typography>
                                    <Typography variant="caption" color="text.secondary">{item.state} • {item.sync_status}</Typography>
                                </Paper>
                            ))}
                        </Stack>
                    </SectionCard>
                    <SectionCard title="Sync events" description="Import, comment posting, and other GitHub integration activity.">
                        <Stack spacing={1.5}>
                            {syncEvents.map((event) => (
                                <Box key={event.id}>
                                    <Typography variant="body2">{event.action} • {event.status}</Typography>
                                    <Typography variant="caption" color="text.secondary">{event.detail || "No details"} • {formatDateTime(event.created_at)}</Typography>
                                </Box>
                            ))}
                        </Stack>
                    </SectionCard>
                </Box>
            )}

            {/* ── Knowledge base ── */}
            {tab === "knowledge" && (
                <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", xl: "minmax(0, 1fr) 400px" }, alignItems: "start" }}>
                    <Stack spacing={2}>
                        <SectionCard title="Documents" description="Upload markdown or text; ingestion chunks the source for retrieval-augmented prompts.">
                            <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ mb: 2 }} alignItems={{ sm: "center" }}>
                                <TextField
                                    label="TTL days"
                                    value={documentTtlDays}
                                    onChange={(event) => setDocumentTtlDays(event.target.value)}
                                    sx={{ width: { xs: "100%", sm: 140 } }}
                                />
                                <Button variant="contained" component="label" startIcon={<UploadIcon />}>
                                    Upload document
                                    <input
                                        hidden
                                        type="file"
                                        accept=".md,.txt,.json,.yml,.yaml,.toml"
                                        onChange={(event) => {
                                            const file = event.target.files?.[0];
                                            if (file) uploadDocumentMutation.mutate(file);
                                            event.currentTarget.value = "";
                                        }}
                                    />
                                </Button>
                            </Stack>
                            {docs.length === 0 ? (
                                <Typography variant="body2" color="text.secondary">No documents yet. Upload a file to seed the knowledge base.</Typography>
                            ) : (
                                <Stack spacing={1.5}>
                                    {docs.map((doc) => (
                                        <Paper key={doc.id} sx={{ p: 2, borderRadius: 4 }}>
                                            <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={1}>
                                                <Box flex={1}>
                                                    <Typography variant="subtitle2">{doc.filename}</Typography>
                                                    <Typography variant="body2" color="text.secondary">{doc.summary_text || `${doc.source_text.slice(0, 200)}…`}</Typography>
                                                </Box>
                                                <Stack direction="row" spacing={0.5} alignItems="center">
                                                    <IconButton
                                                        size="small"
                                                        aria-label="Toggle chunk preview"
                                                        onClick={() => setExpandedDocumentId((current) => (current === doc.id ? null : doc.id))}
                                                    >
                                                        {expandedDocumentId === doc.id ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                                                    </IconButton>
                                                    <Button size="small" color="error" onClick={() => deleteDocumentMutation.mutate(doc.id)}>
                                                        Remove
                                                    </Button>
                                                </Stack>
                                            </Stack>
                                            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mt: 1 }}>
                                                <Chip size="small" variant="outlined" label={`${doc.chunk_count} chunks`} />
                                                <Chip size="small" variant="outlined" label={`${(doc.size_bytes / 1024).toFixed(1)} KB`} />
                                                <Chip size="small" variant="outlined" label={`TTL ${doc.ttl_days ?? "none"}`} />
                                                <Chip size="small" variant="outlined" label={doc.ingestion_status} />
                                            </Stack>
                                            <Collapse in={expandedDocumentId === doc.id}>
                                                <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1.5 }}>
                                                    Source preview (chunking splits this text for embedding)
                                                </Typography>
                                                <Paper
                                                    variant="outlined"
                                                    sx={{
                                                        mt: 1,
                                                        p: 1.5,
                                                        maxHeight: 320,
                                                        overflow: "auto",
                                                        borderRadius: 2,
                                                        fontFamily: "IBM Plex Mono, monospace",
                                                        fontSize: "0.75rem",
                                                        whiteSpace: "pre-wrap",
                                                    }}
                                                >
                                                    {doc.source_text}
                                                </Paper>
                                            </Collapse>
                                        </Paper>
                                    ))}
                                </Stack>
                            )}
                        </SectionCard>
                    </Stack>
                    <SectionCard title="Semantic search" description="Query indexed chunks (minimum three characters).">
                        <TextField
                            label="Search knowledge"
                            value={knowledgeQuery}
                            onChange={(event) => setKnowledgeQuery(event.target.value)}
                            helperText="Matches ranked by relevance; each row is a chunk used during agent runs."
                            fullWidth
                        />
                        {knowledgeQuery.trim().length >= 3 && (
                            <Paper sx={{ p: 2, borderRadius: 4, mt: 2 }}>
                                <Typography variant="subtitle2">Results</Typography>
                                <Stack spacing={1.25} sx={{ mt: 1.25 }}>
                                    {knowledgeResults.length > 0 ? knowledgeResults.map((match) => (
                                        <Box key={match.chunk_id}>
                                            <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                                                <Typography variant="body2">{match.filename}</Typography>
                                                <Chip size="small" label={`chunk #${match.chunk_index}`} variant="outlined" />
                                                <Chip size="small" label={`score ${match.score.toFixed(3)}`} variant="outlined" />
                                            </Stack>
                                            <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: "pre-wrap", display: "block", mt: 0.75 }}>
                                                {match.content}
                                            </Typography>
                                        </Box>
                                    )) : (
                                        <Typography variant="body2" color="text.secondary">No relevant chunks found.</Typography>
                                    )}
                                </Stack>
                            </Paper>
                        )}
                    </SectionCard>
                </Box>
            )}

            {/* ── Activity ── */}
            {tab === "activity" && (
                <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", xl: "1fr 1fr" } }}>
                    <SectionCard title="Run activity" description="Recent execution attempts and their outcomes.">
                        <Stack spacing={1.5}>
                            {runs.map((run) => (
                                <Paper key={run.id} sx={{ p: 2, borderRadius: 4 }}>
                                    <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
                                        <Box>
                                            <Typography variant="subtitle2">{humanizeKey(run.run_mode)} • {humanizeKey(run.status)}</Typography>
                                            <Typography variant="caption" color="text.secondary">
                                                {formatDateTime(run.created_at)} • {run.token_total} tokens
                                            </Typography>
                                        </Box>
                                        <Button size="small" variant="text" onClick={() => navigate(`/runs/${run.id}`)}>Inspect</Button>
                                    </Stack>
                                </Paper>
                            ))}
                        </Stack>
                    </SectionCard>
                    <SectionCard title="Agent memory" description="Scoped notes agents may write between runs, plus approval gates for long-term memory.">
                        <Stack spacing={1.5}>
                            {memoryEntries.map((entry) => (
                                <Paper key={entry.id} sx={{ p: 2, borderRadius: 4 }}>
                                    <Stack direction={{ xs: "column", md: "row" }} justifyContent="space-between" spacing={1.5}>
                                        <Box>
                                            <Typography variant="body2">{entry.key}</Typography>
                                            <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: "pre-wrap" }}>
                                                {entry.value_text}
                                            </Typography>
                                        </Box>
                                        <Button size="small" color="error" onClick={() => deleteMemoryMutation.mutate(entry.id)}>
                                            Remove
                                        </Button>
                                    </Stack>
                                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mt: 1 }}>
                                        <Chip size="small" variant="outlined" label={entry.scope} />
                                        <Chip size="small" variant="outlined" label={entry.status} />
                                        <Chip size="small" variant="outlined" label={entry.expires_at ? `Expires ${formatDateTime(entry.expires_at)}` : "No expiry"} />
                                    </Stack>
                                </Paper>
                            ))}
                            {pendingMemoryApprovals.length > 0 && (
                                <>
                                    <Divider />
                                    <Typography variant="subtitle2">Pending long-term memory writes</Typography>
                                    {pendingMemoryApprovals.map((approval) => (
                                        <Paper key={approval.id} sx={{ p: 2, borderRadius: 4 }}>
                                            <Typography variant="body2">{String(approval.payload.key ?? "memory write")}</Typography>
                                            <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: "pre-wrap" }}>
                                                {String(approval.payload.value_text ?? "")}
                                            </Typography>
                                            <Stack direction="row" spacing={1} sx={{ mt: 1.25 }}>
                                                <Button size="small" variant="contained" onClick={() => memoryApprovalMutation.mutate({ approvalId: approval.id, status: "approved" })}>
                                                    Approve
                                                </Button>
                                                <Button size="small" variant="outlined" color="error" onClick={() => memoryApprovalMutation.mutate({ approvalId: approval.id, status: "rejected" })}>
                                                    Reject
                                                </Button>
                                            </Stack>
                                        </Paper>
                                    ))}
                                </>
                            )}
                        </Stack>
                    </SectionCard>
                </Box>
            )}

            <Drawer
                anchor="right"
                open={Boolean(dagDrawerTaskId)}
                onClose={() => setDagDrawerTaskId(null)}
                PaperProps={{ sx: { width: { xs: "100%", sm: 420 }, p: 2.5, boxSizing: "border-box" } }}
            >
                {dagTask && (
                    <Stack spacing={2}>
                        <Typography variant="overline" color="text.secondary">Task</Typography>
                        <Typography variant="h6" sx={{ fontWeight: 700 }}>{dagTask.title}</Typography>
                        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                            <Chip label={humanizeKey(dagTask.status)} size="small" />
                            <Chip label={dagTask.priority} size="small" variant="outlined" />
                        </Stack>
                        {dagTask.description ? (
                            <Typography variant="body2" color="text.secondary" sx={{ whiteSpace: "pre-wrap" }}>
                                {dagTask.description}
                            </Typography>
                        ) : null}
                        <Stack spacing={1}>
                            <Button variant="outlined" onClick={() => { setTab("board"); setDagDrawerTaskId(null); }}>
                                Open board tab
                            </Button>
                            {dagTaskLatestRun ? (
                                <Button variant="outlined" onClick={() => navigate(`/runs/${dagTaskLatestRun.id}`)}>
                                    Open latest run
                                </Button>
                            ) : null}
                            <Button
                                variant="contained"
                                disabled={runMutation.isPending}
                                onClick={() => {
                                    setSelectedTaskId(dagTask.id);
                                    runMutation.mutate({
                                        taskId: dagTask.id,
                                        runMode: taskRunModes[dagTask.id] ?? "single_agent",
                                        createPr: taskPrModes[dagTask.id] ?? false,
                                    });
                                    setDagDrawerTaskId(null);
                                }}
                            >
                                Run this task
                            </Button>
                            {dagTaskSubtasks.length >= 2 ? (
                                <Button
                                    variant="outlined"
                                    disabled={mergeResolutionMutation.isPending}
                                    onClick={() => {
                                        const done = dagTaskSubtasks.filter((s) => s.status === "completed" || s.status === "approved");
                                        if (done.length < 2) {
                                            showToast({ message: "Need at least two completed subtasks to merge.", severity: "warning" });
                                            return;
                                        }
                                        mergeResolutionMutation.mutate(dagTask.id);
                                        setDagDrawerTaskId(null);
                                    }}
                                >
                                    Merge completed subtasks (resolution run)
                                </Button>
                            ) : null}
                            {dagTask.metadata?.latest_reopen ? (
                                <Alert severity="warning">
                                    Latest rework checklist recorded. Re-run after addressing reviewer items.
                                </Alert>
                            ) : null}
                        </Stack>
                    </Stack>
                )}
            </Drawer>

            {/* ── Acceptance Dialog ── */}
            {acceptanceTaskId && (
                <AcceptanceDialog
                    projectId={projectId}
                    taskId={acceptanceTaskId}
                    taskTitle={tasks.find((t) => t.id === acceptanceTaskId)?.title ?? ""}
                    onClose={() => setAcceptanceTaskId(null)}
                />
            )}
        </PageShell>
    );
}
