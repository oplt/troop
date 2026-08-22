import { useMemo, useState } from "react";
import { Link as RouterLink } from "react-router-dom";
import { useInfiniteQuery } from "@tanstack/react-query";
import {
    Box,
    Button,
    CircularProgress,
    Chip,
    MenuItem,
    Stack,
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableRow,
    TextField,
    Typography,
} from "@mui/material";
import {
    listMyTasksPage,
    type MyTaskListItem,
} from "../api/orchestration";
import type { CursorToken } from "../api/pagination";
import { PageShell } from "../components/ui/PageShell";
import { PageHeader } from "../components/ui/PageHeader";
import { EmptyState } from "../components/ui/EmptyState";
import { StatusChip } from "../components/ui/StatusChip";
import { FilterToolbar } from "../components/ui/FilterToolbar";
import { InspectorDrawer } from "../components/ui/InspectorDrawer";
import { formatDate, formatDateTime, humanizeKey } from "../utils/formatters";
import { Assignment as TasksIcon } from "@mui/icons-material";

type TaskRow = MyTaskListItem;

const CLOSED = new Set(["completed", "archived", "cancelled"]);

function displayStatus(status: string): string {
    if (status === "synced_to_github") return "completed";
    return status;
}

export default function MyTasksPage() {
    const [projectFilter, setProjectFilter] = useState("");
    const [statusFilter, setStatusFilter] = useState("all");
    const [selectedTask, setSelectedTask] = useState<TaskRow | null>(null);
    const taskQuery = useInfiniteQuery({
        queryKey: ["orchestration", "my-tasks"],
        queryFn: ({ pageParam }) => listMyTasksPage({ limit: 50, cursor: pageParam }),
        initialPageParam: null as CursorToken | null,
        getNextPageParam: (page) => page.next_cursor ?? undefined,
    });

    const rows = useMemo(() => {
        const out: TaskRow[] = (taskQuery.data?.pages ?? []).flatMap((page) => page.items).map((task) => ({
            ...task,
            status: displayStatus(String(task.status || "")),
        })).filter((task) => !CLOSED.has(task.status));
        out.sort((a, b) => String(b.updated_at || "").localeCompare(String(a.updated_at || "")));
        return out;
    }, [taskQuery.data]);

    const projects = useMemo(() => {
        const byId = new Map<string, string>();
        rows.forEach((task) => byId.set(task.project_id, task.project_name));
        return Array.from(byId, ([id, name]) => ({ id, name })).sort((a, b) => a.name.localeCompare(b.name));
    }, [rows]);

    const filteredRows = useMemo(() => {
        return rows.filter((task) => {
            if (projectFilter && task.project_id !== projectFilter) return false;
            if (statusFilter !== "all" && displayStatus(String(task.status)) !== statusFilter) return false;
            return true;
        });
    }, [rows, projectFilter, statusFilter]);

    const statusOptions = useMemo(() => {
        const set = new Set(rows.map((task) => displayStatus(String(task.status))));
        return Array.from(set).sort();
    }, [rows]);

    const loading = taskQuery.isLoading;

    return (
        <PageShell variant="browse">
            <PageHeader
                title="My tasks"
                description="Personal open work across projects. Same status chips as the project board."
                actions={
                    <Button component={RouterLink} to="/projects" variant="outlined">
                        Browse projects
                    </Button>
                }
            />

            <FilterToolbar>
                <TextField
                    select
                    size="small"
                    label="Project"
                    value={projectFilter}
                    onChange={(e) => setProjectFilter(e.target.value)}
                    sx={{ minWidth: 200 }}
                >
                    <MenuItem value="">All projects</MenuItem>
                    {projects.map((project) => (
                        <MenuItem key={project.id} value={project.id}>
                            {project.name}
                        </MenuItem>
                    ))}
                </TextField>
                <TextField
                    select
                    size="small"
                    label="Status"
                    value={statusFilter}
                    onChange={(e) => setStatusFilter(e.target.value)}
                    sx={{ minWidth: 160 }}
                >
                    <MenuItem value="all">All open</MenuItem>
                    {statusOptions.map((status) => (
                        <MenuItem key={status} value={status}>
                            {status}
                        </MenuItem>
                    ))}
                </TextField>
            </FilterToolbar>

            {loading ? (
                <Stack alignItems="center" sx={{ py: 6 }} role="status" aria-live="polite">
                    <CircularProgress />
                </Stack>
            ) : filteredRows.length === 0 ? (
                <EmptyState
                    icon={<TasksIcon />}
                    title={rows.length === 0 ? "No open tasks" : "No matching tasks"}
                    description={
                        rows.length === 0
                            ? "When projects assign work to you, it shows up here."
                            : "Clear filters or browse projects for more work."
                    }
                    action={
                        <Button component={RouterLink} to="/projects" variant="contained">
                            Browse projects
                        </Button>
                    }
                />
            ) : (
                <Box sx={{ borderTop: "1px solid", borderColor: "divider" }}>
                    <Table size="small">
                        <TableHead>
                            <TableRow>
                                <TableCell>Task</TableCell>
                                <TableCell>Project</TableCell>
                                <TableCell>Status</TableCell>
                                <TableCell>Assignee</TableCell>
                            </TableRow>
                        </TableHead>
                        <TableBody>
                            {filteredRows.map((task) => (
                                <TableRow key={task.id} hover>
                                    <TableCell>
                                        <Button
                                            variant="text"
                                            color="inherit"
                                            onClick={() => setSelectedTask(task)}
                                            sx={{ justifyContent: "flex-start", px: 0, textAlign: "left" }}
                                        >
                                            {task.title}
                                        </Button>
                                    </TableCell>
                                    <TableCell>{task.project_name}</TableCell>
                                    <TableCell>
                                        <StatusChip status={displayStatus(String(task.status))} kind="task" />
                                    </TableCell>
                                    <TableCell>
                                        {task.assigned_agent_id || "Unassigned"}
                                    </TableCell>
                                </TableRow>
                            ))}
                        </TableBody>
                    </Table>
                </Box>
            )}
            {taskQuery.hasNextPage ? (
                <Stack alignItems="center" sx={{ mt: 2 }}>
                    <Button
                        variant="outlined"
                        disabled={taskQuery.isFetchingNextPage}
                        onClick={() => taskQuery.fetchNextPage()}
                    >
                        {taskQuery.isFetchingNextPage ? "Loading…" : "Load more tasks"}
                    </Button>
                </Stack>
            ) : null}
            <InspectorDrawer
                open={Boolean(selectedTask)}
                onClose={() => setSelectedTask(null)}
                title={selectedTask?.title ?? "Task"}
                subtitle={selectedTask?.project_name}
                actions={selectedTask ? (
                    <Button
                        component={RouterLink}
                        to={`/projects/${selectedTask.project_id}?tab=board&task=${selectedTask.id}`}
                        variant="contained"
                    >
                        Open task
                    </Button>
                ) : null}
            >
                {selectedTask ? (
                    <Stack spacing={2}>
                        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                            <StatusChip status={displayStatus(String(selectedTask.status))} kind="task" />
                            <Chip size="small" variant="outlined" label={humanizeKey(selectedTask.priority)} />
                            <Chip size="small" variant="outlined" label={humanizeKey(selectedTask.task_type)} />
                        </Stack>
                        <Box>
                            <Typography variant="caption" color="text.secondary">Assignee</Typography>
                            <Typography variant="body2">{selectedTask.assigned_agent_id || "Unassigned"}</Typography>
                        </Box>
                        <Box>
                            <Typography variant="caption" color="text.secondary">Due date</Typography>
                            <Typography variant="body2">{selectedTask.due_date ? formatDate(selectedTask.due_date) : "No due date"}</Typography>
                        </Box>
                        <Box>
                            <Typography variant="caption" color="text.secondary">Last updated</Typography>
                            <Typography variant="body2">{formatDateTime(selectedTask.updated_at)}</Typography>
                        </Box>
                        {selectedTask.labels.length > 0 ? (
                            <Box>
                                <Typography variant="caption" color="text.secondary">Labels</Typography>
                                <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap sx={{ mt: 0.5 }}>
                                    {selectedTask.labels.map((label) => <Chip key={label} size="small" label={label} />)}
                                </Stack>
                            </Box>
                        ) : null}
                    </Stack>
                ) : null}
            </InspectorDrawer>
        </PageShell>
    );
}
