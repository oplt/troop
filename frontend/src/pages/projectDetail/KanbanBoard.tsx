import { useCallback, useMemo, useState, memo, type DragEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
    Avatar, Box, Button, Chip, CircularProgress, IconButton, LinearProgress, MenuItem, Paper, Stack, TextField, Tooltip, Typography,
    useMediaQuery,
} from "@mui/material";
import { alpha, useTheme } from "@mui/material/styles";
import {
    Check as CheckSimpleIcon,
    MoreVert as MoreIcon,
    PlayArrow as RunIcon,
} from "@mui/icons-material";
import { useNavigate } from "react-router-dom";
import {
    assignOrchestrationTask, updateOrchestrationTask,
    type OrchestrationTask, type TaskRun,
} from "../../api/orchestration";
import { ApiRequestError } from "../../api/client";
import { useSnackbar } from "../../app/snackbarContext";
import { queryKeys } from "../../config/queryKeys";
import { extractApiErrorMessage } from "../../utils/apiErrors";
import { invalidateProjectMutation } from "../../features/orchestration/project/mutations";
import { StatusChip } from "../../components/ui/StatusChip";
import { FilterToolbar } from "../../components/ui/FilterToolbar";
import { MAIN_KANBAN_COLUMNS } from "./kanbanConstants";
import { KanbanTaskDrawer } from "./KanbanTaskDrawer";
import {
    type ExecutionMode,
    EXCEPTION_TASK_COLUMNS,
    TASK_TRANSITION_MAP,
} from "./projectDetailShared";
import { humanizeKey } from "../../utils/formatters";

