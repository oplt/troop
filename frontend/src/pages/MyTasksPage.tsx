import { useMemo, useState } from "react";
import { Link as RouterLink } from "react-router-dom";
import { useQueries, useQuery } from "@tanstack/react-query";
import {
    Box,
    Button,
    CircularProgress,
    Link,
    MenuItem,
    Stack,
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableRow,
    TextField,
} from "@mui/material";
import {
    listOrchestrationProjects,
    listOrchestrationTasks,
    type OrchestrationTask,
} from "../api/orchestration";
import { PageShell } from "../components/ui/PageShell";
import { PageHeader } from "../components/ui/PageHeader";
import { EmptyState } from "../components/ui/EmptyState";
import { StatusChip } from "../components/ui/StatusChip";
import { FilterToolbar } from "../components/ui/FilterToolbar";
import { Assignment as TasksIcon } from "@mui/icons-material";

type TaskRow = OrchestrationTask & { project_name: string; project_id: string };

const CLOSED = new Set(["completed", "archived", "cancelled"]);

function displayStatus(status: string): string {
    if (status === "synced_to_github") return "completed";
    return status;
}

export default function MyTasksPage() {
    const [projectFilter, setProjectFilter] = useState("");
    const [statusFilter, setStatusFilter] = useState("all");
    const { data: projects = [], isLoading: loadingProjects } = useQuery({
        queryKey: ["orchestration", "projects"],
        queryFn: listOrchestrationProjects,
    });

    const taskQueries = useQueries({
        queries: projects.map((project) => ({
            queryKey: ["orchestration", "project-tasks", project.id, "my-tasks"],
            queryFn: () => listOrchestrationTasks(project.id),
            enabled: Boolean(project.id),
        })),
    });

    const rows = useMemo(() => {
        const out: TaskRow[] = [];
        taskQueries.forEach((query, index) => {
            const project = projects[index];
            if (!project || !query.data) return;
            for (const task of query.data) {
                const status = displayStatus(String(task.status || ""));
                if (CLOSED.has(status)) continue;
                out.push({
                    ...task,
                    status,
                    project_id: project.id,
                    project_name: project.name,
                });
            }
        });
        out.sort((a, b) => String(b.updated_at || "").localeCompare(String(a.updated_at || "")));
        return out;
    }, [projects, taskQueries]);

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

    const loading = loadingProjects || taskQueries.some((q) => q.isLoading);

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
                                        <Link
                                            component={RouterLink}
                                            to={`/projects/${task.project_id}?tab=board&task=${task.id}`}
                                            underline="hover"
                                        >
                                            {task.title}
                                        </Link>
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
        </PageShell>
    );
}
