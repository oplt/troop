import { useForm, useWatch } from "react-hook-form";
import { useEffect, useMemo, useState } from "react";
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { listCompanies } from "../api/companies";
import {
    Alert,
    Box,
    Button,
    CardActionArea,
    Chip,
    Collapse,
    Divider,
    Drawer,
    IconButton,
    InputAdornment,
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
    CheckCircle as CheckCircleIcon,
    Delete as DeleteIcon,
    ErrorOutline as ErrorOutlineIcon,
    ExpandLess as ExpandLessIcon,
    ExpandMore as ExpandMoreIcon,
    Hub as ProjectIcon,
    PendingActions as PendingActionsIcon,
    PlayArrow as PlayArrowIcon,
    Refresh as RefreshIcon,
    Search as SearchIcon,
    WarningAmber as WarningAmberIcon,
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
    validateLocalRepoWorkspace,
} from "../api/orchestration";
import { useSnackbar } from "../app/snackbarContext";
import { EmptyState } from "../components/ui/EmptyState";
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
    local_repo_path: string;
    dirty_worktree_policy: string;
    allowed_branches: string;
    file_allowlist: string;
    file_denylist: string;
    command_allowlist: string;
    max_diff_bytes: number;
};

type SortKey = "last_active" | "name" | "created";
type StatusFilter = "all" | "active" | "completed" | "archived" | "attention";

function splitList(value: string) {
    return value
        .split(/[,\n]/)
        .map((item) => item.trim())
        .filter(Boolean);
}

function buildLocalRepoPayload(
    values: Pick<
        ProjectForm,
        | "local_repo_path"
        | "dirty_worktree_policy"
        | "allowed_branches"
        | "file_allowlist"
        | "file_denylist"
        | "command_allowlist"
        | "max_diff_bytes"
    >,
) {
    const repoPath = values.local_repo_path.trim();
    const maxDiffBytes = Number(values.max_diff_bytes);
    return {
        enabled: Boolean(repoPath),
        repo_path: repoPath,
        dirty_worktree_policy: values.dirty_worktree_policy || "block",
        allowed_branches: splitList(values.allowed_branches),
        file_allowlist: splitList(values.file_allowlist),
        file_denylist: splitList(values.file_denylist),
        command_allowlist: splitList(values.command_allowlist),
        max_diff_bytes: Math.max(1_000, Math.min(5_000_000, Math.floor(Number.isFinite(maxDiffBytes) ? maxDiffBytes : 200_000))),
    };
}