export const KanbanBoard = memo(function KanbanBoard({
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
    const theme = useTheme();
    const listFirstMobile = useMediaQuery(theme.breakpoints.down("md"));
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();
    const navigate = useNavigate();
    const [expandedTask, setExpandedTask] = useState<string | null>(null);
    const [statusFilter, setStatusFilter] = useState<string>("all");
    const [draggingTaskId, setDraggingTaskId] = useState<string | null>(null);
    const [dropHoverColumn, setDropHoverColumn] = useState<string | null>(null);
    const [dropHoverAgentId, setDropHoverAgentId] = useState<string | null>(null);

    const clearKanbanDragState = useCallback(() => {
        setDraggingTaskId(null);
        setDropHoverColumn(null);
        setDropHoverAgentId(null);
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
        onSuccess: async (_, variables) => {
            await invalidateProjectMutation(queryClient, projectId, "tasks");
            await queryClient.invalidateQueries({
                queryKey: queryKeys.orchestration.projectTaskBlockers(projectId, variables.taskId),
            });
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.projectTaskExecution(projectId, expandedTask || undefined) });
        },
        onError: (error) => {
            const detail = error instanceof ApiRequestError && typeof error.detail === "object" && error.detail !== null
                ? error.detail as { approval_id?: unknown; message?: unknown }
                : null;
            if (typeof detail?.approval_id === "string") {
                showToast({
                    message: `${String(detail.message || "This task change requires approval.")} Open Audit & approvals to review it.`,
                    severity: "warning",
                });
                navigate("/approvals");
                return;
            }
            showToast({ message: extractApiErrorMessage(error, "Task update failed."), severity: "error" });
        },
    });

    const assignmentMutation = useMutation({
        mutationFn: ({ taskId, agentId }: { taskId: string; agentId: string | null }) =>
            assignOrchestrationTask(projectId, taskId, agentId, "drag_drop"),
        onSuccess: async (_, variables) => {
            await invalidateProjectMutation(queryClient, projectId, "tasks", "agents");
            await queryClient.invalidateQueries({
                queryKey: queryKeys.orchestration.projectTaskExecution(projectId, variables.taskId),
            });
            showToast({ message: variables.agentId ? "Task assigned to agent." : "Task unassigned.", severity: "success" });
        },
        onError: (error) => {
            const detail = error instanceof ApiRequestError && typeof error.detail === "object" && error.detail !== null
                ? error.detail as { approval_id?: unknown; message?: unknown }
                : null;
            if (typeof detail?.approval_id === "string") {
                showToast({
                    message: `${String(detail.message || "This assignment requires approval.")} Open Audit & approvals to review it.`,
                    severity: "warning",
                });
                navigate("/approvals");
                return;
            }
            showToast({ message: extractApiErrorMessage(error, "Task assignment failed."), severity: "error" });
        },
    });

    const handleAgentDragOver = useCallback(
        (event: DragEvent<HTMLDivElement>, agentId: string) => {
            if (!draggingTaskId || assignmentMutation.isPending) return;
            event.preventDefault();
            event.dataTransfer.dropEffect = "copy";
            setDropHoverColumn(null);
            setDropHoverAgentId(agentId);
        },
        [assignmentMutation.isPending, draggingTaskId],
    );

    const handleAgentDrop = useCallback(
        (event: DragEvent<HTMLDivElement>, agentId: string) => {
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
            const task = tasks.find((item) => item.id === taskId);
            if (!taskId || !task || task.assigned_agent_id === agentId || assignmentMutation.isPending) {
                clearKanbanDragState();
                return;
            }
            assignmentMutation.mutate({ taskId, agentId });
            clearKanbanDragState();
        },
        [assignmentMutation, clearKanbanDragState, tasks],
    );

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

    const tasksByStatus = useMemo(() => {
        const map: Record<string, OrchestrationTask[]> = {};
        for (const col of MAIN_KANBAN_COLUMNS) map[col.status] = [];
        for (const task of tasks) {
            const col = MAIN_KANBAN_COLUMNS.find((c) => c.statuses.includes(task.status));
            if (col) map[col.status].push(task);
        }
        return map;
    }, [tasks]);

    const exceptionTasks = useMemo(
        () => EXCEPTION_TASK_COLUMNS.map((column) => ({ ...column, tasks: tasks.filter((task) => task.status === column.status) })),
        [tasks],
    );

    const listTasks = useMemo(() => {
        if (statusFilter === "all") return tasks;
        return tasks.filter((task) => task.status === statusFilter);
    }, [statusFilter, tasks]);

    const statusOptions = useMemo(() => {
        const values = new Set(tasks.map((task) => String(task.status)));
        return ["all", ...Array.from(values)];
    }, [tasks]);

    return (
        <Stack spacing={2}>
            <Paper
                variant="outlined"
                sx={(theme) => ({
                    p: 2,
                    borderRadius: 1,
                    backgroundColor: theme.palette.grey[50],
                    borderColor: theme.palette.divider,
                })}
            >
                <Stack
                    direction={{ xs: "column", md: "row" }}
                    spacing={1.5}
                    alignItems={{ xs: "stretch", md: "center" }}
                    justifyContent="space-between"
                >
                    <Box>
                        <Typography variant="h6" sx={{ fontWeight: 500 }}>
                            {listFirstMobile ? "Task list" : "Task flow"}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                            {listFirstMobile
                                ? "Tap a task to open details. Kanban drag-and-drop is available on larger screens."
                                : "Move work through five lanes. Failed and blocked tasks stay in exceptions."}
                        </Typography>
                    </Box>

                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                        <Chip size="small" label={`${tasks.length} total`} />
                        <Chip
                            size="small"
                            color="info"
                            variant="outlined"
                            label={`${tasksByStatus.in_progress?.length ?? 0} running`}
                        />
                        <Chip size="small" color="warning" variant="outlined" label={`${tasks.filter((task) => task.status === "blocked").length} blocked`} />
                        <Chip
                            size="small"
                            color="success"
                            variant="outlined"
                            label={`${tasksByStatus.completed?.length ?? 0} done`}
                        />
                        {exceptionTasks.some((group) => group.tasks.length > 0) ? (
                            <Chip
                                size="small"
                                color="error"
                                variant="outlined"
                                label={`${exceptionTasks.reduce((sum, group) => sum + group.tasks.length, 0)} exceptions`}
                            />
                        ) : null}
                    </Stack>
                </Stack>
            </Paper>

            {listFirstMobile ? (
                <Stack spacing={1.5}>
                    <FilterToolbar>
                        <TextField
                            select
                            size="small"
                            label="Status"
                            value={statusFilter}
                            onChange={(event) => setStatusFilter(event.target.value)}
                            sx={{ minWidth: 160 }}
                        >
                            {statusOptions.map((status) => (
                                <MenuItem key={status} value={status}>
                                    {status === "all" ? "All statuses" : humanizeKey(status)}
                                </MenuItem>
                            ))}
                        </TextField>
                    </FilterToolbar>
                    {listTasks.length === 0 ? (
                        <Typography variant="body2" color="text.secondary">
                            No tasks match this filter.
                        </Typography>
                    ) : (
                        listTasks.map((task) => {
                            const agent = allAgents.find((a) => a.id === task.assigned_agent_id);
                            const lastRun = lastRunByTaskId[task.id];
                            return (
                                <Paper
                                    key={task.id}
                                    variant="outlined"
                                    sx={{ p: 1.5, borderRadius: 1, cursor: "pointer" }}
                                    onClick={() => setExpandedTask(task.id)}
                                >
                                    <Stack spacing={1}>
                                        <Stack direction="row" justifyContent="space-between" gap={1} alignItems="flex-start">
                                            <Box sx={{ minWidth: 0 }}>
                                                <Typography variant="subtitle2">{task.title}</Typography>
                                                <Typography variant="caption" color="text.secondary">
                                                    {agent?.name ?? "Unassigned"}
                                                </Typography>
                                            </Box>
                                            <StatusChip status={String(task.status)} kind="task" size="small" />
                                        </Stack>
                                        {lastRun ? (
                                            <StatusChip
                                                status={lastRun.status}
                                                kind="run"
                                                size="small"
                                                showIcon={false}
                                                celebrate={lastRun.status === "completed"}
                                            />
                                        ) : null}
                                    </Stack>
                                </Paper>
                            );
                        })
                    )}
                </Stack>
            ) : (
            <>
            <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 1 }}>
                <Stack spacing={1}>
                    <Box>
                        <Typography variant="subtitle2">Assign from the board</Typography>
                        <Typography variant="caption" color="text.secondary">
                            Drag any task card onto an agent to change ownership. Approval policy still applies to the assignment.
                        </Typography>
                    </Box>
                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                        {allAgents.length === 0 ? (
                            <Typography variant="caption" color="text.secondary">Add project agents to enable drag-and-drop assignment.</Typography>
                        ) : allAgents.map((agent) => {
                            const assignedCount = tasks.filter((task) => task.assigned_agent_id === agent.id).length;
                            const active = dropHoverAgentId === agent.id;
                            return (
                                <Paper
                                    key={agent.id}
                                    variant="outlined"
                                    onDragOver={(event) => handleAgentDragOver(event, agent.id)}
                                    onDragLeave={() => setDropHoverAgentId(null)}
                                    onDrop={(event) => handleAgentDrop(event, agent.id)}
                                    sx={(theme) => ({
                                        minWidth: 150,
                                        p: 1,
                                        borderRadius: 1,
                                        borderColor: active ? theme.palette.primary.main : theme.palette.divider,
                                        bgcolor: active ? "action.selected" : "background.paper",
                                        transition: theme.transitions.create(["border-color", "background-color"]),
                                    })}
                                >
                                    <Stack direction="row" spacing={1} alignItems="center">
                                        <Avatar sx={{ width: 28, height: 28, fontSize: 12 }}>{agent.name.slice(0, 1).toUpperCase()}</Avatar>
                                        <Box sx={{ minWidth: 0 }}>
                                            <Typography variant="body2" noWrap>{agent.name}</Typography>
                                            <Typography variant="caption" color="text.secondary">{assignedCount} assigned</Typography>
                                        </Box>
                                    </Stack>
                                </Paper>
                            );
                        })}
                    </Stack>
                </Stack>
            </Paper>



            <Box
                sx={{
                    display: "grid",
                    gridAutoFlow: "column",
                    gridAutoColumns: {
                        xs: "minmax(260px, 82vw)",
                        sm: "minmax(280px, 36vw)",
                        lg: "minmax(285px, 1fr)",
                    },
                    gap: 1.5,
                    overflowX: "auto",
                    pb: 1,
                    minHeight: 560,
                }}
            >
                {MAIN_KANBAN_COLUMNS.map((col) => {
                    const columnTasks = tasksByStatus[col.status] ?? [];
                    const isDropTarget = dropHoverColumn === col.status && Boolean(draggingTaskId);

                    return (
                        <Paper
                            key={col.status}
                            variant="outlined"
                            onDragOverCapture={(event) => handleKanbanColumnDragOverCapture(event, col.status)}
                            onDragLeave={() => setDropHoverColumn(null)}
                            onDrop={(event) => handleKanbanColumnDrop(event, col.status)}
                            sx={(theme) => ({
                                display: "flex",
                                flexDirection: "column",
                                minHeight: 540,
                                maxHeight: "calc(100vh - 260px)",
                                borderRadius: 1,
                                overflow: "hidden",
                                borderColor: isDropTarget
                                    ? theme.palette.primary.main
                                    : theme.palette.divider,
                                backgroundColor: theme.palette.background.paper,
                                boxShadow: "none",
                                transition: theme.transitions.create(["border-color", "background-color"], {
                                    duration: 330,
                                }),
                            })}
                        >
                            <Box
                                sx={(theme) => ({
                                    position: "sticky",
                                    top: 0,
                                    zIndex: 1,
                                    p: 1.25,
                                    borderBottom: `1px solid ${theme.palette.divider}`,
                                    backgroundColor: alpha(theme.palette.background.paper, 0.96),
                                    backdropFilter: "blur(10px)",
                                })}
                            >
                                <Stack direction="row" alignItems="center" justifyContent="space-between" spacing={1}>
                                    <Stack direction="row" spacing={0.75} alignItems="center">
                                        <Chip
                                            label={col.label}
                                            color={col.color}
                                            size="small"
                                            sx={{
                                                fontWeight: 500,
                                                borderRadius: 1.5,
                                                "& .MuiChip-label": { px: 1 },
                                            }}
                                        />
                                        <Typography variant="caption" color="text.secondary">
                                            {columnTasks.length}
                                        </Typography>
                                    </Stack>

                                    {taskUpdateMutation.isPending ? (
                                        <CircularProgress size={14} />
                                    ) : null}
                                </Stack>
                            </Box>

                            <Stack
                                spacing={1}
                                sx={{
                                    p: 1,
                                    overflowY: "auto",
                                    flex: 1,
                                }}
                            >
                                {columnTasks.length === 0 ? (
                                    <Box
                                        sx={(theme) => ({
                                            minHeight: 120,
                                            borderRadius: 1,
                                            border: `1px dashed ${alpha(theme.palette.text.secondary, 0.24)}`,
                                            display: "grid",
                                            placeItems: "center",
                                            color: "text.secondary",
                                            fontSize: 12,
                                        })}
                                    >
                                        Drop task here
                                    </Box>
                                ) : null}

                                {columnTasks.map((task) => {
                                    const agent = allAgents.find((a) => a.id === task.assigned_agent_id);
                                    const lastRun = lastRunByTaskId[task.id];
                                    const priority = String(task.priority ?? "normal");
                                    const isSelected = selectedTaskId === task.id;
                                    const isUpdating =
                                        taskUpdateMutation.isPending &&
                                        taskUpdateMutation.variables?.taskId === task.id;

                                    const priorityColor =
                                        priority === "urgent" || priority === "high"
                                            ? "error"
                                            : priority === "normal"
                                                ? "info"
                                                : "default";

                                    return (
                                        <Paper
                                            key={task.id}
                                            draggable={!isUpdating}
                                            onDragStart={(event) => {
                                                setDraggingTaskId(task.id);
                                                event.dataTransfer.effectAllowed = "move";
                                                event.dataTransfer.setData(
                                                    "application/json",
                                                    JSON.stringify({ taskId: task.id }),
                                                );
                                            }}
                                            onDragEnd={clearKanbanDragState}
                                            variant="outlined"
                                            sx={(theme) => ({
                                                p: 1.25,
                                                borderRadius: 1,
                                                cursor: isUpdating ? "wait" : "grab",
                                                border: "2px solid",
                                                borderColor: isSelected
                                                    ? theme.palette.primary.main
                                                    : theme.palette.divider,
                                                backgroundColor: theme.palette.background.paper,
                                                boxShadow: "none",
                                                transition: theme.transitions.create(
                                                    ["border-color", "background-color"],
                                                    { duration: 330 },
                                                ),
                                                "&:hover": {
                                                    backgroundColor: theme.palette.grey[50],
                                                },
                                            })}
                                        >
                                            <Stack spacing={1}>
                                                <Stack direction="row" spacing={1} alignItems="flex-start">
                                                    <Avatar
                                                        sx={(theme) => ({
                                                            width: 28,
                                                            height: 28,
                                                            fontSize: 12,
                                                            fontWeight: 500,
                                                            bgcolor: agent
                                                                ? alpha(theme.palette.primary.main, 0.16)
                                                                : alpha(theme.palette.text.secondary, 0.12),
                                                            color: agent
                                                                ? theme.palette.primary.main
                                                                : theme.palette.text.secondary,
                                                        })}
                                                    >
                                                        {(agent?.name ?? "U").slice(0, 1).toUpperCase()}
                                                    </Avatar>

                                                    <Box sx={{ minWidth: 0, flex: 1 }}>
                                                        <Typography
                                                            variant="subtitle2"
                                                            sx={{
                                                                fontWeight: 500,
                                                                lineHeight: 1.25,
                                                                overflow: "hidden",
                                                                textOverflow: "ellipsis",
                                                                display: "-webkit-box",
                                                                WebkitLineClamp: 2,
                                                                WebkitBoxOrient: "vertical",
                                                            }}
                                                        >
                                                            {task.title}
                                                        </Typography>

                                                        <Typography
                                                            variant="caption"
                                                            color="text.secondary"
                                                            sx={{
                                                                display: "block",
                                                                mt: 0.25,
                                                                overflow: "hidden",
                                                                textOverflow: "ellipsis",
                                                                whiteSpace: "nowrap",
                                                            }}
                                                        >
                                                            {agent?.name ?? "Unassigned"}
                                                        </Typography>
                                                    </Box>

                                                    <Tooltip title="Task actions">
                                                        <IconButton size="small" onClick={(event) => event.stopPropagation()}>
                                                            <MoreIcon fontSize="inherit" />
                                                        </IconButton>
                                                    </Tooltip>
                                                </Stack>

                                                <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                                                    <Chip
                                                        size="small"
                                                        color={priorityColor}
                                                        variant="outlined"
                                                        label={priority}
                                                        sx={{ height: 22, fontSize: 11 }}
                                                    />
                                                    {lastRun ? (
                                                        <StatusChip
                                                            status={lastRun.status}
                                                            kind="run"
                                                            size="small"
                                                            showIcon={false}
                                                        />
                                                    ) : null}
                                                </Stack>

                                                {lastRun?.status === "running" || lastRun?.status === "queued" ? (
                                                    <LinearProgress />
                                                ) : null}

                                                <Stack
                                                    direction="row"
                                                    spacing={0.5}
                                                    alignItems="center"
                                                    justifyContent="space-between"
                                                    sx={(theme) => ({
                                                        pt: 0.75,
                                                        borderTop: `1px solid ${theme.palette.divider}`,
                                                    })}
                                                >
                                                    <Stack direction="row" spacing={0.5}>
                                                        <Tooltip title="Start task run">
                                                            <span>
                                                                <IconButton
                                                                    size="small"
                                                                    disabled={isRunPending}
                                                                    onClick={(event) => {
                                                                        event.stopPropagation();
                                                                        onRunTask(
                                                                            task.id,
                                                                            taskRunModes[task.id] ?? "single_agent",
                                                                            taskPrModes[task.id] ?? false,
                                                                        );
                                                                    }}
                                                                >
                                                                    <RunIcon fontSize="inherit" />
                                                                </IconButton>
                                                            </span>
                                                        </Tooltip>

                                                        <Tooltip title="Run acceptance check">
                                                            <IconButton
                                                                size="small"
                                                                onClick={(event) => {
                                                                    event.stopPropagation();
                                                                    onAcceptanceCheck(task.id);
                                                                }}
                                                            >
                                                                <CheckSimpleIcon fontSize="inherit" />
                                                            </IconButton>
                                                        </Tooltip>
                                                    </Stack>

                                                    <Button
                                                        size="small"
                                                        variant="contained"
                                                        onClick={(event) => {
                                                            event.stopPropagation();
                                                            setExpandedTask(task.id);
                                                        }}
                                                        sx={{ minWidth: 0 }}
                                                    >
                                                        Open
                                                    </Button>
                                                </Stack>
                                            </Stack>
                                        </Paper>
                                    );
                                })}
                            </Stack>
                        </Paper>
                    );
                })}
            </Box>

            </>
            )}

            <KanbanTaskDrawer
                projectId={projectId}
                tasks={tasks}
                allAgents={allAgents}
                lastRunByTaskId={lastRunByTaskId}
                expandedTask={expandedTask}
                setExpandedTask={setExpandedTask}
                taskRunModes={taskRunModes}
                taskPrModes={taskPrModes}
                onModeChange={onModeChange}
                onPrModeChange={onPrModeChange}
                onRunTask={onRunTask}
                onAcceptanceCheck={onAcceptanceCheck}
                isRunPending={isRunPending}
            />
        </Stack>
    );
});

