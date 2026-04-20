import { useForm } from "react-hook-form";
import { useEffect, useMemo, useState } from "react";
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { listCompanies } from "../api/companies";
import {
    Alert,
    Box,
    Button,
    Chip,
    Collapse,
    Divider,
    IconButton,
    LinearProgress,
    MenuItem,
    Paper,
    Stack,
    TextField,
    Tooltip,
    Typography,
} from "@mui/material";
import {
    Archive as ArchiveIcon,
    Delete as DeleteIcon,
    ExpandLess as ExpandLessIcon,
    ExpandMore as ExpandMoreIcon,
    Hub as ProjectIcon,
} from "@mui/icons-material";
import { useNavigate } from "react-router-dom";
import {
    applyBootstrappedProject,
    bootstrapProjectFromText,
    createTeamProfileFromTemplate,
    createOrchestrationProject,
    deleteOrchestrationProject,
    listOrchestrationProjects,
    listProjectAgents,
    listRuns,
    listTeamProfiles,
    listTeamTemplates,
    updateOrchestrationProject,
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
    company_id: string;
    team_profile_id: string;
};

type SortKey = "last_active" | "name" | "created";

export default function OrchestrationProjectsPage() {
    const navigate = useNavigate();
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();
    const { register, handleSubmit, reset, setValue, watch } = useForm<ProjectForm>({
        defaultValues: { name: "", slug: "", description: "", goals_markdown: "", company_id: "", team_profile_id: "" },
    });
    const { data: companies = [] } = useQuery({
        queryKey: ["companies"],
        queryFn: listCompanies,
    });
    const selectedCompanyId = watch("company_id");
    useEffect(() => {
        if (!selectedCompanyId && companies.length) {
            setValue("company_id", companies[0].id);
        }
    }, [companies, selectedCompanyId, setValue]);
    const [sortKey, setSortKey] = useState<SortKey>("last_active");
    const [expandedGroups, setExpandedGroups] = useState({
        active: true,
        completed: true,
        archived: true,
    });
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
    const { data: teamTemplates = [] } = useQuery({
        queryKey: ["orchestration", "team-templates"],
        queryFn: listTeamTemplates,
    });
    const { data: teamProfiles = [] } = useQuery({
        queryKey: ["orchestration", "team-profiles"],
        queryFn: listTeamProfiles,
    });
    const [selectedTeamTemplateId, setSelectedTeamTemplateId] = useState("");

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

    const sortedProjects = useMemo(() => {
        let list = [...projects];
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
    }, [projects, sortKey, lastRunAtByProject]);
    const groupedProjects = useMemo(
        () => ({
            active: sortedProjects.filter((project) => !["archived", "completed"].includes(project.status)),
            completed: sortedProjects.filter((project) => project.status === "completed"),
            archived: sortedProjects.filter((project) => project.status === "archived"),
        }),
        [sortedProjects],
    );

    const mutation = useMutation({
        mutationFn: createOrchestrationProject,
        onSuccess: async (project) => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "projects"] });
            reset();
            showToast({ message: "Project created.", severity: "success" });
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
            showToast({ message: "Project created from draft.", severity: "success" });
            navigate(`/agent-projects/${project.id}`);
        },
    });
    const archiveProjectMutation = useMutation({
        mutationFn: (projectId: string) => updateOrchestrationProject(projectId, { status: "archived" }),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "projects"] });
            showToast({ message: "Project archived.", severity: "success" });
        },
    });
    const deleteProjectMutation = useMutation({
        mutationFn: (projectId: string) => deleteOrchestrationProject(projectId),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "projects"] });
            showToast({ message: "Project deleted.", severity: "success" });
        },
    });

    return (
        <PageShell maxWidth="xl">
            <PageHeader
                eyebrow="Workspace"
                title="Agent Projects"
                description="Manage tasks, brainstorms, repos, knowledge, and approvals per project."
            />

            <Box
                sx={{
                    display: "grid",
                    gap: 2,
                    gridTemplateColumns: { xs: "1fr", xl: "360px minmax(0, 1fr)" },
                    alignItems: "start",
                }}
            >
                <SectionCard title="New project" description="Pick a stable slug — used in URLs, repo links, and agent assignments.">
                    <Stack
                        component="form"
                        spacing={2}
                        onSubmit={handleSubmit((values) => {
                            const name = values.name.trim();
                            const rawSlug = values.slug.trim();
                            const slug = (rawSlug || name)
                                .toLowerCase()
                                .replace(/[^a-z0-9-]+/g, "-")
                                .replace(/^-+|-+$/g, "")
                                .slice(0, 255);
                            mutation.mutate({
                                name,
                                slug,
                                description: values.description?.trim() || null,
                                goals_markdown: values.goals_markdown ?? "",
                                settings: values.team_profile_id
                                    ? { execution: { team_profile_id: values.team_profile_id } }
                                    : {},
                            });
                        })}
                    >
                        <input type="hidden" {...register("team_profile_id")} />
                        <TextField
                            label="Name"
                            required
                            inputProps={{ minLength: 2, maxLength: 255 }}
                            {...register("name", { required: true, minLength: 2 })}
                        />
                        <TextField
                            label="Slug"
                            helperText="Lowercase letters, numbers, dashes. Auto-generated from name if blank."
                            inputProps={{ maxLength: 255, pattern: "[a-z0-9][a-z0-9\\-]*" }}
                            {...register("slug", { pattern: /^[a-z0-9][a-z0-9\-]*$/ })}
                        />
                        <TextField
                            select
                            label="Company"
                            value={selectedCompanyId}
                            onChange={(e) => setValue("company_id", e.target.value)}
                            helperText={
                                companies.length === 0
                                    ? "No companies yet — a default workspace will be created."
                                    : "Scopes company-level memory."
                            }
                        >
                            {companies.map((c) => (
                                <MenuItem key={c.id} value={c.id}>
                                    {c.name}
                                </MenuItem>
                            ))}
                            {companies.length === 0 && (
                                <MenuItem value="">Default workspace</MenuItem>
                            )}
                        </TextField>
                        <TextField label="Description" {...register("description")} multiline minRows={3} />
                        <TextField label="Goals" {...register("goals_markdown")} multiline minRows={5} />
                        <TextField
                            select
                            label="Team"
                            value={watch("team_profile_id")}
                            onChange={(e) => setValue("team_profile_id", e.target.value)}
                            helperText={teamProfiles.length > 0
                                ? "Team profile saved from team template."
                                : "No team profiles yet. Save one from a team template below."}
                        >
                            <MenuItem value="">None</MenuItem>
                            {teamProfiles.map((profile) => (
                                <MenuItem key={profile.id} value={profile.id}>
                                    {profile.name}
                                </MenuItem>
                            ))}
                        </TextField>
                        {teamProfiles.length === 0 ? (
                            <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
                                <TextField
                                    select
                                    label="Team template"
                                    value={selectedTeamTemplateId}
                                    onChange={(e) => setSelectedTeamTemplateId(e.target.value)}
                                    sx={{ minWidth: 220 }}
                                >
                                    {teamTemplates.map((template) => (
                                        <MenuItem key={template.id} value={template.id}>{template.name}</MenuItem>
                                    ))}
                                </TextField>
                                <Button
                                    variant="outlined"
                                    disabled={!selectedTeamTemplateId}
                                    onClick={() => {
                                        createTeamProfileFromTemplate({ template_id: selectedTeamTemplateId })
                                            .then(async (profile) => {
                                                await queryClient.invalidateQueries({ queryKey: ["orchestration", "team-profiles"] });
                                                setValue("team_profile_id", profile.id);
                                                showToast({ message: "Team profile saved from template.", severity: "success" });
                                            })
                                            .catch((error: unknown) => {
                                                showToast({
                                                    message: error instanceof Error ? error.message : "Couldn't create team profile.",
                                                    severity: "error",
                                                });
                                            });
                                    }}
                                >
                                    Save team profile
                                </Button>
                            </Stack>
                        ) : null}
                        {mutation.isError && <Alert severity="error">{mutation.error instanceof Error ? mutation.error.message : "Couldn't create project. Try again."}</Alert>}
                        <Button type="submit" variant="contained" disabled={mutation.isPending}>Save</Button>
                    </Stack>
                    <Divider sx={{ my: 2 }} />
                    <Stack spacing={1.5}>
                        <Typography variant="subtitle2">Generate from description</Typography>
                        <TextField
                            label="Project description"
                            placeholder='e.g. "Build a REST API for payments"'
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
                                    Draft ready. Apply to create the project with goals, milestones, and starter tasks.
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
                                {projects.length} {projects.length === 1 ? "project" : "projects"}
                            </Typography>
                        </Stack>
                    </Paper>

                    <SectionCard>
                        {projects.length === 0 ? (
                            <EmptyState icon={<ProjectIcon />} title="No projects yet" description="Create your first project to assign agents and tasks." />
                        ) : (
                            <Stack spacing={2}>
                                {(["active", "completed", "archived"] as const).map((groupKey) => {
                                    const items = groupedProjects[groupKey];
                                    const isExpanded = expandedGroups[groupKey];
                                    return (
                                        <Paper key={groupKey} sx={{ p: 1.5, borderRadius: 3, border: 1, borderColor: "divider" }}>
                                            <Stack direction="row" justifyContent="space-between" alignItems="center">
                                                <Typography variant="subtitle1">
                                                    {humanizeKey(groupKey)} ({items.length})
                                                </Typography>
                                                <IconButton
                                                    size="small"
                                                    onClick={() => setExpandedGroups((current) => ({ ...current, [groupKey]: !current[groupKey] }))}
                                                >
                                                    {isExpanded ? <ExpandLessIcon fontSize="small" /> : <ExpandMoreIcon fontSize="small" />}
                                                </IconButton>
                                            </Stack>
                                            <Collapse in={isExpanded}>
                                                {items.length === 0 ? (
                                                    <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                                                        No projects.
                                                    </Typography>
                                                ) : (
                                                    <Box sx={{ mt: 1.25, display: "grid", gap: 1.5, gridTemplateColumns: { xs: "1fr", md: "repeat(2, minmax(0, 1fr))" } }}>
                                                        {items.map((project) => {
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
                                                                            <Chip size="small" variant="outlined" color={activeRuns > 0 ? "warning" : "default"} label={`${activeRuns} active runs`} />
                                                                            <Chip size="small" variant="outlined" label={`Updated ${formatDate(project.updated_at)}`} />
                                                                        </Stack>
                                                                        {lastRunMs != null ? (
                                                                            <Typography variant="caption" color="text.secondary">
                                                                                Last run {formatDateTime(new Date(lastRunMs).toISOString())}
                                                                            </Typography>
                                                                        ) : null}
                                                                        <LinearProgress
                                                                            variant="determinate"
                                                                            value={Math.min(100, agentCount * 12 + activeRuns * 18)}
                                                                            sx={{ height: 4, borderRadius: 2, opacity: 0.35 }}
                                                                        />
                                                                        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                                                                            <Button variant="text" sx={{ px: 0 }} onClick={() => navigate(`/agent-projects/${project.id}`)}>
                                                                                Open project
                                                                            </Button>
                                                                            {project.status !== "archived" ? (
                                                                                <Tooltip title="Archive project">
                                                                                    <Button
                                                                                        size="small"
                                                                                        variant="outlined"
                                                                                        color="warning"
                                                                                        startIcon={<ArchiveIcon />}
                                                                                        onClick={() => archiveProjectMutation.mutate(project.id)}
                                                                                    >
                                                                                        Archive
                                                                                    </Button>
                                                                                </Tooltip>
                                                                            ) : null}
                                                                            <Tooltip title="Delete project permanently">
                                                                                <Button
                                                                                    size="small"
                                                                                    variant="outlined"
                                                                                    color="error"
                                                                                    startIcon={<DeleteIcon />}
                                                                                    onClick={() => {
                                                                                        if (!window.confirm(`Delete project "${project.name}" permanently?`)) return;
                                                                                        deleteProjectMutation.mutate(project.id);
                                                                                    }}
                                                                                >
                                                                                    Delete
                                                                                </Button>
                                                                            </Tooltip>
                                                                        </Stack>
                                                                    </Stack>
                                                                </Paper>
                                                            );
                                                        })}
                                                    </Box>
                                                )}
                                            </Collapse>
                                        </Paper>
                                    );
                                })}
                            </Stack>
                        )}
                    </SectionCard>
                </Stack>
            </Box>
        </PageShell>
    );
}