export default function OrchestrationProjectsPage() {
    const navigate = useNavigate();
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();
    const { control, register, handleSubmit, reset, setValue } = useForm<ProjectForm>({
        defaultValues: {
            name: "",
            slug: "",
            description: "",
            goals_markdown: "",
            company_id: "",
            team_profile_id: "",
            local_repo_path: "",
            dirty_worktree_policy: "block",
            allowed_branches: "main, master, develop",
            file_allowlist: "**/*",
            file_denylist: ".git/**, .env, .env.*, **/.env, **/.env.*, node_modules/**, **/node_modules/**",
            command_allowlist: "git status, git diff, rg, pnpm, uv, pytest",
            max_diff_bytes: 200000,
        },
    });
    const { data: companies = [] } = useQuery({
        queryKey: ["companies"],
        queryFn: listCompanies,
    });
    const selectedCompanyId = useWatch({ control, name: "company_id" });
    const selectedTeamProfileId = useWatch({ control, name: "team_profile_id" });
    const watchedLocalRepoPath = useWatch({ control, name: "local_repo_path" });
    const watchedDirtyPolicy = useWatch({ control, name: "dirty_worktree_policy" });
    const watchedAllowedBranches = useWatch({ control, name: "allowed_branches" });
    const watchedFileAllowlist = useWatch({ control, name: "file_allowlist" });
    const watchedFileDenylist = useWatch({ control, name: "file_denylist" });
    const watchedCommandAllowlist = useWatch({ control, name: "command_allowlist" });
    const watchedMaxDiffBytes = useWatch({ control, name: "max_diff_bytes" });
    useEffect(() => {
        if (!selectedCompanyId && companies.length) {
            setValue("company_id", companies[0].id);
        }
    }, [companies, selectedCompanyId, setValue]);
    const [sortKey, setSortKey] = useState<SortKey>("last_active");
    const [searchQuery, setSearchQuery] = useState("");
    const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
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

    const failedRunCountByProject = useMemo(() => {
        const map = new Map<string, number>();
        for (const run of runs) {
            if (!["failed", "error", "cancelled"].includes(run.status)) continue;
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

    const filteredProjects = useMemo(() => {
        const query = searchQuery.trim().toLowerCase();
        return projects.filter((project) => {
            const activeRuns = activeRunCountByProject.get(project.id) ?? 0;
            const failedRuns = failedRunCountByProject.get(project.id) ?? 0;
            const matchesQuery =
                !query ||
                project.name.toLowerCase().includes(query) ||
                String(project.description ?? "").toLowerCase().includes(query) ||
                project.status.toLowerCase().includes(query);
            const matchesStatus =
                statusFilter === "all" ||
                project.status === statusFilter ||
                (statusFilter === "attention" && (activeRuns > 0 || failedRuns > 0));
            return matchesQuery && matchesStatus;
        });
    }, [projects, searchQuery, statusFilter, activeRunCountByProject, failedRunCountByProject]);

    const sortedProjects = useMemo(() => {
        const list = [...filteredProjects];
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
    }, [filteredProjects, sortKey, lastRunAtByProject]);

    const groupedProjects = useMemo(
        () => ({
            active: sortedProjects.filter((project) => !["archived", "completed"].includes(project.status)),
            completed: sortedProjects.filter((project) => project.status === "completed"),
            archived: sortedProjects.filter((project) => project.status === "archived"),
        }),
        [sortedProjects],
    );

    const dashboardStats = useMemo(() => {
        const activeProjects = projects.filter((project) => !["archived", "completed"].includes(project.status)).length;
        const runningRuns = runs.filter((run) => ["queued", "in_progress"].includes(run.status)).length;
        const failedRuns = runs.filter((run) => ["failed", "error", "cancelled"].includes(run.status)).length;
        const assignedAgents = projects.reduce((total, project) => total + (agentCountByProject.get(project.id) ?? 0), 0);
        return { activeProjects, runningRuns, failedRuns, assignedAgents };
    }, [projects, runs, agentCountByProject]);

    const attentionProjects = useMemo(
        () =>
            projects.filter((project) => {
                const activeRuns = activeRunCountByProject.get(project.id) ?? 0;
                const failedRuns = failedRunCountByProject.get(project.id) ?? 0;
                return activeRuns > 0 || failedRuns > 0;
            }),
        [projects, activeRunCountByProject, failedRunCountByProject],
    );

    const recentRuns = useMemo(
        () =>
            [...runs]
                .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
                .slice(0, 6),
        [runs],
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

    const [drawerOpen, setDrawerOpen] = useState(false);
    const [repoValidationSignature, setRepoValidationSignature] = useState<string | null>(null);

    const currentRepoPayload = useMemo(
        () =>
            buildLocalRepoPayload({
                local_repo_path: watchedLocalRepoPath ?? "",
                dirty_worktree_policy: watchedDirtyPolicy ?? "block",
                allowed_branches: watchedAllowedBranches ?? "",
                file_allowlist: watchedFileAllowlist ?? "",
                file_denylist: watchedFileDenylist ?? "",
                command_allowlist: watchedCommandAllowlist ?? "",
                max_diff_bytes: watchedMaxDiffBytes ?? 200000,
            }),
        [
            watchedAllowedBranches,
            watchedCommandAllowlist,
            watchedDirtyPolicy,
            watchedFileAllowlist,
            watchedFileDenylist,
            watchedLocalRepoPath,
            watchedMaxDiffBytes,
        ],
    );
    const currentRepoSignature = useMemo(() => JSON.stringify(currentRepoPayload), [currentRepoPayload]);
    const hasLocalRepoPath = Boolean(String(currentRepoPayload.repo_path ?? "").trim());
    const repoValidationIsCurrent = repoValidationSignature === currentRepoSignature;
    const validateRepoMutation = useMutation({
        mutationFn: (payload: Record<string, unknown>) => validateLocalRepoWorkspace(payload),
        onSuccess: (_status, payload) => {
            setRepoValidationSignature(JSON.stringify(payload));
        },
    });
    const repoValidation = repoValidationIsCurrent ? validateRepoMutation.data : undefined;
    const repoValidationBlocked = hasLocalRepoPath && (!repoValidation || !repoValidation.valid);

    const submitProject = handleSubmit((values) => {
        const name = values.name.trim();
        const rawSlug = values.slug.trim();
        const slug = (rawSlug || name)
            .toLowerCase()
            .replace(/[^a-z0-9-]+/g, "-")
            .replace(/^-+|-+$/g, "")
            .slice(0, 255);
        const localRepoPath = values.local_repo_path.trim();
        const localRepo = buildLocalRepoPayload(values);
        const signature = JSON.stringify(localRepo);
        if (localRepoPath && (repoValidationSignature !== signature || !validateRepoMutation.data?.valid)) {
            validateRepoMutation.mutate(localRepo);
            showToast({ message: "Validate repo connection before saving.", severity: "warning" });
            return;
        }

        mutation.mutate({
            name,
            slug,
            description: values.description?.trim() || null,
            goals_markdown: values.goals_markdown ?? "",
            settings: {
                ...(values.team_profile_id
                    ? { execution: { team_profile_id: values.team_profile_id } }
                    : {}),
                local_repo: localRepo,
            },
        });
    });

    return (
        <PageShell maxWidth="xl">
            <Stack spacing={3}>
                <Paper
                    elevation={0}
                    sx={{
                        p: { xs: 2, md: 3 },
                        borderRadius: 4,
                        border: 1,
                        borderColor: "divider",
                        bgcolor: "background.paper",
                    }}
                >
                    <Stack spacing={2.5}>
                        <Stack direction={{ xs: "column", md: "row" }} justifyContent="space-between" spacing={2}>
                            <Box>
                                <Typography variant="h4" sx={{ fontWeight: 800, letterSpacing: -0.4 }}>
                                    Agent Projects
                                </Typography>
                                <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                                    Monitor project health, agent capacity, active runs, and repo-backed workspaces.
                                </Typography>
                            </Box>
                            <Stack direction={{ xs: "column", sm: "row" }} spacing={1} alignItems={{ sm: "center" }}>
                                <Button variant="outlined" startIcon={<RefreshIcon />} onClick={() => queryClient.invalidateQueries({ queryKey: ["orchestration"] })}>
                                    Refresh
                                </Button>
                                <Button variant="contained" startIcon={<ProjectIcon />} onClick={() => setDrawerOpen(true)}>
                                    New project
                                </Button>
                            </Stack>
                        </Stack>

                        <Box sx={{ display: "grid", gap: 1.5, gridTemplateColumns: { xs: "1fr", sm: "repeat(2, 1fr)", lg: "repeat(4, 1fr)" } }}>
                            {[
                                { label: "Active projects", value: dashboardStats.activeProjects, icon: <ProjectIcon fontSize="small" /> },
                                { label: "Running runs", value: dashboardStats.runningRuns, icon: <PlayArrowIcon fontSize="small" /> },
                                { label: "Needs attention", value: dashboardStats.failedRuns, icon: <WarningAmberIcon fontSize="small" /> },
                                { label: "Assigned agents", value: dashboardStats.assignedAgents, icon: <PendingActionsIcon fontSize="small" /> },
                            ].map((item) => (
                                <Paper key={item.label} variant="outlined" sx={{ p: 2, borderRadius: 3 }}>
                                    <Stack direction="row" spacing={1.25} alignItems="center">
                                        <Box sx={{ display: "grid", placeItems: "center", width: 34, height: 34, borderRadius: 2, bgcolor: "action.hover" }}>
                                            {item.icon}
                                        </Box>
                                        <Box>
                                            <Typography variant="h6" sx={{ fontWeight: 800, lineHeight: 1 }}>
                                                {item.value}
                                            </Typography>
                                            <Typography variant="caption" color="text.secondary">
                                                {item.label}
                                            </Typography>
                                        </Box>
                                    </Stack>
                                </Paper>
                            ))}
                        </Box>

                        <Stack direction={{ xs: "column", md: "row" }} spacing={1.5} alignItems={{ md: "center" }}>
                            <TextField
                                size="small"
                                placeholder="Search projects, descriptions, status..."
                                value={searchQuery}
                                onChange={(e) => setSearchQuery(e.target.value)}
                                sx={{ flex: 1 }}
                                InputProps={{
                                    startAdornment: (
                                        <InputAdornment position="start">
                                            <SearchIcon fontSize="small" />
                                        </InputAdornment>
                                    ),
                                }}
                            />
                            <TextField
                                select
                                size="small"
                                label="Status"
                                value={statusFilter}
                                onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
                                sx={{ minWidth: 170 }}
                            >
                                <MenuItem value="all">All projects</MenuItem>
                                <MenuItem value="attention">Needs attention</MenuItem>
                                <MenuItem value="active">Active</MenuItem>
                                <MenuItem value="completed">Completed</MenuItem>
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
                        </Stack>
                    </Stack>
                </Paper>



                <Box sx={{ display: "grid", gap: 3, gridTemplateColumns: { xs: "1fr", xl: "minmax(0, 1fr) 360px" }, alignItems: "start" }}>
                    <SectionCard>
                        {projects.length === 0 ? (
                            <EmptyState icon={<ProjectIcon />} title="No projects yet" description="Create your first orchestration project to assign agents, run tasks, and sync work with GitHub." />
                        ) : sortedProjects.length === 0 ? (
                            <EmptyState icon={<SearchIcon />} title="No matching projects" description="Clear the search or adjust filters to see more projects." />
                        ) : (
                            <Stack spacing={2}>
                                {(["active", "completed", "archived"] as const).map((groupKey) => {
                                    const items = groupedProjects[groupKey];
                                    const isExpanded = expandedGroups[groupKey];
                                    if (items.length === 0 && statusFilter !== "all") return null;
                                    return (
                                        <Paper key={groupKey} variant="outlined" sx={{ p: 1.5, borderRadius: 3 }}>
                                            <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ px: 0.5 }}>
                                                <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
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
                                                    <Typography variant="body2" color="text.secondary" sx={{ mt: 1, px: 0.5 }}>
                                                        No {groupKey} projects.
                                                    </Typography>
                                                ) : (
                                                    <Box sx={{ mt: 1.25, display: "grid", gap: 1.5, gridTemplateColumns: { xs: "1fr", lg: "repeat(2, minmax(0, 1fr))" } }}>
                                                        {items.map((project) => {
                                                            const agentCount = agentCountByProject.get(project.id) ?? 0;
                                                            const activeRuns = activeRunCountByProject.get(project.id) ?? 0;
                                                            const failedRuns = failedRunCountByProject.get(project.id) ?? 0;
                                                            const lastRunMs = lastRunAtByProject.get(project.id);
                                                            const localRepo = project.settings?.local_repo as { enabled?: boolean; repo_path?: string; dirty_worktree_policy?: string } | undefined;
                                                            const progress = project.status === "completed" ? 100 : Math.min(92, 10 + agentCount * 8 + activeRuns * 12);
                                                            const statusColor = failedRuns > 0 ? "error" : activeRuns > 0 ? "warning" : project.status === "active" ? "success" : "default";
                                                            return (
                                                                <Paper
                                                                    key={project.id}
                                                                    variant="outlined"
                                                                    sx={{
                                                                        overflow: "hidden",
                                                                        borderRadius: 4,
                                                                        transition: "border-color 160ms ease, transform 160ms ease, box-shadow 160ms ease",
                                                                        "&:hover": { borderColor: "primary.main", transform: "translateY(-1px)", boxShadow: 3 },
                                                                    }}
                                                                >
                                                                    <CardActionArea onClick={() => navigate(`/agent-projects/${project.id}`)} sx={{ p: 2.25, alignItems: "stretch" }}>
                                                                        <Stack spacing={1.35}>
                                                                            <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={1}>
                                                                                <Box sx={{ minWidth: 0 }}>
                                                                                    <Typography variant="subtitle1" sx={{ fontWeight: 800 }} noWrap>
                                                                                        {project.name}
                                                                                    </Typography>
                                                                                    <Typography variant="caption" color="text.secondary">
                                                                                        Updated {formatDate(project.updated_at)}
                                                                                    </Typography>
                                                                                </Box>
                                                                                <Chip size="small" label={failedRuns > 0 ? "Needs attention" : humanizeKey(project.status)} color={statusColor} variant={activeRuns > 0 || failedRuns > 0 ? "filled" : "outlined"} />
                                                                            </Stack>

                                                                            <Typography variant="body2" color="text.secondary" sx={{ minHeight: 40 }}>
                                                                                {project.description || "No description yet. Add a short goal so agents and reviewers understand the workspace."}
                                                                            </Typography>

                                                                            <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                                                                                <Chip size="small" variant="outlined" label={`${agentCount} agent${agentCount === 1 ? "" : "s"}`} />
                                                                                <Chip size="small" variant="outlined" color={activeRuns > 0 ? "warning" : "default"} label={`${activeRuns} active run${activeRuns === 1 ? "" : "s"}`} />
                                                                                {failedRuns > 0 ? <Chip size="small" color="error" variant="outlined" label={`${failedRuns} failed`} /> : null}
                                                                                {localRepo?.enabled ? <Chip size="small" variant="outlined" label="Local repo" /> : null}
                                                                            </Stack>

                                                                            <Box>
                                                                                <Stack direction="row" justifyContent="space-between" sx={{ mb: 0.5 }}>
                                                                                    <Typography variant="caption" color="text.secondary">Execution readiness</Typography>
                                                                                    <Typography variant="caption" color="text.secondary">{progress}%</Typography>
                                                                                </Stack>
                                                                                <LinearProgress variant="determinate" value={progress} sx={{ height: 6, borderRadius: 999 }} />
                                                                            </Box>

                                                                            <Stack spacing={0.4}>
                                                                                {lastRunMs != null ? (
                                                                                    <Typography variant="caption" color="text.secondary">
                                                                                        Last run {formatDateTime(new Date(lastRunMs).toISOString())}
                                                                                    </Typography>
                                                                                ) : (
                                                                                    <Typography variant="caption" color="text.secondary">No runs yet</Typography>
                                                                                )}
                                                                                {localRepo?.enabled ? (
                                                                                    <Typography variant="caption" color="text.secondary" noWrap>
                                                                                        Repo: {localRepo.repo_path ?? "local"} · dirty policy {humanizeKey(String(localRepo.dirty_worktree_policy ?? "block"))}
                                                                                    </Typography>
                                                                                ) : null}
                                                                            </Stack>
                                                                        </Stack>
                                                                    </CardActionArea>
                                                                    <Divider />
                                                                    <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={1} sx={{ p: 1.25, pl: 2 }}>
                                                                        <Button size="small" variant={activeRuns > 0 ? "contained" : "text"} startIcon={<PlayArrowIcon />} onClick={() => navigate(`/agent-projects/${project.id}`)}>
                                                                            {activeRuns > 0 ? "Resume" : "Open workspace"}
                                                                        </Button>
                                                                        <Stack direction="row" spacing={0.5}>
                                                                            {project.status !== "archived" ? (
                                                                                <Tooltip title="Archive project">
                                                                                    <IconButton size="small" color="warning" onClick={() => archiveProjectMutation.mutate(project.id)}>
                                                                                        <ArchiveIcon fontSize="small" />
                                                                                    </IconButton>
                                                                                </Tooltip>
                                                                            ) : null}
                                                                            <Tooltip title="Delete project permanently">
                                                                                <IconButton
                                                                                    size="small"
                                                                                    color="error"
                                                                                    onClick={() => {
                                                                                        if (!window.confirm(`Delete project "${project.name}" permanently?`)) return;
                                                                                        deleteProjectMutation.mutate(project.id);
                                                                                    }}
                                                                                >
                                                                                    <DeleteIcon fontSize="small" />
                                                                                </IconButton>
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

                    <Paper variant="outlined" sx={{ p: 2, borderRadius: 4, position: { xl: "sticky" }, top: { xl: 16 } }}>
                        <Stack spacing={1.5}>
                            <Box>
                                <Typography variant="subtitle1" sx={{ fontWeight: 800 }}>
                                    Recent run activity
                                </Typography>
                                <Typography variant="body2" color="text.secondary">
                                    Latest orchestration events across projects.
                                </Typography>
                            </Box>
                            <Divider />
                            {recentRuns.length === 0 ? (
                                <Typography variant="body2" color="text.secondary">
                                    No runs yet. Start a task from a project workspace to see live activity here.
                                </Typography>
                            ) : (
                                <Stack spacing={1.25}>
                                    {recentRuns.map((run) => {
                                        const project = projects.find((item) => item.id === run.project_id);
                                        const isRunning = ["queued", "in_progress"].includes(run.status);
                                        const isFailed = ["failed", "error", "cancelled"].includes(run.status);
                                        return (
                                            <Paper key={run.id} variant="outlined" sx={{ p: 1.25, borderRadius: 2 }}>
                                                <Stack spacing={0.5}>
                                                    <Stack direction="row" justifyContent="space-between" spacing={1}>
                                                        <Typography variant="body2" sx={{ fontWeight: 700 }} noWrap>
                                                            {project?.name ?? "Unknown project"}
                                                        </Typography>
                                                        <Chip size="small" label={humanizeKey(run.status)} color={isFailed ? "error" : isRunning ? "warning" : "default"} />
                                                    </Stack>
                                                    <Typography variant="caption" color="text.secondary">
                                                        {formatDateTime(run.created_at)}
                                                    </Typography>
                                                </Stack>
                                            </Paper>
                                        );
                                    })}
                                </Stack>
                            )}
                        </Stack>
                    </Paper>
                </Box>
            </Stack>
            <Drawer
                anchor="right"
                open={drawerOpen}
                onClose={() => setDrawerOpen(false)}
                PaperProps={{
                    sx: {
                        width: 500,
                        maxWidth: "90vw",
                        p: 3,
                    },
                }}
            >
                <Stack spacing={2} component="form" onSubmit={submitProject} sx={{ width: "100%" }}>
                    <input type="hidden" {...register("team_profile_id")} />
                    <TextField
                        label="Name"
                        required
                        inputProps={{ minLength: 2, maxLength: 255 }}
                        {...register("name", { required: true, minLength: 2 })}
                    />

                    <TextField
                        select
                        label="Company"
                        value={selectedCompanyId}
                        onChange={(e) => setValue("company_id", e.target.value)}
                        helperText={
                            companies.length === 0
                                ? "No companies yet - a default workspace will be created."
                                : "Scopes company-level memory."
                        }
                    >
                        {companies.map((c) => (
                            <MenuItem key={c.id} value={c.id}>
                                {c.name}
                            </MenuItem>
                        ))}
                        {companies.length === 0 && <MenuItem value="">Default workspace</MenuItem>}
                    </TextField>
                    <TextField label="Description" {...register("description")} multiline minRows={3} />
                    <TextField label="Goals" {...register("goals_markdown")} multiline minRows={5} />
                    <Divider />
                    <Typography variant="subtitle2">Local repo workspace</Typography>
                    <TextField
                        label="Local repo path"
                        placeholder="/home/polat/Desktop/Projects/my-repo"
                        helperText="Agents use this Git repo for code-change tasks. Leave blank for non-code projects."
                        {...register("local_repo_path")}
                    />
                    <Stack direction={{ xs: "column", sm: "row" }} spacing={1} alignItems={{ sm: "center" }}>
                        <Button
                            variant="outlined"
                            startIcon={<RefreshIcon />}
                            disabled={!hasLocalRepoPath || validateRepoMutation.isPending}
                            onClick={() => validateRepoMutation.mutate(currentRepoPayload)}
                        >
                            Validate repo
                        </Button>
                        {hasLocalRepoPath && repoValidation?.valid ? (
                            <Chip
                                icon={<CheckCircleIcon />}
                                color="success"
                                variant="outlined"
                                label="Ready"
                                sx={{ alignSelf: { xs: "flex-start", sm: "center" } }}
                            />
                        ) : null}
                        {hasLocalRepoPath && repoValidation && !repoValidation.valid ? (
                            <Chip
                                icon={<ErrorOutlineIcon />}
                                color="error"
                                variant="outlined"
                                label="Blocked"
                                sx={{ alignSelf: { xs: "flex-start", sm: "center" } }}
                            />
                        ) : null}
                    </Stack>
                    {hasLocalRepoPath && validateRepoMutation.isPending ? <LinearProgress /> : null}
                    {hasLocalRepoPath && !repoValidationIsCurrent && validateRepoMutation.data ? (
                        <Alert severity="info">Repo settings changed. Validate again before saving.</Alert>
                    ) : null}
                    {validateRepoMutation.isError ? (
                        <Alert severity="error">
                            {validateRepoMutation.error instanceof Error
                                ? validateRepoMutation.error.message
                                : "Could not validate repo."}
                        </Alert>
                    ) : null}
                    {repoValidation ? (
                        <Paper sx={{ p: 1.5, borderRadius: 2, border: 1, borderColor: repoValidation.valid ? "success.main" : "error.main" }}>
                            <Stack spacing={1}>
                                {repoValidation.blocked_reasons.length > 0 ? (
                                    <Alert severity="error">
                                        {repoValidation.blocked_reasons.join(" ")}
                                    </Alert>
                                ) : null}
                                <Box sx={{ display: "grid", gap: 1, gridTemplateColumns: { xs: "1fr", sm: "repeat(2, minmax(0, 1fr))" } }}>
                                    <Box>
                                        <Typography variant="caption" color="text.secondary">Branch</Typography>
                                        <Typography variant="body2">{repoValidation.branch || "unknown"}</Typography>
                                    </Box>
                                    <Box>
                                        <Typography variant="caption" color="text.secondary">Worktree</Typography>
                                        <Typography variant="body2">{repoValidation.dirty ? "Uncommitted changes" : "Clean"}</Typography>
                                    </Box>
                                    <Box>
                                        <Typography variant="caption" color="text.secondary">Diff size</Typography>
                                        <Typography variant="body2">{Number(repoValidation.diff_bytes ?? 0).toLocaleString()} bytes</Typography>
                                    </Box>
                                    <Box>
                                        <Typography variant="caption" color="text.secondary">Last commit</Typography>
                                        <Typography variant="body2" sx={{ overflowWrap: "anywhere" }}>
                                            {repoValidation.last_commit || "None"}
                                        </Typography>
                                    </Box>
                                </Box>
                                <Box>
                                    <Typography variant="caption" color="text.secondary">Remotes</Typography>
                                    <Typography
                                        component="pre"
                                        variant="caption"
                                        sx={{ m: 0, whiteSpace: "pre-wrap", overflowWrap: "anywhere", fontFamily: "monospace" }}
                                    >
                                        {repoValidation.remotes || "No remotes configured"}
                                    </Typography>
                                </Box>
                                {repoValidation.status ? (
                                    <Box>
                                        <Typography variant="caption" color="text.secondary">Uncommitted changes</Typography>
                                        <Typography
                                            component="pre"
                                            variant="caption"
                                            sx={{ m: 0, maxHeight: 160, overflow: "auto", whiteSpace: "pre-wrap", fontFamily: "monospace" }}
                                        >
                                            {repoValidation.status}
                                        </Typography>
                                    </Box>
                                ) : null}
                            </Stack>
                        </Paper>
                    ) : null}
                    <TextField
                        select
                        label="Dirty worktree policy"
                        defaultValue="block"
                        helperText="Controls what agents do when the repo has uncommitted changes before creating a task branch."
                        {...register("dirty_worktree_policy")}
                    >
                        <MenuItem value="block">Block agent work</MenuItem>
                        <MenuItem value="warn">Warn on dirty worktree</MenuItem>
                        <MenuItem value="allow">Allow dirty worktree</MenuItem>
                    </TextField>
                    <TextField
                        label="Allowed branches"
                        helperText="Comma-separated branch patterns agents may start from or merge into."
                        {...register("allowed_branches")}
                    />
                    <TextField
                        label="File allowlist"
                        helperText="Comma-separated glob patterns agents may read/write."
                        {...register("file_allowlist")}
                    />
                    <TextField
                        label="File denylist"
                        helperText="Comma-separated glob patterns always blocked."
                        {...register("file_denylist")}
                    />
                    <TextField
                        label="Command allowlist"
                        helperText="Comma-separated executable names allowed via code execution."
                        {...register("command_allowlist")}
                    />
                    <TextField
                        label="Max diff bytes"
                        type="number"
                        inputProps={{ min: 1000, max: 5000000 }}
                        helperText="Allowed range: 1,000 to 5,000,000 bytes."
                        {...register("max_diff_bytes", { valueAsNumber: true })}
                    />
                    <TextField
                        select
                        label="Team"
                        value={selectedTeamProfileId}
                        onChange={(e) => setValue("team_profile_id", e.target.value)}
                        helperText={
                            teamProfiles.length > 0
                                ? "Team profile saved from team template."
                                : "No team profiles yet. Save one from a team template below."
                        }
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
                                    <MenuItem key={template.id} value={template.id}>
                                        {template.name}
                                    </MenuItem>
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
                    {mutation.isError && (
                        <Alert severity="error">
                            {mutation.error instanceof Error ? mutation.error.message : "Couldn't create project. Try again."}
                        </Alert>
                    )}
                    <Button type="submit" variant="contained" disabled={mutation.isPending || validateRepoMutation.isPending || repoValidationBlocked}>
                        Save
                    </Button>
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
                </Stack>
            </Drawer>
        </PageShell>
    );
}