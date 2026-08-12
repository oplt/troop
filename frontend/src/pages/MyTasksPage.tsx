import { useMemo } from "react";
import { Link as RouterLink } from "react-router-dom";
import { useQueries, useQuery } from "@tanstack/react-query";
import {
    Box,
    Chip,
    CircularProgress,
    Link,
    Paper,
    Stack,
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableRow,
    Typography,
} from "@mui/material";
import {
    listOrchestrationProjects,
    listOrchestrationTasks,
    type OrchestrationTask,
} from "../api/orchestration";
import { PageShell } from "../components/ui/PageShell";

type TaskRow = OrchestrationTask & { project_name: string; project_id: string };

const CLOSED = new Set(["completed", "archived", "cancelled"]);

function displayStatus(status: string): string {
    if (status === "synced_to_github") return "completed";
    return status;
}

export default function MyTasksPage() {
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
                const status = String(task.status || "");
                if (CLOSED.has(status)) continue;
                out.push({
                    ...task,
                    project_id: project.id,
                    project_name: project.name,
                });
            }
        });
        out.sort((a, b) => String(b.updated_at || "").localeCompare(String(a.updated_at || "")));
        return out;
    }, [projects, taskQueries]);

    const loading = loadingProjects || taskQueries.some((q) => q.isLoading);

    return (
        <PageShell>
            <Stack spacing={3} sx={{ py: 3 }}>
                <Box>
                    <Typography variant="h4" gutterBottom>
                        My tasks
                    </Typography>
                    <Typography color="text.secondary">
                        Open work across your projects. Legacy `synced_to_github` displays as completed.
                    </Typography>
                </Box>

                <Paper sx={{ p: 2 }}>
                    {loading ? (
                        <Stack alignItems="center" sx={{ py: 6 }}>
                            <CircularProgress />
                        </Stack>
                    ) : rows.length === 0 ? (
                        <Typography color="text.secondary">No open tasks.</Typography>
                    ) : (
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
                                {rows.map((task) => (
                                    <TableRow key={task.id} hover>
                                        <TableCell>
                                            <Link
                                                component={RouterLink}
                                                to={`/projects/${task.project_id}?task=${task.id}`}
                                                underline="hover"
                                            >
                                                {task.title}
                                            </Link>
                                        </TableCell>
                                        <TableCell>{task.project_name}</TableCell>
                                        <TableCell>
                                            <Chip size="small" label={displayStatus(String(task.status))} />
                                        </TableCell>
                                        <TableCell>
                                            {task.assigned_agent_id || "Unassigned"}
                                        </TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    )}
                </Paper>
            </Stack>
        </PageShell>
    );
}
