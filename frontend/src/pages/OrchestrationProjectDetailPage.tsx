import { useMemo, useRef, useState } from "react";
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
    getProjectRepositoryIndexStatus,
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
    listProjectMemoryIngestJobs,
    listProjectRepositories,
    listSemanticMemory,
    listProjectMilestones,
    getProjectMemorySettings,
    patchProjectMemorySettings,
    listProviders,
    listRuns,
    searchProjectKnowledge,
    listSubtasks,
    listTaskArtifacts,
    startBrainstorm,
    startTaskRun,
    updateOrchestrationTask,
    updateOrchestrationProject,
    updateAgent,
    updateProjectAgent,
    updateProjectMilestone,
    uploadProjectDocument,
    getGateConfig,
    getTaskExecutionState,
    getTaskTimeline,
    listDagReadyTasks,
    listWorkflowTemplates,
    startDagParallelReady,
    startMergeResolutionRun,
    getMergeResolutionPreview,
    queueProjectRepositoryIndex,
    updateGateConfig,
    updateProjectRepository,
} from "../api/orchestration";
import type { GateConfig, OrchestrationTask, ProviderConfig, TaskRun } from "../api/orchestration";
import { readOrchestrationSelectionMeta } from "../utils/orchestrationSelection";
import { useSnackbar } from "../app/snackbarContext";
import { EmptyState } from "../components/ui/EmptyState";
import { PageHeader } from "../components/ui/PageHeader";
import { PageShell } from "../components/ui/PageShell";
import { SectionCard } from "../components/ui/SectionCard";
import { useLiveSnapshotStream } from "../hooks/useLiveSnapshotStream";
import { formatDateTime, humanizeKey } from "../utils/formatters";

type DetailTab = "overview" | "board" | "dag" | "agents" | "brainstorms" | "decisions" | "github" | "knowledge" | "activity";
type ExecutionMode = "single_agent" | "manager_worker" | "debate";

const BRAINSTORM_MODE_OPTIONS = [
    { value: "exploration", label: "Exploration" },
    { value: "solution_design", label: "Solution design" },
    { value: "code_review", label: "Code review debate" },
    { value: "incident_triage", label: "Incident triage" },
    { value: "root_cause", label: "Root-cause analysis" },
    { value: "architecture_proposal", label: "Architecture proposal" },
] as const;

const BRAINSTORM_OUTPUT_OPTIONS = [
    { value: "implementation_plan", label: "Implementation plan" },
    { value: "adr", label: "ADR" },
    { value: "test_plan", label: "Test plan" },
    { value: "risk_register", label: "Risk register" },
] as const;

const KANBAN_COLUMNS: { status: string; label: string; color: "default" | "warning" | "info" | "success" | "error" }[] = [
    { status: "backlog", label: "Backlog", color: "default" },
    { status: "queued", label: "Queued", color: "warning" },
    { status: "in_progress", label: "In Progress", color: "info" },
    { status: "needs_review", label: "Review", color: "warning" },
    { status: "completed", label: "Done", color: "success" },
    { status: "failed", label: "Failed", color: "error" },
];

function extractApiErrorMessage(error: unknown, fallback: string): string {
    if (typeof error === "object" && error && "detail" in error) {
        const detail = (error as { detail?: unknown }).detail;
        if (typeof detail === "string" && detail.trim()) return detail;
        if (typeof detail === "object" && detail && "message" in detail) {
            const message = (detail as { message?: unknown }).message;
            if (typeof message === "string" && message.trim()) return message;
        }
    }
    return fallback;
}

type PolicyRoutingRule = {
    field?: string;
    operator?: string;
    value?: unknown;
    route_to?: "cheap_model_slug" | "strong_model_slug" | "local_model_slug" | string;
};

function policyFieldValue(
    field: string,
    sample: { priority: string; taskType: string; labels: string[]; projectSensitive: boolean }
): unknown {
    if (field === "task.priority") return sample.priority;
    if (field === "task.task_type") return sample.taskType;
    if (field === "task.labels") return sample.labels;
    if (field === "project.is_sensitive") return sample.projectSensitive;
    return null;
}

function policyRuleMatches(actual: unknown, operator: string, expected: unknown): boolean {
    if (operator === "equals") return actual === expected;
    if (operator === "contains") {
        if (Array.isArray(actual)) return actual.includes(expected);
        if (typeof actual === "string") return String(actual).includes(String(expected ?? ""));
    }
    return false;
}

function milestoneStatusColor(status: string): "success" | "warning" | "default" {
    if (status === "completed") return "success";
    if (status === "in_progress" || status === "active") return "warning";
    return "default";
}

function dueDateToTime(value: string | null) {
    return value ? new Date(value).getTime() : null;
}

type AcceptanceCriterionItem = {
    item: string;
    passed: boolean;
    evidence_excerpt?: string;
};

type AcceptanceCheckerConfig = {
    required_artifact_kinds: string[];
    require_github_comment: boolean;
    require_github_pr: boolean;
    require_reviewer_approval: boolean;
};

function getAcceptanceItems(check: { name: string } & Record<string, unknown>): AcceptanceCriterionItem[] {
    if (check.name !== "acceptance_criteria" || !Array.isArray(check.items)) {
        return [];
    }
    return check.items.filter((item): item is AcceptanceCriterionItem => {
        if (typeof item !== "object" || item === null) {
            return false;
        }
        const candidate = item as Partial<AcceptanceCriterionItem>;
        return typeof candidate.item === "string" && typeof candidate.passed === "boolean";
    });
}

function readAcceptanceCheckerConfig(task: OrchestrationTask): AcceptanceCheckerConfig {
    const raw = task.metadata?.acceptance_checker;
    const config = typeof raw === "object" && raw !== null ? raw as Record<string, unknown> : {};
    return {
        required_artifact_kinds: Array.isArray(config.required_artifact_kinds)
            ? config.required_artifact_kinds.map((item) => String(item).trim()).filter(Boolean)
            : [],
        require_github_comment: Boolean(config.require_github_comment),
        require_github_pr: Boolean(config.require_github_pr),
        require_reviewer_approval: Boolean(config.require_reviewer_approval),
    };
}

