import { useForm } from "react-hook-form";
import { useMemo, useState } from "react";
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import {
    Alert,
    Box,
    Button,
    Chip,
    Divider,
    LinearProgress,
    MenuItem,
    Paper,
    Stack,
    TextField,
    Typography,
} from "@mui/material";
import { Hub as ProjectIcon } from "@mui/icons-material";
import { useNavigate } from "react-router-dom";
import {
    applyBootstrappedProject,
    bootstrapProjectFromText,
    createOrchestrationProject,
    listOrchestrationProjects,
    listProjectAgents,
    listRuns,
} from "../api/orchestration";
import { useSnackbar } from "../app/snackbarContext";
import { EmptyState } from "../components/ui/EmptyState";
import { PageHeader } from "../components/ui/PageHeader";
import { PageShell } from "../components/ui/PageShell";
import { SectionCard } from "../components/ui/SectionCard";
import { formatDate, formatDateTime, humanizeKey } from "../utils/formatters";

type ProjectForm = {
    name: string;
    slug: string;
    description: string;
    goals_markdown: string;
};

type StatusFilter = "all" | "active" | "archived";
type SortKey = "last_active" | "name" | "created";

export default function OrchestrationProjectsPage() {
    const navigate = useNavigate();
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();
    const { register, handleSubmit, reset } = useForm<ProjectForm>();
    const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
    const [sortKey, setSortKey] = useState<SortKey>("last_active");
    const [bootstrapPrompt, setBootstrapPrompt] = useState("");
    const [bootstrapDraft, setBootstrapDraft] = useState<Record<string, unknown> | null>(null);

    const { data: projects = [] } = useQuery({
        queryKey: ["orchestration", "projects"],
        queryFn: listOrchestrationProjects,
    });
    const { data: runs = [] } = useQuery({
        queryKey: ["orchestration", "runs"],
        queryFn: () => listRuns(),
    });

    const membershipQueries = useQueries({
        queries: projects.map((project) => ({
            queryKey: ["orchestration", "project", project.id, "agents"],
            queryFn: () => listProjectAgents(project.id),
            enabled: projects.length > 0,
        })),
    });

    const agentCountByProject = useMemo(() => {
        const map = new Map<string, number>();
        projects.forEach((project, index) => {
            map.set(project.id, membershipQueries[index]?.data?.length ?? 0);
        });
        return map;
    }, [projects, membershipQueries]);

    const activeRunCountByProject = useMemo(() => {
        const map = new Map<string, number>();
        for (const run of runs) {
            if (!["queued", "in_progress"].includes(run.status)) continue;
            map.set(run.project_id, (map.get(run.project_id) ?? 0) + 1);
        }
        return map;
    }, [runs]);

    const lastRunAtByProject = useMemo(() => {
        const map = new Map<string, number>();
        for (const run of runs) {
            const t = new Date(run.created_at).getTime();
            const prev = map.get(run.project_id) ?? 0;
            if (t > prev) map.set(run.project_id, t);
        }
        return map;
    }, [runs]);

    const filteredSortedProjects = useMemo(() => {
        let list = [...projects];
        if (statusFilter === "active") {
            list = list.filter((p) => p.status !== "archived");
        } else if (statusFilter === "archived") {
            list = list.filter((p) => p.status === "archived");
        }
        list.sort((a, b) => {
            if (sortKey === "name") return a.name.localeCompare(b.name);
            if (sortKey === "created") {
                return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
            }
            const tb = lastRunAtByProject.get(b.id) ?? new Date(b.updated_at).getTime();
            const ta = lastRunAtByProject.get(a.id) ?? new Date(a.updated_at).getTime();
            return tb - ta;
        });
        return list;
    }, [projects, statusFilter, sortKey, lastRunAtByProject]);

    const mutation = useMutation({
        mutationFn: createOrchestrationProject,
        onSuccess: async (project) => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "projects"] });
            reset();
            showToast({ message: "Orchestration project created.", severity: "success" });
            navigate(`/agent-projects/${project.id}`);
        },
    });
    const bootstrapMutation = useMutation({
        mutationFn: () => bootstrapProjectFromText(bootstrapPrompt),
        onSuccess: (draft) => setBootstrapDraft(draft),
    });
    const applyBootstrapMutation = useMutation({
        mutationFn: () => applyBootstrappedProject(bootstrapDraft ?? {}),
        onSuccess: async (project) => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "projects"] });
            showToast({ message: "Bootstrapped project created.", severity: "success" });
            navigate(`/agent-projects/${project.id}`);
        },
    });

    return (
        <PageShell maxWidth="xl">
            <PageHeader
                eyebrow="Execution"
                title="Agent Projects"
                description="Projects own tasks, brainstorms, repositories, knowledge, and approvals. Cards show linked agent count and active runs."
            />

            <Box
                sx={{
                    display: "grid",
                    gap: 2,
                    gridTemplateColumns: { xs: "1fr", xl: "360px minmax(0, 1fr)" },
                    alignItems: "start",
                }}
            >
                <SectionCard title="Create project" description="Use a stable slug so provider overrides, repo mappings, and agent scopes remain consistent.">
                    <Stack component="form" spacing={2} onSubmit={handleSubmit((values) => mutation.mutate(values))}>
                        <TextField label="Name" {...register("name")} />
                        <TextField label="Slug" {...register("slug")} />
                        <TextField label="Description" {...register("description")} multiline minRows={3} />
                        <TextField label="Goals" {...register("goals_markdown")} multiline minRows={5} />
                        {mutation.isError && <Alert severity="error">{mutation.error instanceof Error ? mutation.error.message : "Failed to create project."}</Alert>}
                        <Button type="submit" variant="contained">Create project</Button>
                    </Stack>
                    <Divider sx={{ my: 2 }} />
                    <Stack spacing={1.5}>
                        <Typography variant="subtitle2">Natural language setup</Typography>
                        <TextField
                            label='Example: "Create a project to build a REST API for payments"'
                            value={bootstrapPrompt}
                            onChange={(e) => setBootstrapPrompt(e.target.value)}
                            multiline
                            minRows={2}
                        />
                        <Button
                            variant="outlined"
                            disabled={!bootstrapPrompt.trim() || bootstrapMutation.isPending}
                            onClick={() => bootstrapMutation.mutate()}
                        >
                            Generate draft plan
                        </Button>
                        {bootstrapDraft && (
                            <Paper sx={{ p: 1.5, borderRadius: 2, border: 1, borderColor: "divider" }}>
                                <Typography variant="caption" color="text.secondary">
                                    Draft ready. Review and apply to create goals, milestones, and starter tasks.
                                </Typography>
                                <Button
                                    size="small"
                                    sx={{ mt: 1 }}
                                    variant="contained"
                                    onClick={() => applyBootstrapMutation.mutate()}
                                    disabled={applyBootstrapMutation.isPending}
                                >
                                    Approve and create project
                                </Button>
                            </Paper>
                        )}
                    </Stack>
                </SectionCard>

                <Stack spacing={2}>
                    <Paper sx={{ p: 2, borderRadius: 3 }}>
                        <Stack direction={{ xs: "column", sm: "row" }} spacing={2} alignItems={{ sm: "center" }}>
                            <TextField
                                select
                                size="small"
                                label="Status"
                                value={statusFilter}
                                onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
                                sx={{ minWidth: 160 }}
                            >
                                <MenuItem value="all">All statuses</MenuItem>
                                <MenuItem value="active">Active / running</MenuItem>
                                <MenuItem value="archived">Archived</MenuItem>
                            </TextField>
                            <TextField
                                select
                                size="small"
                                label="Sort by"
                                value={sortKey}
                                onChange={(e) => setSortKey(e.target.value as SortKey)}
                                sx={{ minWidth: 180 }}
                            >
                                <MenuItem value="last_active">Last activity</MenuItem>
                                <MenuItem value="name">Name</MenuItem>
                                <MenuItem value="created">Recently created</MenuItem>
                            </TextField>
                            <Typography variant="body2" color="text.secondary">
                                {filteredSortedProjects.length} shown
                            </Typography>
                        </Stack>
                    </Paper>

                    <SectionCard title="Projects" description="Open a project to manage tasks, runs, brainstorms, GitHub links, and activity.">
                        {projects.length === 0 ? (
                            <EmptyState icon={<ProjectIcon />} title="No orchestration projects yet" description="Create one to start assigning agents and execution tasks." />
                        ) : (
                            <Box sx={{ display: "grid", gap: 1.5, gridTemplateColumns: { xs: "1fr", md: "repeat(2, minmax(0, 1fr))" } }}>
                                {filteredSortedProjects.map((project) => {
                                    const agentCount = agentCountByProject.get(project.id) ?? 0;
                                    const activeRuns = activeRunCountByProject.get(project.id) ?? 0;
                                    const lastRunMs = lastRunAtByProject.get(project.id);
                                    return (
                                        <Paper key={project.id} sx={{ p: 2.25, borderRadius: 4 }}>
                                            <Stack spacing={1.25}>
                                                <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={1}>
                                                    <Typography variant="subtitle1">{project.name}</Typography>
                                                    <Chip size="small" label={humanizeKey(project.status)} color={project.status === "active" ? "success" : "default"} variant="outlined" />
                                                </Stack>
                                                <Typography variant="body2" color="text.secondary">{project.description || "No description yet."}</Typography>
                                                <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                                                    <Chip size="small" variant="outlined" label={`${agentCount} agents`} />
                                                    <Chip
                                                        size="small"
                                                        variant="outlined"
                                                        color={activeRuns > 0 ? "warning" : "default"}
                                                        label={`${activeRuns} active runs`}
                                                    />
                                                    <Chip size="small" variant="outlined" label={`Updated ${formatDate(project.updated_at)}`} />
                                                </Stack>
                                                {lastRunMs != null && (
                                                    <Typography variant="caption" color="text.secondary">
                                                        Last run {formatDateTime(new Date(lastRunMs).toISOString())}
                                                    </Typography>
                                                )}
                                                <LinearProgress
                                                    variant="determinate"
                                                    value={Math.min(100, agentCount * 12 + activeRuns * 18)}
                                                    sx={{ height: 4, borderRadius: 2, opacity: 0.35 }}
                                                />
                                                <Button variant="text" sx={{ px: 0, alignSelf: "flex-start" }} onClick={() => navigate(`/agent-projects/${project.id}`)}>
                                                    Open project
                                                </Button>
                                            </Stack>
                                        </Paper>
                                    );
                                })}
                            </Box>
                        )}
                    </SectionCard>
                </Stack>
            </Box>
        </PageShell>
    );
}