function MilestoneTimeline({ milestones }: { milestones: Array<{ id: string; title: string; due_date: string | null; status: string }> }) {
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

function SubtaskPanel({ projectId, taskId, taskTitle }: { projectId: string; taskId: string; taskTitle: string }) {
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
    const { showToast } = useSnackbar();
    const [dragging, setDragging] = useState<string | null>(null);
    const [expandedTask, setExpandedTask] = useState<string | null>(null);

    const moveMutation = useMutation({
        mutationFn: ({ taskId, status }: { taskId: string; status: string }) =>
            updateOrchestrationTask(projectId, taskId, { status }),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "tasks"] });
        },
        onError: (error) => {
            showToast({ message: extractApiErrorMessage(error, "Task status update failed."), severity: "error" });
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
                            const acceptanceConfig = readAcceptanceCheckerConfig(task);
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
    const [brainstormForm, setBrainstormForm] = useState({
        topic: "",
        task_id: "",
        moderator_agent_id: "",
        participant_agent_ids: [] as string[],
        mode: "exploration",
        output_type: "implementation_plan",
        max_rounds: "3",
        max_cost_usd: "10",
        max_repetition_score: "0.92",
        soft_consensus_min_similarity: "0.72",
        conflict_pairwise_max_similarity: "0.38",
        stop_on_consensus: true,
        accept_soft_consensus: true,
        escalate_on_no_consensus: true,
    });
    const [milestoneForm, setMilestoneForm] = useState({ title: "", description: "", due_date: "" });
    const [decisionForm, setDecisionForm] = useState({ title: "", decision: "", rationale: "", author_label: "" });
    const [knowledgeQuery, setKnowledgeQuery] = useState("");
    const [includeDecisionRecall, setIncludeDecisionRecall] = useState(true);
    const [documentTtlDays, setDocumentTtlDays] = useState("30");
    const [expandedDocumentId, setExpandedDocumentId] = useState<string | null>(null);
    const [githubForm, setGithubForm] = useState<Partial<{
        branch_prefix: string;
        enforce_branch_naming: boolean;
        auto_post_progress: boolean;
        auto_activate_review_on_pr_open: boolean;
        auto_review_on_pr_review: boolean;
        close_issue_with_manager_summary: boolean;
        sync_labels_to_github: boolean;
        sync_assignees_to_github: boolean;
        sync_state_to_github: boolean;
        sync_milestone_to_github: boolean;
        repo_agent_pools_json: string;
    }>>({});
    const [hitlForm, setHitlForm] = useState<Partial<{
        sandbox_note: string;
        secret_scope: string;
        sandbox_mode: string;
    }>>({});
    const [approvalReasonById, setApprovalReasonById] = useState<Record<string, string>>({});
    const [acceptanceTaskId, setAcceptanceTaskId] = useState<string | null>(null);
    const [taskRunModes, setTaskRunModes] = useState<Record<string, ExecutionMode>>({});
    const [taskPrModes, setTaskPrModes] = useState<Record<string, boolean>>({});
    const [dagDrawerTaskId, setDagDrawerTaskId] = useState<string | null>(null);
    const [dagDependencyDrafts, setDagDependencyDrafts] = useState<Record<string, string[]>>({});
    const [projectTeamSettings, setProjectTeamSettings] = useState<null | {
        manager_agent_id: string;
        reviewer_agent_ids: string[];
        reviewer_chain_mode: string;
        autonomy_level: string;
        provider_config_id: string;
        model_name: string;
        fallback_model: string;
        escalation_target_agent_id: string;
        stuck_for_minutes: string;
        cost_exceeds_usd: string;
        no_consensus_after_rounds: string;
        routing_mode: string;
        sibling_load_balance: string;
        skip_unhealthy_worker_providers: boolean;
        offline_local_only_mode: boolean;
        enforce_project_model_policy: boolean;
        allowed_provider_types_csv: string;
        allowed_model_slugs_csv: string;
        blocked_handoff_mode: string;
        blocked_handoff_target_agent_id: string;
        blocked_handoff_fallback_to_manager: boolean;
        sla_enabled: boolean;
        sla_warn_hours: string;
        sla_escalate_after_due_hours: string;
    }>(null);
    const [policyPreviewForm, setPolicyPreviewForm] = useState({
        priority: "normal",
        taskType: "general",
        labelsCsv: "",
        projectSensitive: false,
    });
    const [memorySettingsDraft, setMemorySettingsDraft] = useState<null | {
        semantic_write_requires_approval: boolean;
        episodic_retention_days: string;
        deep_recall_mode: boolean;
    }>(null);
    const [mergeTaskId, setMergeTaskId] = useState<string | null>(null);
    const [mergeNotes, setMergeNotes] = useState("");
    const [repoIndexDrafts, setRepoIndexDrafts] = useState<Record<string, { scheduleLabel: string; pathPrefixes: string; autoEnabled: boolean }>>({});

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
    const { data: projectRepositories = [] } = useQuery({
        queryKey: ["orchestration", "project", projectId, "repositories"],
        queryFn: () => listProjectRepositories(projectId),
        enabled: Boolean(projectId),
    });
    const { data: repositoryIndexStatus = [] } = useQuery({
        queryKey: ["orchestration", "project", projectId, "repository-index-status"],
        queryFn: () => getProjectRepositoryIndexStatus(projectId),
        enabled: Boolean(projectId),
    });
    const { data: knowledgeResults = [] } = useQuery({
        queryKey: ["orchestration", "project", projectId, "knowledge", knowledgeQuery, includeDecisionRecall],
        queryFn: () => searchProjectKnowledge(projectId, knowledgeQuery, undefined, { includeDecisions: includeDecisionRecall }),
        enabled: Boolean(projectId) && knowledgeQuery.trim().length >= 3,
    });
    const { data: semanticEntries = [] } = useQuery({
        queryKey: ["orchestration", "project", projectId, "semantic-memory", knowledgeQuery],
        queryFn: () => listSemanticMemory(projectId, knowledgeQuery.trim() ? { q: knowledgeQuery, limit: 25 } : { limit: 25 }),
        enabled: Boolean(projectId),
    });
    const { data: projectMemorySettings } = useQuery({
        queryKey: ["orchestration", "project", projectId, "memory-settings"],
        queryFn: () => getProjectMemorySettings(projectId),
        enabled: Boolean(projectId),
    });
    const { data: memoryIngestJobs = [] } = useQuery({
        queryKey: ["orchestration", "project", projectId, "memory-ingest-jobs"],
        queryFn: () => listProjectMemoryIngestJobs(projectId, 80),
        enabled: Boolean(projectId),
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

    const { data: dagReadyList = [] } = useQuery({
        queryKey: ["orchestration", "project", projectId, "dag-ready"],
        queryFn: () => listDagReadyTasks(projectId),
        enabled: Boolean(projectId) && tab === "dag",
    });
    const { data: mergePreview } = useQuery({
        queryKey: ["orchestration", "project", projectId, "merge-preview", mergeTaskId],
        queryFn: () => getMergeResolutionPreview(projectId, mergeTaskId as string),
        enabled: Boolean(projectId) && Boolean(mergeTaskId),
    });

    useLiveSnapshotStream(
        projectId ? `/orchestration/projects/${projectId}/stream` : null,
        {
            enabled: Boolean(projectId),
            onSnapshot: () => {
                void queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId] });
                void queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "tasks"] });
                void queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "runs"] });
                void queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "dag-ready"] });
                void queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "sync-events"] });
                void queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "memory-ingest-jobs"] });
                void queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "repository-index-status"] });
                void queryClient.invalidateQueries({ queryKey: ["orchestration", "approvals"] });
            },
        }
    );

    const projectAgentMap = useMemo(() => new Set(projectAgents.map((item) => item.agent_id)), [projectAgents]);
    const projectAgentProfiles = useMemo(
        () => allAgents.filter((agent) => projectAgentMap.has(agent.id)),
        [allAgents, projectAgentMap],
    );
    const availableAgents = allAgents.filter((agent) => !projectAgentMap.has(agent.id));
    const activeRuns = runs.filter((item) => ["queued", "in_progress"].includes(item.status));
    const brainstormParticipantProfiles = useMemo(
        () => allAgents.filter((agent) => brainstormForm.participant_agent_ids.includes(agent.id)),
        [allAgents, brainstormForm.participant_agent_ids],
    );
    const brainstormSuggestedOutput = useMemo(() => {
        const byMode: Record<string, string> = {
            exploration: "implementation_plan",
            solution_design: "implementation_plan",
            code_review: "test_plan",
            incident_triage: "risk_register",
            root_cause: "risk_register",
            architecture_proposal: "adr",
        };
        return byMode[brainstormForm.mode] ?? "implementation_plan";
    }, [brainstormForm.mode]);
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
    const dagTaskDependents = useMemo(() => {
        if (!dagTask) return [];
        return tasks.filter((task) => (task.dependency_ids ?? []).includes(dagTask.id));
    }, [tasks, dagTask]);
    const dagBlockedSuggestion = useMemo(() => {
        if (!dagTask) return null;
        const targetId = typeof dagTask.metadata?.suggested_handoff_agent_id === "string" ? dagTask.metadata.suggested_handoff_agent_id : "";
        if (!targetId) return null;
        const targetAgent = allAgents.find((agent) => agent.id === targetId);
        return {
            agentName: targetAgent?.name || targetId,
            via: String(dagTask.metadata?.handoff_suggested_via || "handoff rule"),
            reason: String(dagTask.metadata?.handoff_blocked_reason || ""),
        };
    }, [allAgents, dagTask]);
    const dagDescendantIds = useMemo(() => {
        if (!dagTask) return new Set<string>();
        const dependentsById = new Map<string, string[]>();
        for (const task of tasks) {
            for (const depId of task.dependency_ids ?? []) {
                const current = dependentsById.get(depId) ?? [];
                current.push(task.id);
                dependentsById.set(depId, current);
            }
        }
        const descendants = new Set<string>();
        const stack = [...(dependentsById.get(dagTask.id) ?? [])];
        while (stack.length > 0) {
            const current = stack.pop();
            if (!current || descendants.has(current)) continue;
            descendants.add(current);
            stack.push(...(dependentsById.get(current) ?? []));
        }
        return descendants;
    }, [dagTask, tasks]);
    const currentDagDependencySelection = dagTask ? (dagDependencyDrafts[dagTask.id] ?? dagTask.dependency_ids ?? []) : [];
    const githubDefaults = useMemo(() => {
        const gh = (project?.settings?.github as Record<string, unknown> | undefined) ?? {};
        return {
            branch_prefix: String(gh.branch_prefix ?? "troop/{task_id}-{slug}"),
            enforce_branch_naming: Boolean(gh.enforce_branch_naming ?? true),
            auto_post_progress: Boolean(gh.auto_post_progress),
            auto_activate_review_on_pr_open: Boolean(gh.auto_activate_review_on_pr_open ?? true),
            auto_review_on_pr_review: Boolean(gh.auto_review_on_pr_review),
            close_issue_with_manager_summary: Boolean(gh.close_issue_with_manager_summary ?? true),
            sync_labels_to_github: Boolean(gh.sync_labels_to_github ?? true),
            sync_assignees_to_github: Boolean(gh.sync_assignees_to_github ?? true),
            sync_state_to_github: Boolean(gh.sync_state_to_github ?? true),
            sync_milestone_to_github: Boolean(gh.sync_milestone_to_github ?? true),
            repo_agent_pools_json: JSON.stringify(gh.repo_agent_pools ?? {}, null, 2),
        };
    }, [project?.settings]);
    const resolvedGithubForm = { ...githubDefaults, ...githubForm };
    const hitlDefaults = useMemo(() => {
        const hitl = (project?.settings?.hitl as Record<string, unknown> | undefined) ?? {};
        return {
            sandbox_note: String(hitl.sandbox_note ?? ""),
            secret_scope: String(hitl.secret_scope ?? "project_default"),
            sandbox_mode: String(hitl.sandbox_mode ?? "allow_host_fallback"),
        };
    }, [project?.settings]);
    const resolvedHitlForm = { ...hitlDefaults, ...hitlForm };
    const executionSettings = ((project?.settings?.execution as Record<string, unknown> | undefined) ?? {}) as Record<string, unknown>;
    const resolvedProjectTeamSettings = projectTeamSettings ?? {
        manager_agent_id: String((executionSettings.manager_agent_id as string | undefined) ?? ""),
        reviewer_agent_ids: Array.isArray(executionSettings.reviewer_agent_ids) ? executionSettings.reviewer_agent_ids as string[] : [],
        reviewer_chain_mode: String((executionSettings.reviewer_chain_mode as string | undefined) ?? "sequential"),
        autonomy_level: String((executionSettings.autonomy_level as string | undefined) ?? "semi-autonomous"),
        provider_config_id: String((executionSettings.provider_config_id as string | undefined) ?? ""),
        model_name: String((executionSettings.model_name as string | undefined) ?? ""),
        fallback_model: String((executionSettings.fallback_model as string | undefined) ?? ""),
        escalation_target_agent_id: String((((executionSettings.escalation_rules as Array<Record<string, unknown>> | undefined) ?? [])[0]?.escalate_to as string | undefined) ?? ""),
        stuck_for_minutes: String((((executionSettings.escalation_rules as Array<Record<string, unknown>> | undefined) ?? []).find((item) => item.condition === "stuck_for_minutes")?.value as number | undefined) ?? 30),
        cost_exceeds_usd: String((((executionSettings.escalation_rules as Array<Record<string, unknown>> | undefined) ?? []).find((item) => item.condition === "cost_exceeds_usd")?.value as number | undefined) ?? 10),
        no_consensus_after_rounds: String((((executionSettings.escalation_rules as Array<Record<string, unknown>> | undefined) ?? []).find((item) => item.condition === "no_consensus_after_rounds")?.value as number | undefined) ?? 3),
        routing_mode: String((executionSettings.routing_mode as string | undefined) ?? "capability_based"),
        sibling_load_balance: String((executionSettings.sibling_load_balance as string | undefined) ?? "queue_depth"),
        skip_unhealthy_worker_providers: executionSettings.skip_unhealthy_worker_providers !== false,
        offline_local_only_mode: Boolean(executionSettings.offline_local_only_mode),
        enforce_project_model_policy: Boolean(executionSettings.enforce_project_model_policy),
        allowed_provider_types_csv: Array.isArray(executionSettings.allowed_provider_types)
            ? (executionSettings.allowed_provider_types as string[]).join(", ")
            : "",
        allowed_model_slugs_csv: Array.isArray(executionSettings.allowed_model_slugs)
            ? (executionSettings.allowed_model_slugs as string[]).join(", ")
            : "",
        blocked_handoff_mode: String(((executionSettings.blocked_handoff as Record<string, unknown> | undefined)?.mode as string | undefined) ?? "escalation_path"),
        blocked_handoff_target_agent_id: String(((executionSettings.blocked_handoff as Record<string, unknown> | undefined)?.target_agent_id as string | undefined) ?? ""),
        blocked_handoff_fallback_to_manager: ((executionSettings.blocked_handoff as Record<string, unknown> | undefined)?.fallback_to_manager as boolean | undefined) !== false,
        sla_enabled: ((executionSettings.sla as Record<string, unknown> | undefined)?.enabled as boolean | undefined) !== false,
        sla_warn_hours: String(((executionSettings.sla as Record<string, unknown> | undefined)?.warn_hours_before_due as number | undefined) ?? 24),
        sla_escalate_after_due_hours: String(((executionSettings.sla as Record<string, unknown> | undefined)?.escalate_hours_after_due as number | undefined) ?? 0),
    };
    const policyRoutingPreview = useMemo(() => {
        const policy = ((executionSettings.policy_routing as Record<string, unknown> | undefined) ?? {}) as {
            cheap_model_slug?: string;
            strong_model_slug?: string;
            local_model_slug?: string;
            rules?: PolicyRoutingRule[];
        };
        const labels = policyPreviewForm.labelsCsv
            .split(",")
            .map((item) => item.trim())
            .filter(Boolean);
        const sample = {
            priority: policyPreviewForm.priority,
            taskType: policyPreviewForm.taskType,
            labels,
            projectSensitive: policyPreviewForm.projectSensitive,
        };
        const rules = Array.isArray(policy.rules) ? policy.rules : [];
        let matchedRule: PolicyRoutingRule | null = null;
        let routeKey = "";
        for (const rule of rules) {
            const field = String(rule.field ?? "");
            const operator = String(rule.operator ?? "equals");
            const actual = policyFieldValue(field, sample);
            if (!policyRuleMatches(actual, operator, rule.value)) continue;
            matchedRule = rule;
            routeKey = String(rule.route_to ?? "");
            break;
        }
        const fallbackModel =
            resolvedProjectTeamSettings.model_name ||
            providers.find((provider) => provider.id === resolvedProjectTeamSettings.provider_config_id)?.default_model ||
            "provider/default";
        const modelFromRoute = routeKey
            ? String((policy as Record<string, unknown>)[routeKey] ?? "")
            : "";
        const selectedModel = modelFromRoute || fallbackModel;
        const selectedProvider =
            routeKey === "local_model_slug"
                ? providers.find((provider) => provider.provider_type === "ollama" && provider.is_enabled) ?? null
                : providers.find((provider) => provider.id === resolvedProjectTeamSettings.provider_config_id) ?? null;
        return {
            matchedRule,
            routeKey,
            selectedModel,
            selectedProviderName: selectedProvider?.name ?? (routeKey === "local_model_slug" ? "local runtime fallback" : "project/default provider"),
        };
    }, [
        executionSettings.policy_routing,
        policyPreviewForm.labelsCsv,
        policyPreviewForm.priority,
        policyPreviewForm.projectSensitive,
        policyPreviewForm.taskType,
        providers,
        resolvedProjectTeamSettings.model_name,
        resolvedProjectTeamSettings.provider_config_id,
    ]);
    const resolvedMemorySettings = memorySettingsDraft ?? {
        semantic_write_requires_approval: Boolean(projectMemorySettings?.semantic_write_requires_approval),
        episodic_retention_days: String(projectMemorySettings?.episodic_retention_days ?? 90),
        deep_recall_mode: Boolean(projectMemorySettings?.deep_recall_mode),
    };
    const memoryIngestCounts = useMemo(() => {
        const counts = { pending: 0, running: 0, completed: 0, failed: 0 };
        for (const job of memoryIngestJobs) {
            const status = String(job.status);
            if (status === "pending") counts.pending += 1;
            else if (status === "running") counts.running += 1;
            else if (status === "completed") counts.completed += 1;
            else if (status === "failed") counts.failed += 1;
        }
        return counts;
    }, [memoryIngestJobs]);

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
        mutationFn: ({ parentTaskId, notes }: { parentTaskId: string; notes: string }) =>
            startMergeResolutionRun(projectId, parentTaskId, {
                notes,
                input_payload: {
                    merge_resolution: {
                        checklist_confirmed: true,
                        notes,
                    },
                },
            }),
        onSuccess: async (run) => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "runs"] });
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "tasks"] });
            showToast({ message: "Merge resolution run queued.", severity: "success" });
            setMergeTaskId(null);
            setMergeNotes("");
            navigate(`/runs/${run.id}`);
        },
    });
    const queueRepositoryIndexMutation = useMutation({
        mutationFn: ({ repositoryLinkId, mode, pathPrefixes, scheduleLabel, autoEnabled }: {
            repositoryLinkId: string;
            mode: "full" | "incremental";
            pathPrefixes: string[];
            scheduleLabel?: string | null;
            autoEnabled?: boolean | null;
        }) =>
            queueProjectRepositoryIndex(projectId, repositoryLinkId, {
                mode,
                path_prefixes: pathPrefixes,
                schedule_label: scheduleLabel,
                auto_enabled: autoEnabled,
            }),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "memory-ingest-jobs"] });
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "repository-index-status"] });
            showToast({ message: "Repository indexing queued.", severity: "success" });
        },
    });
    const updateRepositoryMutation = useMutation({
        mutationFn: ({ repositoryLinkId, defaultBranch, metadata }: {
            repositoryLinkId: string;
            defaultBranch?: string | null;
            metadata?: Record<string, unknown>;
        }) =>
            updateProjectRepository(projectId, repositoryLinkId, {
                default_branch: defaultBranch,
                metadata,
            }),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "repositories"] });
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "repository-index-status"] });
            showToast({ message: "Repository index settings saved.", severity: "success" });
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
    const updateHierarchyAgentMutation = useMutation({
        mutationFn: ({ agentId, payload }: { agentId: string; payload: Record<string, unknown> }) =>
            updateAgent(agentId, payload),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "agents"] });
            showToast({ message: "Reporting line updated.", severity: "success" });
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
            setBrainstormForm({
                topic: "",
                task_id: "",
                moderator_agent_id: "",
                participant_agent_ids: [],
                mode: "exploration",
                output_type: "implementation_plan",
                max_rounds: "3",
                max_cost_usd: "10",
                max_repetition_score: "0.92",
                soft_consensus_min_similarity: "0.72",
                conflict_pairwise_max_similarity: "0.38",
                stop_on_consensus: true,
                accept_soft_consensus: true,
                escalate_on_no_consensus: true,
            });
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "brainstorms"] });
            showToast({ message: "Brainstorm created.", severity: "success" });
            await startBrainstorm(brainstorm.id);
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "runs"] });
        },
        onError: (error) => {
            showToast({ message: extractApiErrorMessage(error, "Couldn't start brainstorm. Try again."), severity: "error" });
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
    const updateDagTaskMutation = useMutation({
        mutationFn: ({ taskId, payload }: { taskId: string; payload: Record<string, unknown> }) =>
            updateOrchestrationTask(projectId, taskId, payload),
        onSuccess: async (_, variables) => {
            setDagDependencyDrafts((current) => {
                const next = { ...current };
                delete next[variables.taskId];
                return next;
            });
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "tasks"] });
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "dag-ready"] });
            showToast({ message: "Task graph updated.", severity: "success" });
        },
        onError: (error) => {
            showToast({ message: extractApiErrorMessage(error, "Couldn't save task graph. Refresh and retry."), severity: "error" });
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
        mutationFn: ({ approvalId, status, reason }: { approvalId: string; status: "approved" | "rejected"; reason?: string }) =>
            decideApproval(approvalId, { status, reason }),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "memory"] });
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "approvals"] });
            showToast({ message: "Memory review updated.", severity: "success" });
        },
    });
    const memorySettingsMutation = useMutation({
        mutationFn: (payload: Record<string, unknown>) => patchProjectMemorySettings(projectId, payload),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "memory-settings"] });
            showToast({ message: "Memory rules updated.", severity: "success" });
        },
    });
    const pendingMemoryApprovals = approvals.filter(
        (approval) => approval.project_id === projectId && approval.approval_type === "agent_memory_write" && approval.status === "pending",
    );
    const pendingProjectApprovals = approvals.filter(
        (approval) => approval.project_id === projectId && approval.status === "pending",
    );

    const providerOptions: ProviderConfig[] = providers;
    const saveProjectExecutionSettings = () => {
        const escalationRules = [
            {
                condition: "stuck_for_minutes",
                value: Number(resolvedProjectTeamSettings.stuck_for_minutes || 0),
                escalate_to: resolvedProjectTeamSettings.escalation_target_agent_id || resolvedProjectTeamSettings.manager_agent_id || null,
            },
            {
                condition: "cost_exceeds_usd",
                value: Number(resolvedProjectTeamSettings.cost_exceeds_usd || 0),
                escalate_to: resolvedProjectTeamSettings.escalation_target_agent_id || resolvedProjectTeamSettings.manager_agent_id || null,
            },
            {
                condition: "no_consensus_after_rounds",
                value: Number(resolvedProjectTeamSettings.no_consensus_after_rounds || 0),
                escalate_to: resolvedProjectTeamSettings.escalation_target_agent_id || resolvedProjectTeamSettings.manager_agent_id || null,
            },
        ];
        saveProjectSettingsMutation.mutate({
            settings: {
                ...(project?.settings ?? {}),
                execution: {
                    ...executionSettings,
                    manager_agent_id: resolvedProjectTeamSettings.manager_agent_id || null,
                    reviewer_agent_ids: resolvedProjectTeamSettings.reviewer_agent_ids,
                    reviewer_chain_mode: resolvedProjectTeamSettings.reviewer_chain_mode || "sequential",
                    autonomy_level: resolvedProjectTeamSettings.autonomy_level,
                    provider_config_id: resolvedProjectTeamSettings.provider_config_id || null,
                    model_name: resolvedProjectTeamSettings.model_name || null,
                    fallback_model: resolvedProjectTeamSettings.fallback_model || null,
                    escalation_rules: escalationRules,
                    routing_mode: resolvedProjectTeamSettings.routing_mode || "capability_based",
                    sibling_load_balance: resolvedProjectTeamSettings.sibling_load_balance || "queue_depth",
                    skip_unhealthy_worker_providers: resolvedProjectTeamSettings.skip_unhealthy_worker_providers,
                    offline_local_only_mode: resolvedProjectTeamSettings.offline_local_only_mode,
                    enforce_project_model_policy: resolvedProjectTeamSettings.enforce_project_model_policy,
                    allowed_provider_types: resolvedProjectTeamSettings.allowed_provider_types_csv
                        .split(",")
                        .map((item) => item.trim().toLowerCase())
                        .filter(Boolean),
                    allowed_model_slugs: resolvedProjectTeamSettings.allowed_model_slugs_csv
                        .split(",")
                        .map((item) => item.trim())
                        .filter(Boolean),
                    blocked_handoff: {
                        mode: resolvedProjectTeamSettings.blocked_handoff_mode || "escalation_path",
                        target_agent_id: resolvedProjectTeamSettings.blocked_handoff_target_agent_id || null,
                        fallback_to_manager: resolvedProjectTeamSettings.blocked_handoff_fallback_to_manager,
                    },
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
        let repoAgentPools: Record<string, unknown> = {};
        try {
            repoAgentPools = JSON.parse(resolvedGithubForm.repo_agent_pools_json || "{}") as Record<string, unknown>;
        } catch {
            showToast({ message: "Repo agent pools must be valid JSON.", severity: "error" });
            return;
        }
        saveProjectSettingsMutation.mutate({
            settings: {
                ...(project?.settings ?? {}),
                github: {
                    ...((project?.settings?.github as Record<string, unknown> | undefined) ?? {}),
                    branch_prefix: resolvedGithubForm.branch_prefix,
                    enforce_branch_naming: resolvedGithubForm.enforce_branch_naming,
                    auto_post_progress: resolvedGithubForm.auto_post_progress,
                    auto_activate_review_on_pr_open: resolvedGithubForm.auto_activate_review_on_pr_open,
                    auto_review_on_pr_review: resolvedGithubForm.auto_review_on_pr_review,
                    close_issue_with_manager_summary: resolvedGithubForm.close_issue_with_manager_summary,
                    sync_labels_to_github: resolvedGithubForm.sync_labels_to_github,
                    sync_assignees_to_github: resolvedGithubForm.sync_assignees_to_github,
                    sync_state_to_github: resolvedGithubForm.sync_state_to_github,
                    sync_milestone_to_github: resolvedGithubForm.sync_milestone_to_github,
                    repo_agent_pools: repoAgentPools,
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
                    sandbox_note: resolvedHitlForm.sandbox_note,
                    secret_scope: resolvedHitlForm.secret_scope,
                    sandbox_mode: resolvedHitlForm.sandbox_mode,
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
                            onClick={() => navigate(`/projects/${projectId}/memory`)}
                        >
                            Memory
                        </Button>
                        <Button variant="outlined" size="small" onClick={() => navigate(`/projects/${projectId}/benchmark`)}>
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
                                <Stack spacing={2} sx={{ mb: 2 }}>
                                    <Box>
                                        <LinearProgress variant="determinate" value={milestoneProgress} sx={{ height: 6, borderRadius: 3 }} />
                                        <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: "block" }}>
                                            {milestones.filter((m) => m.status === "completed").length} / {milestones.length} completed
                                        </Typography>
                                    </Box>
                                    <MilestoneTimeline milestones={milestones} />
                                </Stack>
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
                                <TextField size="small" label="Description" value={milestoneForm.description} onChange={(e) => setMilestoneForm((f) => ({ ...f, description: e.target.value }))} multiline minRows={2} />
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
                                        description: milestoneForm.description || null,
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
                        <SectionCard
                            title="Pending approvals"
                            description="Approve or reject blocked actions inline. Rejections require a reason."
                        >
                            <Stack spacing={1.5}>
                                {pendingProjectApprovals.length === 0 ? (
                                    <Typography variant="body2" color="text.secondary">No pending approvals.</Typography>
                                ) : pendingProjectApprovals.map((approval) => (
                                    <Paper key={approval.id} sx={{ p: 1.5, borderRadius: 2, border: 1, borderColor: "divider" }}>
                                        <Stack spacing={1}>
                                            <Typography variant="subtitle2">{humanizeKey(approval.approval_type)}</Typography>
                                            <Typography variant="caption" color="text.secondary">
                                                Requested {formatDateTime(approval.created_at)}
                                            </Typography>
                                            <TextField
                                                size="small"
                                                label="Reason"
                                                value={approvalReasonById[approval.id] ?? ""}
                                                onChange={(e) => setApprovalReasonById((current) => ({ ...current, [approval.id]: e.target.value }))}
                                                placeholder="Required when rejecting"
                                            />
                                            <Stack direction="row" spacing={1}>
                                                <Button
                                                    size="small"
                                                    variant="contained"
                                                    onClick={() => memoryApprovalMutation.mutate({ approvalId: approval.id, status: "approved", reason: approvalReasonById[approval.id] || undefined })}
                                                >
                                                    Approve
                                                </Button>
                                                <Button
                                                    size="small"
                                                    variant="outlined"
                                                    color="error"
                                                    onClick={() => {
                                                        const reason = (approvalReasonById[approval.id] ?? "").trim();
                                                        if (!reason) {
                                                            showToast({ message: "Rejection reason is required.", severity: "warning" });
                                                            return;
                                                        }
                                                        memoryApprovalMutation.mutate({ approvalId: approval.id, status: "rejected", reason });
                                                    }}
                                                >
                                                    Reject
                                                </Button>
                                            </Stack>
                                        </Stack>
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
                            {createTaskMutation.isError && <Alert severity="error">Couldn't create task. Check fields and try again.</Alert>}
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
                    <SectionCard title="Task dependency graph" description="Nodes represent tasks; click a node to edit dependencies, inspect downstream impact, and run or merge work. Arrows point from dependency → dependent. Drag tasks on the board tab to change status.">
                        {dagReadyList.length > 0 ? (
                            <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap sx={{ mb: 1.5 }}>
                                {dagReadyList.slice(0, 8).map((task) => (
                                    <Chip key={task.id} label={`Ready: ${task.title}`} size="small" color="info" variant="outlined" />
                                ))}
                            </Stack>
                        ) : null}
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
                                                <TextField
                                                    select
                                                    size="small"
                                                    label="Reports to"
                                                    value={agent?.parent_agent_id ?? ""}
                                                    onChange={(event) => updateHierarchyAgentMutation.mutate({
                                                        agentId: membership.agent_id,
                                                        payload: { parent_agent_id: event.target.value || null },
                                                    })}
                                                    sx={{ minWidth: 180 }}
                                                >
                                                    <MenuItem value="">None</MenuItem>
                                                    {projectAgentProfiles.filter((item) => item.id !== membership.agent_id).map((candidate) => (
                                                        <MenuItem key={`parent-${candidate.id}`} value={candidate.id}>{candidate.name}</MenuItem>
                                                    ))}
                                                </TextField>
                                                <TextField
                                                    select
                                                    size="small"
                                                    label="Reviewer"
                                                    value={agent?.reviewer_agent_id ?? ""}
                                                    onChange={(event) => updateHierarchyAgentMutation.mutate({
                                                        agentId: membership.agent_id,
                                                        payload: { reviewer_agent_id: event.target.value || null },
                                                    })}
                                                    sx={{ minWidth: 180 }}
                                                >
                                                    <MenuItem value="">None</MenuItem>
                                                    {projectAgentProfiles.filter((item) => item.id !== membership.agent_id).map((candidate) => (
                                                        <MenuItem key={`reviewer-${candidate.id}`} value={candidate.id}>{candidate.name}</MenuItem>
                                                    ))}
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
                                    label="Reviewer chain"
                                    value={resolvedProjectTeamSettings.reviewer_agent_ids}
                                    onChange={(event) => setProjectTeamSettings((current) => ({
                                        ...(current ?? resolvedProjectTeamSettings),
                                        reviewer_agent_ids: typeof event.target.value === "string" ? [event.target.value] : event.target.value,
                                    }))}
                                    helperText="Ordered reviewers. Each approval hands off to the next reviewer before the task is finally approved."
                                >
                                    {projectAgents.map((membership) => {
                                        const agent = allAgents.find((item) => item.id === membership.agent_id);
                                        return <MenuItem key={`reviewer-${membership.id}`} value={membership.agent_id}>{agent?.name || membership.agent_id}</MenuItem>;
                                    })}
                                </TextField>
                                <TextField
                                    select
                                    label="Reviewer chain mode"
                                    value={resolvedProjectTeamSettings.reviewer_chain_mode}
                                    onChange={(event) => setProjectTeamSettings((current) => ({
                                        ...(current ?? resolvedProjectTeamSettings),
                                        reviewer_chain_mode: event.target.value,
                                    }))}
                                >
                                    <MenuItem value="sequential">Sequential</MenuItem>
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
                                    Auto-assignment can optimize for capability match, deadlines, provider health, cost, or explicit pinning. User-pinned workers still win over auto-selection.
                                </Typography>
                                <TextField
                                    select
                                    label="Routing mode"
                                    value={resolvedProjectTeamSettings.routing_mode}
                                    onChange={(event) => setProjectTeamSettings((current) => ({ ...(current ?? resolvedProjectTeamSettings), routing_mode: event.target.value }))}
                                    helperText="Matches the Stage 2 routing modes. Pinned workers still override automatic routing."
                                >
                                    <MenuItem value="capability_based">Capability-based</MenuItem>
                                    <MenuItem value="priority_sla">Priority / SLA aware</MenuItem>
                                    <MenuItem value="cost_aware">Cost-aware</MenuItem>
                                    <MenuItem value="model_availability">Model availability</MenuItem>
                                    <MenuItem value="user_pinned">User-pinned fallback mode</MenuItem>
                                    <MenuItem value="throughput">Throughput</MenuItem>
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
                                <Stack direction="row" alignItems="center" spacing={1}>
                                    <Switch
                                        checked={resolvedProjectTeamSettings.offline_local_only_mode}
                                        onChange={(_, checked) => setProjectTeamSettings((current) => ({
                                            ...(current ?? resolvedProjectTeamSettings),
                                            offline_local_only_mode: checked,
                                        }))}
                                    />
                                    <Typography variant="body2">Offline/local-only mode (restrict execution to local providers)</Typography>
                                </Stack>
                                <Stack direction="row" alignItems="center" spacing={1}>
                                    <Switch
                                        checked={resolvedProjectTeamSettings.enforce_project_model_policy}
                                        onChange={(_, checked) => setProjectTeamSettings((current) => ({
                                            ...(current ?? resolvedProjectTeamSettings),
                                            enforce_project_model_policy: checked,
                                        }))}
                                    />
                                    <Typography variant="body2">Enforce project model policy allowlists</Typography>
                                </Stack>
                                <TextField
                                    label="Allowed provider types (CSV)"
                                    value={resolvedProjectTeamSettings.allowed_provider_types_csv}
                                    onChange={(event) => setProjectTeamSettings((current) => ({
                                        ...(current ?? resolvedProjectTeamSettings),
                                        allowed_provider_types_csv: event.target.value,
                                    }))}
                                    helperText="Example: openai, openai_compatible, ollama"
                                />
                                <TextField
                                    label="Allowed model slugs (CSV)"
                                    value={resolvedProjectTeamSettings.allowed_model_slugs_csv}
                                    onChange={(event) => setProjectTeamSettings((current) => ({
                                        ...(current ?? resolvedProjectTeamSettings),
                                        allowed_model_slugs_csv: event.target.value,
                                    }))}
                                    helperText="Optional strict allowlist for model names."
                                />
                                <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 3 }}>
                                    <Stack spacing={1.25}>
                                        <Typography variant="subtitle2">Policy routing preview</Typography>
                                        <Typography variant="body2" color="text.secondary">
                                            Simulate routing for a sample task before starting a run.
                                        </Typography>
                                        <Stack direction={{ xs: "column", md: "row" }} spacing={1.25}>
                                            <TextField
                                                select
                                                label="Sample priority"
                                                value={policyPreviewForm.priority}
                                                onChange={(event) => setPolicyPreviewForm((current) => ({ ...current, priority: event.target.value }))}
                                                fullWidth
                                            >
                                                <MenuItem value="low">low</MenuItem>
                                                <MenuItem value="normal">normal</MenuItem>
                                                <MenuItem value="high">high</MenuItem>
                                                <MenuItem value="urgent">urgent</MenuItem>
                                            </TextField>
                                            <TextField
                                                label="Sample task type"
                                                value={policyPreviewForm.taskType}
                                                onChange={(event) => setPolicyPreviewForm((current) => ({ ...current, taskType: event.target.value }))}
                                                fullWidth
                                            />
                                        </Stack>
                                        <TextField
                                            label="Sample labels (CSV)"
                                            value={policyPreviewForm.labelsCsv}
                                            onChange={(event) => setPolicyPreviewForm((current) => ({ ...current, labelsCsv: event.target.value }))}
                                        />
                                        <Stack direction="row" alignItems="center" spacing={1}>
                                            <Switch
                                                checked={policyPreviewForm.projectSensitive}
                                                onChange={(_, checked) => setPolicyPreviewForm((current) => ({ ...current, projectSensitive: checked }))}
                                            />
                                            <Typography variant="body2">Project is sensitive</Typography>
                                        </Stack>
                                        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                                            <Chip
                                                size="small"
                                                color={policyRoutingPreview.routeKey ? "info" : "default"}
                                                label={
                                                    policyRoutingPreview.routeKey
                                                        ? `Matched route: ${policyRoutingPreview.routeKey}`
                                                        : "No matching route rule"
                                                }
                                            />
                                            <Chip size="small" color="success" label={`Model: ${policyRoutingPreview.selectedModel}`} />
                                            <Chip size="small" variant="outlined" label={`Provider: ${policyRoutingPreview.selectedProviderName}`} />
                                        </Stack>
                                    </Stack>
                                </Paper>
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
                                <TextField
                                    select
                                    label="Escalation target"
                                    value={resolvedProjectTeamSettings.escalation_target_agent_id}
                                    onChange={(event) => setProjectTeamSettings((current) => ({
                                        ...(current ?? resolvedProjectTeamSettings),
                                        escalation_target_agent_id: event.target.value,
                                    }))}
                                    helperText="Default recipient for rule-based escalations."
                                >
                                    <MenuItem value="">Project manager</MenuItem>
                                    {projectAgents.map((membership) => {
                                        const agent = allAgents.find((item) => item.id === membership.agent_id);
                                        return <MenuItem key={`escalate-${membership.id}`} value={membership.agent_id}>{agent?.name || membership.agent_id}</MenuItem>;
                                    })}
                                </TextField>
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
                                <Divider />
                                <Typography variant="subtitle2">Blocked handoff</Typography>
                                <TextField
                                    select
                                    label="Blocked-task handoff mode"
                                    value={resolvedProjectTeamSettings.blocked_handoff_mode}
                                    onChange={(event) => setProjectTeamSettings((current) => ({
                                        ...(current ?? resolvedProjectTeamSettings),
                                        blocked_handoff_mode: event.target.value,
                                    }))}
                                >
                                    <MenuItem value="escalation_path">Worker escalation path</MenuItem>
                                    <MenuItem value="configured_agent">Configured fallback agent</MenuItem>
                                    <MenuItem value="sibling_with_capacity">Sibling with capacity</MenuItem>
                                </TextField>
                                <TextField
                                    select
                                    label="Configured handoff agent"
                                    value={resolvedProjectTeamSettings.blocked_handoff_target_agent_id}
                                    onChange={(event) => setProjectTeamSettings((current) => ({
                                        ...(current ?? resolvedProjectTeamSettings),
                                        blocked_handoff_target_agent_id: event.target.value,
                                    }))}
                                    helperText="Used when blocked-task handoff mode is configured_agent."
                                >
                                    <MenuItem value="">None</MenuItem>
                                    {projectAgents.map((membership) => {
                                        const agent = allAgents.find((item) => item.id === membership.agent_id);
                                        return <MenuItem key={`handoff-${membership.id}`} value={membership.agent_id}>{agent?.name || membership.agent_id}</MenuItem>;
                                    })}
                                </TextField>
                                <Stack direction="row" alignItems="center" spacing={1}>
                                    <Switch
                                        checked={resolvedProjectTeamSettings.blocked_handoff_fallback_to_manager}
                                        onChange={(_, checked) => setProjectTeamSettings((current) => ({
                                            ...(current ?? resolvedProjectTeamSettings),
                                            blocked_handoff_fallback_to_manager: checked,
                                        }))}
                                    />
                                    <Typography variant="body2">Fall back to project manager when the selected handoff target is unavailable</Typography>
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
                                            { key: "change_task_ownership", label: "Change task ownership", description: "Reassign task assignee/owner" },
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
                    <SectionCard title="Start brainstorm" description="Configure room mode, participants, moderator, and guardrails before launching the discussion.">
                        <Stack spacing={2}>
                            <TextField label="Topic" value={brainstormForm.topic} onChange={(e) => setBrainstormForm((current) => ({ ...current, topic: e.target.value }))} />
                            <TextField
                                select
                                label="Linked task"
                                value={brainstormForm.task_id}
                                onChange={(e) => setBrainstormForm((current) => ({ ...current, task_id: e.target.value }))}
                                helperText="Optional. Use this when the brainstorm should directly support a task."
                            >
                                <MenuItem value="">None</MenuItem>
                                {tasks.map((task) => (
                                    <MenuItem key={task.id} value={task.id}>{task.title}</MenuItem>
                                ))}
                            </TextField>
                            <TextField
                                select
                                label="Moderator"
                                value={brainstormForm.moderator_agent_id}
                                onChange={(e) => setBrainstormForm((current) => ({ ...current, moderator_agent_id: e.target.value }))}
                                helperText="Leave empty to use the project manager automatically."
                            >
                                <MenuItem value="">Auto-select project manager</MenuItem>
                                {projectAgentProfiles.map((agent) => (
                                    <MenuItem key={agent.id} value={agent.id}>{agent.name}</MenuItem>
                                ))}
                            </TextField>
                            <TextField
                                select
                                SelectProps={{ multiple: true }}
                                label="Participants"
                                value={brainstormForm.participant_agent_ids}
                                onChange={(e) => {
                                    const nextValue = e.target.value;
                                    setBrainstormForm((current) => ({
                                        ...current,
                                        participant_agent_ids: Array.isArray(nextValue) ? nextValue : String(nextValue).split(",").filter(Boolean),
                                    }));
                                }}
                                helperText="At least two agents are required."
                            >
                                {projectAgentProfiles.map((agent) => (
                                    <MenuItem key={agent.id} value={agent.id}>{agent.name}</MenuItem>
                                ))}
                            </TextField>
                            {brainstormParticipantProfiles.length > 0 ? (
                                <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                                    {brainstormParticipantProfiles.map((agent) => (
                                        <Chip key={agent.id} label={agent.name} size="small" variant="outlined" />
                                    ))}
                                </Stack>
                            ) : null}
                            <TextField
                                select
                                label="Mode"
                                value={brainstormForm.mode}
                                onChange={(e) => {
                                    const mode = e.target.value;
                                    setBrainstormForm((current) => ({
                                        ...current,
                                        mode,
                                        output_type: current.output_type === brainstormSuggestedOutput ? mode === "code_review" ? "test_plan" : mode === "incident_triage" || mode === "root_cause" ? "risk_register" : mode === "architecture_proposal" ? "adr" : "implementation_plan" : current.output_type,
                                    }));
                                }}
                            >
                                {BRAINSTORM_MODE_OPTIONS.map((option) => (
                                    <MenuItem key={option.value} value={option.value}>{option.label}</MenuItem>
                                ))}
                            </TextField>
                            <TextField
                                select
                                label="Output"
                                value={brainstormForm.output_type}
                                onChange={(e) => setBrainstormForm((current) => ({ ...current, output_type: e.target.value }))}
                                helperText={`Recommended for this mode: ${humanizeKey(brainstormSuggestedOutput)}`}
                            >
                                {BRAINSTORM_OUTPUT_OPTIONS.map((option) => (
                                    <MenuItem key={option.value} value={option.value}>{option.label}</MenuItem>
                                ))}
                            </TextField>
                            <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
                                <TextField label="Max rounds" type="number" value={brainstormForm.max_rounds} onChange={(e) => setBrainstormForm((current) => ({ ...current, max_rounds: e.target.value }))} fullWidth />
                                <TextField label="Cost cap (USD)" type="number" value={brainstormForm.max_cost_usd} onChange={(e) => setBrainstormForm((current) => ({ ...current, max_cost_usd: e.target.value }))} fullWidth />
                            </Stack>
                            <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
                                <TextField label="Loop threshold" type="number" value={brainstormForm.max_repetition_score} onChange={(e) => setBrainstormForm((current) => ({ ...current, max_repetition_score: e.target.value }))} fullWidth />
                                <TextField label="Soft consensus similarity" type="number" value={brainstormForm.soft_consensus_min_similarity} onChange={(e) => setBrainstormForm((current) => ({ ...current, soft_consensus_min_similarity: e.target.value }))} fullWidth />
                            </Stack>
                            <TextField label="Conflict similarity ceiling" type="number" value={brainstormForm.conflict_pairwise_max_similarity} onChange={(e) => setBrainstormForm((current) => ({ ...current, conflict_pairwise_max_similarity: e.target.value }))} />
                            <FormControlLabel
                                control={<Switch checked={brainstormForm.stop_on_consensus} onChange={(_, checked) => setBrainstormForm((current) => ({ ...current, stop_on_consensus: checked }))} />}
                                label="Stop when consensus is reached"
                            />
                            <FormControlLabel
                                control={<Switch checked={brainstormForm.accept_soft_consensus} onChange={(_, checked) => setBrainstormForm((current) => ({ ...current, accept_soft_consensus: checked }))} />}
                                label="Accept soft consensus"
                            />
                            <FormControlLabel
                                control={<Switch checked={brainstormForm.escalate_on_no_consensus} onChange={(_, checked) => setBrainstormForm((current) => ({ ...current, escalate_on_no_consensus: checked }))} />}
                                label="Escalate if no consensus after the final round"
                            />
                            <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 2 }}>
                                <Typography variant="subtitle2">Guardrails</Typography>
                                <Typography variant="body2" color="text.secondary">
                                    The moderator will summarize each round automatically. The room stops on consensus, cost cap, round cap, or loop detection.
                                </Typography>
                            </Paper>
                            <Button
                                variant="contained"
                                disabled={!brainstormForm.topic.trim() || brainstormForm.participant_agent_ids.length < 2}
                                onClick={() =>
                                    brainstormMutation.mutate({
                                        project_id: projectId,
                                        task_id: brainstormForm.task_id || null,
                                        moderator_agent_id: brainstormForm.moderator_agent_id || null,
                                        topic: brainstormForm.topic,
                                        participant_agent_ids: brainstormForm.participant_agent_ids,
                                        mode: brainstormForm.mode,
                                        output_type: brainstormForm.output_type,
                                        max_rounds: Number(brainstormForm.max_rounds || 3),
                                        max_cost_usd: Number(brainstormForm.max_cost_usd || 10),
                                        max_repetition_score: Number(brainstormForm.max_repetition_score || 0.92),
                                        stop_conditions: {
                                            stop_on_consensus: brainstormForm.stop_on_consensus,
                                            accept_soft_consensus: brainstormForm.accept_soft_consensus,
                                            escalate_on_no_consensus: brainstormForm.escalate_on_no_consensus,
                                            soft_consensus_min_similarity: Number(brainstormForm.soft_consensus_min_similarity || 0.72),
                                            conflict_pairwise_max_similarity: Number(brainstormForm.conflict_pairwise_max_similarity || 0.38),
                                        },
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
                                    <Stack spacing={1.25}>
                                        <Box>
                                            <Typography variant="subtitle2">{brainstorm.topic}</Typography>
                                            <Typography variant="body2" color="text.secondary">{brainstorm.summary || brainstorm.final_recommendation || "Run pending or no summary yet."}</Typography>
                                        </Box>
                                        <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                                            <Chip label={humanizeKey(brainstorm.status)} size="small" />
                                            <Chip label={humanizeKey(brainstorm.mode)} size="small" variant="outlined" />
                                            <Chip label={humanizeKey(brainstorm.output_type)} size="small" variant="outlined" />
                                            <Chip label={`Round ${brainstorm.current_round}/${brainstorm.max_rounds}`} size="small" variant="outlined" />
                                            <Chip
                                                label={humanizeKey(brainstorm.consensus_status)}
                                                size="small"
                                                color={brainstorm.consensus_status === "consensus" || brainstorm.consensus_status === "soft_consensus" ? "success" : brainstorm.consensus_status === "conflict" || brainstorm.consensus_status === "loop_detected" ? "warning" : "default"}
                                            />
                                        </Stack>
                                        <Typography variant="caption" color="text.secondary">
                                            {brainstorm.participant_count} participants • updated {formatDateTime(brainstorm.updated_at)}
                                        </Typography>
                                        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
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
                        description="Branch policy, approval-gated GitHub writes, repo-specific routing, and review automation."
                    >
                        <Stack spacing={2}>
                            <TextField
                                label="Branch name template"
                                size="small"
                                fullWidth
                                value={resolvedGithubForm.branch_prefix}
                                onChange={(e) => setGithubForm((f) => ({ ...f, branch_prefix: e.target.value }))}
                                helperText="Placeholders: {task_id}, {slug} (from task title). Used when generating PR branches."
                            />
                            <FormControlLabel
                                control={(
                                    <Switch
                                        checked={resolvedGithubForm.enforce_branch_naming}
                                        onChange={(_, checked) => setGithubForm((f) => ({ ...f, enforce_branch_naming: checked }))}
                                    />
                                )}
                                label="Enforce branch naming convention on GitHub PR open events"
                            />
                            <FormControlLabel
                                control={(
                                    <Switch
                                        checked={resolvedGithubForm.auto_post_progress}
                                        onChange={(_, checked) => setGithubForm((f) => ({ ...f, auto_post_progress: checked }))}
                                    />
                                )}
                                label="Draft agent progress notes for approval when runs complete"
                            />
                            <FormControlLabel
                                control={(
                                    <Switch
                                        checked={resolvedGithubForm.auto_activate_review_on_pr_open}
                                        onChange={(_, checked) => setGithubForm((f) => ({ ...f, auto_activate_review_on_pr_open: checked }))}
                                    />
                                )}
                                label="Queue a Troop review run as soon as a GitHub PR opens"
                            />
                            <FormControlLabel
                                control={(
                                    <Switch
                                        checked={resolvedGithubForm.auto_review_on_pr_review}
                                        onChange={(_, checked) => setGithubForm((f) => ({ ...f, auto_review_on_pr_review: checked }))}
                                    />
                                )}
                                label="Queue a Troop review run when a GitHub PR review is submitted"
                            />
                            <FormControlLabel
                                control={(
                                    <Switch
                                        checked={resolvedGithubForm.close_issue_with_manager_summary}
                                        onChange={(_, checked) => setGithubForm((f) => ({ ...f, close_issue_with_manager_summary: checked }))}
                                    />
                                )}
                                label="Draft a manager-authored issue closure summary for approval on managed runs"
                            />
                            <Divider />
                            <Typography variant="subtitle2">Bidirectional sync</Typography>
                            <FormControlLabel
                                control={(
                                    <Switch
                                        checked={resolvedGithubForm.sync_labels_to_github}
                                        onChange={(_, checked) => setGithubForm((f) => ({ ...f, sync_labels_to_github: checked }))}
                                    />
                                )}
                                label="Sync internal labels back to GitHub issues"
                            />
                            <FormControlLabel
                                control={(
                                    <Switch
                                        checked={resolvedGithubForm.sync_assignees_to_github}
                                        onChange={(_, checked) => setGithubForm((f) => ({ ...f, sync_assignees_to_github: checked }))}
                                    />
                                )}
                                label="Sync internal assignee changes back to GitHub issues"
                            />
                            <FormControlLabel
                                control={(
                                    <Switch
                                        checked={resolvedGithubForm.sync_state_to_github}
                                        onChange={(_, checked) => setGithubForm((f) => ({ ...f, sync_state_to_github: checked }))}
                                    />
                                )}
                                label="Sync internal task completion state back to GitHub issue state"
                            />
                            <FormControlLabel
                                control={(
                                    <Switch
                                        checked={resolvedGithubForm.sync_milestone_to_github}
                                        onChange={(_, checked) => setGithubForm((f) => ({ ...f, sync_milestone_to_github: checked }))}
                                    />
                                )}
                                label="Sync `metadata.github_milestone_number` back to GitHub issue milestone"
                            />
                            <TextField
                                label="Repo agent pools JSON"
                                size="small"
                                fullWidth
                                multiline
                                minRows={8}
                                value={resolvedGithubForm.repo_agent_pools_json}
                                onChange={(e) => setGithubForm((f) => ({ ...f, repo_agent_pools_json: e.target.value }))}
                                helperText='Map repository id or "owner/name" to routing config. Example: {"org/repo":{"worker_agent_ids":["agent-1"],"default_assignee_agent_id":"agent-1","default_reviewer_agent_id":"agent-2","github_assignee_map":{"octocat":"agent-1"}}}'
                            />
                            <Button variant="contained" onClick={saveGithubIntegration} disabled={saveProjectSettingsMutation.isPending}>
                                Save GitHub settings
                            </Button>
                        </Stack>
                    </SectionCard>
                    <SectionCard
                        title="Sandbox & secret scoping (beta)"
                        description="Enforce sandbox and secret boundaries for agent tool execution."
                    >
                        <Stack spacing={2}>
                            <TextField
                                select
                                label="Sandbox execution policy"
                                size="small"
                                value={resolvedHitlForm.sandbox_mode}
                                onChange={(e) => setHitlForm((f) => ({ ...f, sandbox_mode: e.target.value }))}
                                fullWidth
                            >
                                <MenuItem value="allow_host_fallback">Allow host fallback when Docker is unavailable</MenuItem>
                                <MenuItem value="docker_required">Require Docker sandbox (block host fallback)</MenuItem>
                            </TextField>
                            <TextField
                                select
                                label="Secret scope posture"
                                size="small"
                                value={resolvedHitlForm.secret_scope}
                                onChange={(e) => setHitlForm((f) => ({ ...f, secret_scope: e.target.value }))}
                                fullWidth
                            >
                                <MenuItem value="project_default">Project default (env + provider keys)</MenuItem>
                                <MenuItem value="repo_scoped">Prefer repository-scoped tokens when available</MenuItem>
                                <MenuItem value="agent_scoped">Prefer per-agent secret slots (manual rotation)</MenuItem>
                                <MenuItem value="deny_external">Deny external network + GitHub tools</MenuItem>
                            </TextField>
                            <TextField
                                label="Sandbox / runner notes"
                                size="small"
                                multiline
                                minRows={2}
                                fullWidth
                                value={resolvedHitlForm.sandbox_note}
                                onChange={(e) => setHitlForm((f) => ({ ...f, sandbox_note: e.target.value }))}
                                placeholder="e.g. Dedicated worker queue, CPU seconds cap, egress deny list…"
                            />
                            <Button variant="outlined" onClick={saveHitlSettings} disabled={saveProjectSettingsMutation.isPending}>
                                Save HITL controls
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
                        <SectionCard title="Connected repositories" description="Repo-level indexing, schedule controls, file coverage, and failure reporting for searchable project knowledge.">
                            <Stack spacing={1.5}>
                                {repositoryIndexStatus.length === 0 && projectRepositories.length === 0 ? (
                                    <Typography variant="body2" color="text.secondary">
                                        No connected repositories yet. Link a GitHub repository on the GitHub tab to index code knowledge here.
                                    </Typography>
                                ) : (
                                    (repositoryIndexStatus.length > 0 ? repositoryIndexStatus : projectRepositories.map((repository) => ({
                                        repository_link_id: repository.id,
                                        github_repository_id: repository.github_repository_id,
                                        full_name: repository.full_name,
                                        default_branch: repository.default_branch,
                                        repository_url: repository.repository_url,
                                        index_settings: (repository.metadata.indexing as Record<string, unknown> | undefined) ?? {},
                                        indexed_files: 0,
                                        chunk_count: 0,
                                        searchable_documents: 0,
                                        last_indexed_at: null,
                                        latest_job: null,
                                        last_successful_job_id: null,
                                        pending_jobs: 0,
                                        running_jobs: 0,
                                        recent_files: [],
                                        recent_errors: [],
                                    }))).map((repository) => {
                                        const draft = repoIndexDrafts[repository.repository_link_id] ?? {
                                            scheduleLabel: String((repository.index_settings as Record<string, unknown>).schedule_label ?? ""),
                                            pathPrefixes: Array.isArray((repository.index_settings as Record<string, unknown>).path_prefixes)
                                                ? ((repository.index_settings as Record<string, unknown>).path_prefixes as string[]).join(", ")
                                                : "",
                                            autoEnabled: Boolean((repository.index_settings as Record<string, unknown>).auto_enabled),
                                        };
                                        return (
                                            <Paper key={repository.repository_link_id} sx={{ p: 2, borderRadius: 4 }}>
                                                <Stack direction={{ xs: "column", lg: "row" }} justifyContent="space-between" spacing={2}>
                                                    <Box sx={{ flex: 1 }}>
                                                        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                                                            <Typography variant="subtitle2">{repository.full_name}</Typography>
                                                            <Chip size="small" variant="outlined" label={repository.default_branch || "no branch"} />
                                                            <Chip size="small" color="info" variant="outlined" label={`${repository.indexed_files} files`} />
                                                            <Chip size="small" color="success" variant="outlined" label={`${repository.chunk_count} chunks`} />
                                                            {repository.latest_job ? (
                                                                <Chip size="small" color={repository.latest_job.status === "failed" ? "error" : repository.latest_job.status === "running" ? "info" : repository.latest_job.status === "pending" ? "warning" : "success"} label={`latest ${repository.latest_job.status}`} />
                                                            ) : null}
                                                        </Stack>
                                                        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.75 }}>
                                                            {repository.last_indexed_at ? `Last indexed ${formatDateTime(repository.last_indexed_at)}` : "Not indexed yet"}
                                                            {repository.repository_url ? ` • ${repository.repository_url}` : ""}
                                                        </Typography>
                                                        <Stack direction={{ xs: "column", md: "row" }} spacing={1.25} sx={{ mt: 1.25 }}>
                                                            <TextField
                                                                size="small"
                                                                label="Schedule label"
                                                                value={draft.scheduleLabel}
                                                                onChange={(event) => setRepoIndexDrafts((current) => ({
                                                                    ...current,
                                                                    [repository.repository_link_id]: { ...draft, scheduleLabel: event.target.value },
                                                                }))}
                                                                sx={{ minWidth: 180 }}
                                                                helperText="Example: every 6h / daily / before review"
                                                            />
                                                            <TextField
                                                                size="small"
                                                                label="Incremental paths"
                                                                value={draft.pathPrefixes}
                                                                onChange={(event) => setRepoIndexDrafts((current) => ({
                                                                    ...current,
                                                                    [repository.repository_link_id]: { ...draft, pathPrefixes: event.target.value },
                                                                }))}
                                                                fullWidth
                                                                helperText="Comma-separated path prefixes for focused reindex."
                                                            />
                                                        </Stack>
                                                        <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 1 }}>
                                                            <Switch
                                                                checked={draft.autoEnabled}
                                                                onChange={(_, checked) => setRepoIndexDrafts((current) => ({
                                                                    ...current,
                                                                    [repository.repository_link_id]: { ...draft, autoEnabled: checked },
                                                                }))}
                                                            />
                                                            <Typography variant="body2">Auto queue scheduled index for this repo</Typography>
                                                        </Stack>
                                                        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mt: 1.25 }}>
                                                            <Button
                                                                size="small"
                                                                variant="contained"
                                                                onClick={() => queueRepositoryIndexMutation.mutate({
                                                                    repositoryLinkId: repository.repository_link_id,
                                                                    mode: "full",
                                                                    pathPrefixes: [],
                                                                    scheduleLabel: draft.scheduleLabel || null,
                                                                    autoEnabled: draft.autoEnabled,
                                                                })}
                                                            >
                                                                Full index
                                                            </Button>
                                                            <Button
                                                                size="small"
                                                                variant="outlined"
                                                                onClick={() => queueRepositoryIndexMutation.mutate({
                                                                    repositoryLinkId: repository.repository_link_id,
                                                                    mode: "incremental",
                                                                    pathPrefixes: draft.pathPrefixes.split(",").map((item) => item.trim()).filter(Boolean),
                                                                    scheduleLabel: draft.scheduleLabel || null,
                                                                    autoEnabled: draft.autoEnabled,
                                                                })}
                                                            >
                                                                Incremental reindex
                                                            </Button>
                                                            <Button
                                                                size="small"
                                                                onClick={() => updateRepositoryMutation.mutate({
                                                                    repositoryLinkId: repository.repository_link_id,
                                                                    metadata: {
                                                                        indexing: {
                                                                            schedule_label: draft.scheduleLabel || null,
                                                                            path_prefixes: draft.pathPrefixes.split(",").map((item) => item.trim()).filter(Boolean),
                                                                            auto_enabled: draft.autoEnabled,
                                                                        },
                                                                    },
                                                                })}
                                                            >
                                                                Save schedule
                                                            </Button>
                                                        </Stack>
                                                    </Box>
                                                    <Stack spacing={1} sx={{ width: { xs: "100%", lg: 320 } }}>
                                                        <Typography variant="caption" color="text.secondary">Recent indexed files</Typography>
                                                        {repository.recent_files.length > 0 ? repository.recent_files.slice(0, 5).map((file) => (
                                                            <Paper key={file.document_id} variant="outlined" sx={{ p: 1, borderRadius: 2 }}>
                                                                <Typography variant="body2">{file.path}</Typography>
                                                                <Typography variant="caption" color="text.secondary">
                                                                    {file.branch} • {file.chunk_count} chunks • {file.status}
                                                                </Typography>
                                                            </Paper>
                                                        )) : (
                                                            <Typography variant="body2" color="text.secondary">No indexed files yet.</Typography>
                                                        )}
                                                        {repository.recent_errors.length > 0 ? (
                                                            <>
                                                                <Typography variant="caption" color="error">Recent failures</Typography>
                                                                {repository.recent_errors.map((error) => (
                                                                    <Alert key={error.job_id} severity="error">
                                                                        {error.error_text || "Unknown indexing failure"}
                                                                    </Alert>
                                                                ))}
                                                            </>
                                                        ) : null}
                                                    </Stack>
                                                </Stack>
                                            </Paper>
                                        );
                                    })
                                )}
                            </Stack>
                        </SectionCard>
                    </Stack>
                    <SectionCard title="Memory expiration rules" description="Control retention + approval gate for long-term memory writes.">
                        <Stack spacing={1.25}>
                            <Stack direction="row" alignItems="center" spacing={1}>
                                <Switch
                                    checked={resolvedMemorySettings.semantic_write_requires_approval}
                                    onChange={(_, checked) =>
                                        setMemorySettingsDraft((current) => ({
                                            ...(current ?? resolvedMemorySettings),
                                            semantic_write_requires_approval: checked,
                                        }))
                                    }
                                />
                                <Typography variant="body2">Require approval before long-term semantic memory writes</Typography>
                            </Stack>
                            <Stack direction="row" alignItems="center" spacing={1}>
                                <Switch
                                    checked={resolvedMemorySettings.deep_recall_mode}
                                    onChange={(_, checked) =>
                                        setMemorySettingsDraft((current) => ({
                                            ...(current ?? resolvedMemorySettings),
                                            deep_recall_mode: checked,
                                        }))
                                    }
                                />
                                <Typography variant="body2">Enable deep recall mode for episodic retrieval</Typography>
                            </Stack>
                            <TextField
                                label="Episodic retention days"
                                value={resolvedMemorySettings.episodic_retention_days}
                                onChange={(event) =>
                                    setMemorySettingsDraft((current) => ({
                                        ...(current ?? resolvedMemorySettings),
                                        episodic_retention_days: event.target.value,
                                    }))
                                }
                                helperText="Older episodic records are archived/expired by background jobs."
                            />
                            <Button
                                variant="outlined"
                                onClick={() =>
                                    memorySettingsMutation.mutate({
                                        semantic_write_requires_approval:
                                            resolvedMemorySettings.semantic_write_requires_approval,
                                        deep_recall_mode: resolvedMemorySettings.deep_recall_mode,
                                        episodic_retention_days: Number(
                                            resolvedMemorySettings.episodic_retention_days || 90
                                        ),
                                    })
                                }
                                disabled={memorySettingsMutation.isPending}
                            >
                                Save memory rules
                            </Button>
                        </Stack>
                    </SectionCard>
                    <SectionCard title="Ingestion jobs" description="Queue/worker visibility for repository indexing and document ingestion.">
                        <Stack spacing={1.25}>
                            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                                <Chip size="small" color="warning" label={`Pending ${memoryIngestCounts.pending}`} />
                                <Chip size="small" color="info" label={`Running ${memoryIngestCounts.running}`} />
                                <Chip size="small" color="success" label={`Completed ${memoryIngestCounts.completed}`} />
                                <Chip size="small" color="error" label={`Failed ${memoryIngestCounts.failed}`} />
                            </Stack>
                            {memoryIngestJobs.slice(0, 12).map((job) => (
                                <Paper key={job.id} sx={{ p: 1.5, borderRadius: 3 }}>
                                    <Stack direction={{ xs: "column", md: "row" }} justifyContent="space-between" spacing={1}>
                                        <Box>
                                            <Typography variant="body2">{job.job_type}</Typography>
                                            <Typography variant="caption" color="text.secondary">
                                                {formatDateTime(job.created_at)}
                                                {job.started_at ? ` • started ${formatDateTime(job.started_at)}` : ""}
                                                {job.finished_at ? ` • finished ${formatDateTime(job.finished_at)}` : ""}
                                            </Typography>
                                        </Box>
                                        <Chip size="small" label={job.status} color={job.status === "failed" ? "error" : job.status === "completed" ? "success" : job.status === "running" ? "info" : "warning"} />
                                    </Stack>
                                    {job.error_text ? (
                                        <Typography variant="caption" color="error" sx={{ display: "block", mt: 0.75, whiteSpace: "pre-wrap" }}>
                                            {job.error_text}
                                        </Typography>
                                    ) : null}
                                </Paper>
                            ))}
                            {memoryIngestJobs.length === 0 && (
                                <Typography variant="body2" color="text.secondary">
                                    No ingestion jobs yet.
                                </Typography>
                            )}
                        </Stack>
                    </SectionCard>
                    <SectionCard title="Semantic search" description="Query indexed chunks and optional decision recall (minimum three characters).">
                        <TextField
                            label="Search knowledge"
                            value={knowledgeQuery}
                            onChange={(event) => setKnowledgeQuery(event.target.value)}
                            helperText="Matches ranked by relevance; each row is a chunk used during agent runs."
                            fullWidth
                        />
                        <Stack direction="row" alignItems="center" spacing={1} sx={{ mt: 1 }}>
                            <Switch checked={includeDecisionRecall} onChange={(_, checked) => setIncludeDecisionRecall(checked)} />
                            <Typography variant="body2">Decision recall: include project decisions ("what did we decide about X?")</Typography>
                        </Stack>
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
                    <SectionCard title="Semantic memory explorer" description="Per-project semantic memory entries created from runs, documents, and decisions.">
                        <Stack spacing={1.25}>
                            {semanticEntries.length > 0 ? semanticEntries.map((entry) => (
                                <Paper key={entry.id} sx={{ p: 1.5, borderRadius: 3 }}>
                                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap alignItems="center">
                                        <Typography variant="body2">{entry.title}</Typography>
                                        <Chip size="small" variant="outlined" label={entry.entry_type} />
                                        <Chip size="small" variant="outlined" label={entry.namespace} />
                                    </Stack>
                                    <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: "pre-wrap", mt: 0.75, display: "block" }}>
                                        {entry.body.slice(0, 400)}
                                    </Typography>
                                </Paper>
                            )) : (
                                <Typography variant="body2" color="text.secondary">No semantic memory entries yet.</Typography>
                            )}
                        </Stack>
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
                                                <Button size="small" variant="outlined" color="error" onClick={() => memoryApprovalMutation.mutate({ approvalId: approval.id, status: "rejected", reason: "Rejected from memory panel" })}>
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
                        <TextField
                            select
                            SelectProps={{ multiple: true }}
                            size="small"
                            label="Dependencies"
                            value={currentDagDependencySelection}
                            onChange={(event) => {
                                const nextValue = event.target.value;
                                if (!dagTask) return;
                                setDagDependencyDrafts((current) => ({
                                    ...current,
                                    [dagTask.id]: Array.isArray(nextValue)
                                        ? nextValue
                                        : String(nextValue).split(",").filter(Boolean),
                                }));
                            }}
                            helperText="Selected tasks must finish before this one can run."
                            fullWidth
                        >
                            {tasks
                                .filter((candidate) => candidate.id !== dagTask.id && !dagDescendantIds.has(candidate.id))
                                .map((candidate) => (
                                    <MenuItem key={candidate.id} value={candidate.id}>
                                        {candidate.title} · {humanizeKey(candidate.status)}
                                    </MenuItem>
                                ))}
                        </TextField>
                        <Button
                            variant="outlined"
                            disabled={updateDagTaskMutation.isPending}
                            onClick={() => updateDagTaskMutation.mutate({
                                taskId: dagTask.id,
                                payload: { dependency_ids: currentDagDependencySelection },
                            })}
                        >
                            Save dependencies
                        </Button>
                        {dagTaskDependents.length > 0 ? (
                            <Stack spacing={0.5}>
                                <Typography variant="caption" color="text.secondary">Downstream tasks</Typography>
                                <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                                    {dagTaskDependents.map((dependent) => (
                                        <Chip key={dependent.id} label={dependent.title} size="small" variant="outlined" />
                                    ))}
                                </Stack>
                            </Stack>
                        ) : null}
                        {dagBlockedSuggestion ? (
                            <Alert severity="warning">
                                Suggested handoff: {dagBlockedSuggestion.agentName} via {humanizeKey(dagBlockedSuggestion.via)}.
                                {dagBlockedSuggestion.reason ? ` ${dagBlockedSuggestion.reason}` : ""}
                            </Alert>
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
                                        setMergeTaskId(dagTask.id);
                                        setMergeNotes(`Synthesize the best branch outputs for "${dagTask.title}". Resolve conflicts, preserve accepted evidence, and promote one final artifact set.`);
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

            <Dialog open={Boolean(mergeTaskId)} onClose={() => setMergeTaskId(null)} fullWidth maxWidth="md">
                <DialogTitle>Merge branch outputs</DialogTitle>
                <DialogContent>
                    <Stack spacing={2} sx={{ mt: 1 }}>
                        <Typography variant="body2" color="text.secondary">
                            Review completed branch outputs, flag conflicts, then queue one synthesis run on the parent task.
                        </Typography>
                        {mergePreview ? (
                            <>
                                <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 3 }}>
                                    <Typography variant="subtitle2">{String((mergePreview.parent as { title?: string } | undefined)?.title || "Parent task")}</Typography>
                                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mt: 1 }}>
                                        <Chip size="small" variant="outlined" label={`${Number(mergePreview.completed_branch_count || 0)} completed branches`} />
                                        <Chip size="small" variant="outlined" label={`${Number(mergePreview.distinct_agents_on_completed || 0)} contributing agents`} />
                                        <Chip
                                            size="small"
                                            color={mergePreview.needs_merge_agent ? "warning" : "success"}
                                            label={mergePreview.needs_merge_agent ? "conflict review needed" : "low conflict"}
                                        />
                                    </Stack>
                                </Paper>
                                <Stack spacing={1}>
                                    {Array.isArray(mergePreview.branches) ? mergePreview.branches.map((branch) => {
                                        const branchRow = branch as { id: string; title?: string; status?: string; assigned_agent_id?: string | null; result_summary?: string | null };
                                        return (
                                            <Paper key={branchRow.id} sx={{ p: 1.5, borderRadius: 3 }}>
                                                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap alignItems="center">
                                                    <Typography variant="subtitle2">{branchRow.title || "Branch task"}</Typography>
                                                    <Chip size="small" variant="outlined" label={branchRow.status || "unknown"} />
                                                    {branchRow.assigned_agent_id ? <Chip size="small" variant="outlined" label={branchRow.assigned_agent_id.slice(0, 8)} /> : null}
                                                </Stack>
                                                <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.75, whiteSpace: "pre-wrap" }}>
                                                    {branchRow.result_summary || "No summary captured yet."}
                                                </Typography>
                                            </Paper>
                                        );
                                    }) : null}
                                </Stack>
                            </>
                        ) : (
                            <LinearProgress />
                        )}
                        <Alert severity="info">
                            Checklist: compare branch evidence, reconcile conflicts, preserve accepted artifacts, and name the promoted final output in notes.
                        </Alert>
                        <TextField
                            label="Synthesis notes"
                            multiline
                            minRows={5}
                            value={mergeNotes}
                            onChange={(event) => setMergeNotes(event.target.value)}
                            helperText="These notes become merge context for the synthesis run."
                            fullWidth
                        />
                    </Stack>
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setMergeTaskId(null)}>Cancel</Button>
                    <Button
                        variant="contained"
                        disabled={!mergeTaskId || mergeResolutionMutation.isPending}
                        onClick={() => {
                            if (!mergeTaskId) return;
                            mergeResolutionMutation.mutate({ parentTaskId: mergeTaskId, notes: mergeNotes.trim() || "Merge branches from project DAG." });
                        }}
                    >
                        Queue merge resolution run
                    </Button>
                </DialogActions>
            </Dialog>

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
