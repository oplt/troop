import { useForm, useWatch } from "react-hook-form";
import { useEffect, useMemo, useState, type MouseEvent } from "react";
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { listCompanies } from "../api/companies";
import { listDepartments, analyzeProject } from "../api/workforce";
import {
    Accordion,
    AccordionDetails,
    AccordionSummary,
    Alert,
    Box,
    Button,
    Chip,
    Drawer,
    IconButton,
    InputAdornment,
    LinearProgress,
    Menu,
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
    ExpandMore as ExpandMoreIcon,
    Hub as ProjectIcon,
    MoreVert as MoreIcon,
    PlayArrow as PlayArrowIcon,
    Refresh as RefreshIcon,
    Search as SearchIcon,
    WarningAmber as WarningAmberIcon,
} from "@mui/icons-material";
import { useNavigate, useSearchParams } from "react-router-dom";
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
import { ConfirmDestructiveDialog } from "../components/ui/ConfirmDestructiveDialog";
import { PageShell } from "../components/ui/PageShell";
import { PageHeader } from "../components/ui/PageHeader";
import { FilterToolbar } from "../components/ui/FilterToolbar";
import { SectionCard } from "../components/ui/SectionCard";
import { StatusChip } from "../components/ui/StatusChip";
import { formatDate, formatDateTime, humanizeKey } from "../utils/formatters";

type ProjectForm = {
    name: string;
    slug: string;
    description: string;
    goals_markdown: string;
    company_id: string;
    team_profile_id: string;
    department_id: string;
    local_repo_path: string;
    dirty_worktree_policy: string;
    allowed_branches: string;
    file_allowlist: string;
    file_denylist: string;
    command_allowlist: string;
    max_diff_bytes: number;
};

type SortKey = "last_active" | "name" | "created";
type StatusFilter = "all" | "active" | "running" | "completed" | "archived" | "attention";

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
            department_id: "",
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
    const selectedDepartmentId = useWatch({ control, name: "department_id" }) || "";
    const selectedTeamProfileId = useWatch({ control, name: "team_profile_id" });
    const { data: departments = [] } = useQuery({
        queryKey: ["workforce", "departments", selectedCompanyId],
        queryFn: () => listDepartments(selectedCompanyId),
        enabled: Boolean(selectedCompanyId),
    });
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
    const [statusFilter, setStatusFilter] = useState<StatusFilter>("active");
    const [statusFilterTouched, setStatusFilterTouched] = useState(false);
    const [bootstrapPrompt, setBootstrapPrompt] = useState("");
    const [bootstrapDraft, setBootstrapDraft] = useState<Record<string, unknown> | null>(null);
    const [createMode, setCreateMode] = useState<"manual" | "generate">("manual");
    const [createStep, setCreateStep] = useState<1 | 2>(1);
    const [showRepoDetails, setShowRepoDetails] = useState(false);
    const [projectMenuAnchor, setProjectMenuAnchor] = useState<HTMLElement | null>(null);
    const [projectMenuProjectId, setProjectMenuProjectId] = useState<string | null>(null);
    const [deleteProjectTarget, setDeleteProjectTarget] = useState<{ id: string; name: string } | null>(null);
    const [advancedRepoOpen, setAdvancedRepoOpen] = useState(false);

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

    const latestRunByProject = useMemo(() => {
        const map = new Map<string, typeof runs[number]>();
        for (const run of runs) {
            const prev = map.get(run.project_id);
            if (!prev || new Date(run.created_at).getTime() > new Date(prev.created_at).getTime()) {
                map.set(run.project_id, run);
            }
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

    const attentionProjects = useMemo(
        () =>
            projects.filter((project) => {
                const failedRuns = failedRunCountByProject.get(project.id) ?? 0;
                return failedRuns > 0;
            }),
        [projects, failedRunCountByProject],
    );

    const effectiveStatusFilter: StatusFilter = statusFilterTouched
        ? statusFilter
        : attentionProjects.length > 0
            ? "attention"
            : "active";

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
                effectiveStatusFilter === "all" ||
                (effectiveStatusFilter === "active" && !["archived", "completed"].includes(project.status)) ||
                (effectiveStatusFilter === "running" && activeRuns > 0) ||
                project.status === effectiveStatusFilter ||
                (effectiveStatusFilter === "attention" && failedRuns > 0);
            return matchesQuery && matchesStatus;
        });
    }, [projects, searchQuery, effectiveStatusFilter, activeRunCountByProject, failedRunCountByProject]);

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

    const dashboardStats = useMemo(() => {
        const activeProjects = projects.filter((project) => !["archived", "completed"].includes(project.status)).length;
        const runningRuns = runs.filter((run) => ["queued", "in_progress"].includes(run.status)).length;
        const failedRuns = runs.filter((run) => ["failed", "error", "cancelled"].includes(run.status)).length;
        return { activeProjects, runningRuns, failedRuns };
    }, [projects, runs]);

    function selectStatusFilter(nextFilter: StatusFilter) {
        setStatusFilter(nextFilter);
        setStatusFilterTouched(true);
    }

    const mutation = useMutation({
        mutationFn: createOrchestrationProject,
        onSuccess: async (project) => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "projects"] });
            reset();
            showToast({ message: "Project created.", severity: "success" });
            
            const shouldAnalyze = window.confirm("Analyze this project with AI to identify skills and agents?");
            if (shouldAnalyze) {
                try {
                    await analyzeProject(project.id);
                    showToast({ message: "Project analysis started.", severity: "success" });
                } catch (error) {
                    showToast({ message: `Analysis failed: ${(error as Error).message}`, severity: "warning" });
                }
            }
            
            navigate(`/projects/${project.id}`);
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
            navigate(`/projects/${project.id}`);
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
    const [searchParams, setSearchParams] = useSearchParams();
    const createFromQuery = searchParams.get("create") === "1";
    const [trackedCreateFromQuery, setTrackedCreateFromQuery] = useState(createFromQuery);

    if (createFromQuery !== trackedCreateFromQuery) {
        setTrackedCreateFromQuery(createFromQuery);
        if (createFromQuery) {
            setCreateMode("manual");
            setCreateStep(1);
            setDrawerOpen(true);
        }
    }

    useEffect(() => {
        if (!createFromQuery) {
            return;
        }
        const next = new URLSearchParams(searchParams);
        next.delete("create");
        setSearchParams(next, { replace: true });
    }, [createFromQuery, searchParams, setSearchParams]);

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
            ...(values.company_id ? { company_id: values.company_id } : {}),
            ...(values.department_id ? { department_id: values.department_id } : {}),
            settings: {
                ...(values.team_profile_id
                    ? { execution: { team_profile_id: values.team_profile_id } }
                    : {}),
                local_repo: localRepo,
            },
        });
    });

    return (
        <PageShell variant="browse">
            <Stack spacing={3}>
                <PageHeader
                    title="Projects"
                    description="Find active work, resume runs, and spot projects that need attention."
                    actions={
                        <>
                            <Button variant="outlined" startIcon={<RefreshIcon />} onClick={() => queryClient.invalidateQueries({ queryKey: ["orchestration"] })}>
                                Refresh
                            </Button>
                            <Button variant="contained" startIcon={<ProjectIcon />} onClick={() => setDrawerOpen(true)}>
                                New project
                            </Button>
                        </>
                    }
                />

                <FilterToolbar>
                    <TextField
                        size="small"
                        placeholder="Search projects"
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        InputProps={{
                            startAdornment: (
                                <InputAdornment position="start">
                                    <SearchIcon fontSize="small" />
                                </InputAdornment>
                            ),
                        }}
                        sx={{ minWidth: { sm: 220 }, flex: 1 }}
                    />
                    <TextField
                        select
                        size="small"
                        label="Status"
                        value={statusFilter}
                        onChange={(e) => {
                            setStatusFilterTouched(true);
                            setStatusFilter(e.target.value as StatusFilter);
                        }}
                        sx={{ minWidth: 150 }}
                    >
                        <MenuItem value="all">All</MenuItem>
                        <MenuItem value="active">Active</MenuItem>
                        <MenuItem value="running">Running</MenuItem>
                        <MenuItem value="attention">Needs attention</MenuItem>
                        <MenuItem value="completed">Completed</MenuItem>
                        <MenuItem value="archived">Archived</MenuItem>
                    </TextField>
                    <TextField
                        select
                        size="small"
                        label="Sort by"
                        value={sortKey}
                        onChange={(e) => setSortKey(e.target.value as SortKey)}
                        sx={{ minWidth: 170 }}
                    >
                        <MenuItem value="last_active">Last activity</MenuItem>
                        <MenuItem value="name">Name</MenuItem>
                        <MenuItem value="created">Recently created</MenuItem>
                    </TextField>
                </FilterToolbar>

                <SectionCard density="plain">
                    <Box sx={{ display: "grid", gap: 1, gridTemplateColumns: { xs: "1fr", sm: "repeat(3, 1fr)" }, mb: 2 }}>
                            {[
                                { label: "Active", value: dashboardStats.activeProjects, icon: <ProjectIcon fontSize="small" />, filter: "active" as const },
                                { label: "Running", value: dashboardStats.runningRuns, icon: <PlayArrowIcon fontSize="small" />, filter: "running" as const },
                                { label: "Attention", value: dashboardStats.failedRuns, icon: <WarningAmberIcon fontSize="small" />, filter: "attention" as const },
                            ].map((item) => (
                                <Paper
                                    key={item.label}
                                    component="button"
                                    type="button"
                                    variant="outlined"
                                    onClick={() => selectStatusFilter(item.filter)}
                                    sx={{
                                        p: 1.5,
                                        borderRadius: 1,
                                        borderColor: effectiveStatusFilter === item.filter ? "primary.main" : "divider",
                                        bgcolor: effectiveStatusFilter === item.filter ? "action.selected" : "background.paper",
                                        cursor: "pointer",
                                        textAlign: "left",
                                    }}
                                >
                                    <Stack direction="row" spacing={1.25} alignItems="center">
                                        <Box sx={{ display: "grid", placeItems: "center", width: 32, height: 32, borderRadius: 1.5, bgcolor: "action.hover" }}>
                                            {item.icon}
                                        </Box>
                                        <Box>
                                            <Typography variant="h6" sx={{ fontWeight: 500, lineHeight: 1.1 }}>
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

                    {projects.length === 0 ? (
                        <EmptyState
                            icon={<ProjectIcon />}
                            title="No projects yet"
                            description="Start from a blank project or generate one from a short description."
                            action={
                                <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
                                    <Button variant="contained" startIcon={<ProjectIcon />} onClick={() => { setCreateMode("manual"); setDrawerOpen(true); }}>
                                        New project
                                    </Button>
                                    <Button variant="outlined" onClick={() => { setCreateMode("generate"); setDrawerOpen(true); }}>
                                        Generate from description
                                    </Button>
                                </Stack>
                            }
                        />
                    ) : sortedProjects.length === 0 ? (
                        <EmptyState icon={<SearchIcon />} title="No matching projects" description="Clear search or adjust view." />
                    ) : (
                        <Stack spacing={1}>
                            <Box
                                sx={{
                                    display: { xs: "none", md: "grid" },
                                    gridTemplateColumns: "minmax(220px, 1.5fr) 130px 160px 160px minmax(120px, 1fr) 130px 44px",
                                    gap: 1.5,
                                    px: 2,
                                    py: 1,
                                }}
                            >
                                {["Project", "Status", "Active run", "Last activity", "Repo", "Action", ""].map((heading) => (
                                    <Typography key={heading} variant="caption" color="text.secondary" sx={{ fontWeight: 500 }}>
                                        {heading}
                                    </Typography>
                                ))}
                            </Box>
                            {sortedProjects.map((project) => {
                                const agentCount = agentCountByProject.get(project.id) ?? 0;
                                const activeRuns = activeRunCountByProject.get(project.id) ?? 0;
                                const failedRuns = failedRunCountByProject.get(project.id) ?? 0;
                                const lastRun = latestRunByProject.get(project.id);
                                const lastRunMs = lastRunAtByProject.get(project.id);
                                const localRepo = project.settings?.local_repo as { enabled?: boolean; repo_path?: string } | undefined;
                                const statusKey = failedRuns > 0 ? "needs_attention" : activeRuns > 0 ? "running" : project.status;
                                const actionLabel = activeRuns > 0 ? "Resume" : "Open";
                                return (
                                    <Paper
                                        key={project.id}
                                        variant="outlined"
                                        sx={{
                                            p: { xs: 1.5, md: 0 },
                                            borderRadius: 1,
                                            overflow: "hidden",
                                            transition: "border-color 0.33s, background-color 0.33s",
                                            "&:hover": { borderColor: "primary.main", backgroundColor: "grey.50" },
                                        }}
                                    >
                                        <Box
                                            sx={{
                                                display: "grid",
                                                gridTemplateColumns: { xs: "1fr", md: "minmax(220px, 1.5fr) 130px 160px 160px minmax(120px, 1fr) 130px 44px" },
                                                gap: { xs: 1, md: 1.5 },
                                                alignItems: "center",
                                                px: { xs: 0, md: 2 },
                                                py: { xs: 0, md: 1.5 },
                                            }}
                                        >
                                            <Box sx={{ minWidth: 0 }}>
                                                <Typography variant="subtitle2" sx={{ fontWeight: 500 }} noWrap>
                                                    {project.name}
                                                </Typography>
                                                <Typography
                                                    variant="body2"
                                                    color="text.secondary"
                                                    sx={{
                                                        overflow: "hidden",
                                                        textOverflow: "ellipsis",
                                                        whiteSpace: "nowrap",
                                                    }}
                                                >
                                                    {project.description || "No description"}
                                                </Typography>
                                                <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap sx={{ mt: 0.75, display: { md: "none" } }}>
                                                    <StatusChip
                                                        status={statusKey}
                                                        kind="project"
                                                        label={failedRuns > 0 ? "Needs attention" : humanizeKey(project.status)}
                                                        variant={failedRuns > 0 || activeRuns > 0 ? "filled" : "outlined"}
                                                    />
                                                    <Chip size="small" variant="outlined" label={`${activeRuns} active`} />
                                                    <Chip size="small" variant="outlined" label={`${agentCount} agents`} />
                                                </Stack>
                                            </Box>

                                            <Box sx={{ display: { xs: "none", md: "block" } }}>
                                                <StatusChip
                                                    status={statusKey}
                                                    kind="project"
                                                    label={failedRuns > 0 ? "Needs attention" : humanizeKey(project.status)}
                                                    variant={failedRuns > 0 || activeRuns > 0 ? "filled" : "outlined"}
                                                />
                                            </Box>

                                            <Typography variant="body2" color={activeRuns > 0 ? "warning.main" : "text.secondary"}>
                                                {activeRuns > 0 ? `${activeRuns} running` : lastRun ? humanizeKey(lastRun.status) : "No runs"}
                                            </Typography>

                                            <Typography variant="body2" color="text.secondary">
                                                {lastRunMs != null ? formatDateTime(new Date(lastRunMs).toISOString()) : formatDate(project.updated_at)}
                                            </Typography>

                                            <Typography variant="body2" color="text.secondary" noWrap>
                                                {localRepo?.enabled ? localRepo.repo_path ?? "Local repo" : "None"}
                                            </Typography>

                                            <Button size="small" variant={activeRuns > 0 ? "contained" : "outlined"} startIcon={<PlayArrowIcon />} onClick={() => navigate(`/projects/${project.id}`)}>
                                                {actionLabel}
                                            </Button>

                                            <Tooltip title="Project actions">
                                                <IconButton
                                                    size="small"
                                                    onClick={(event: MouseEvent<HTMLElement>) => {
                                                        setProjectMenuAnchor(event.currentTarget);
                                                        setProjectMenuProjectId(project.id);
                                                    }}
                                                >
                                                    <MoreIcon fontSize="small" />
                                                </IconButton>
                                            </Tooltip>
                                        </Box>
                                    </Paper>
                                );
                            })}
                        </Stack>
                    )}
                </SectionCard>
            </Stack>
            <Menu
                anchorEl={projectMenuAnchor}
                open={Boolean(projectMenuAnchor)}
                onClose={() => {
                    setProjectMenuAnchor(null);
                    setProjectMenuProjectId(null);
                }}
            >
                {(() => {
                    const project = projects.find((item) => item.id === projectMenuProjectId);
                    if (!project) return null;
                    return [
                        project.status !== "archived" ? (
                            <MenuItem
                                key="archive"
                                onClick={() => {
                                    archiveProjectMutation.mutate(project.id);
                                    setProjectMenuAnchor(null);
                                    setProjectMenuProjectId(null);
                                }}
                            >
                                <ArchiveIcon fontSize="small" sx={{ mr: 1 }} />
                                Archive
                            </MenuItem>
                        ) : null,
                        <MenuItem
                            key="delete"
                            sx={{ color: "error.main" }}
                            onClick={() => {
                                setDeleteProjectTarget({ id: project.id, name: project.name });
                                setProjectMenuAnchor(null);
                                setProjectMenuProjectId(null);
                            }}
                        >
                            <DeleteIcon fontSize="small" sx={{ mr: 1 }} />
                            Delete
                        </MenuItem>,
                    ];
                })()}
            </Menu>
            <ConfirmDestructiveDialog
                open={Boolean(deleteProjectTarget)}
                title="Delete project"
                description={
                    deleteProjectTarget
                        ? `Delete “${deleteProjectTarget.name}” permanently? Tasks, runs, and board history for this project are removed.`
                        : ""
                }
                confirmLabel="Delete project"
                loading={deleteProjectMutation.isPending}
                onClose={() => setDeleteProjectTarget(null)}
                onConfirm={() => {
                    if (!deleteProjectTarget) return;
                    deleteProjectMutation.mutate(deleteProjectTarget.id, {
                        onSettled: () => setDeleteProjectTarget(null),
                    });
                }}
            />
            <Drawer
                anchor="right"
                open={drawerOpen}
                onClose={() => setDrawerOpen(false)}
                PaperProps={{
                    sx: {
                        width: 540,
                        maxWidth: "100vw",
                        p: 3,
                    },
                }}
            >
                <Stack spacing={2} component="form" onSubmit={submitProject} sx={{ width: "100%" }}>
                    <input type="hidden" {...register("team_profile_id")} />
                    <Box>
                        <Typography variant="h6" sx={{ fontWeight: 500 }}>
                            New project
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                            Start blank or generate a draft plan.
                        </Typography>
                    </Box>

                    <Stack direction="row" spacing={1}>
                        <Button
                            variant={createMode === "manual" ? "contained" : "outlined"}
                            onClick={() => setCreateMode("manual")}
                            fullWidth
                        >
                            Blank project
                        </Button>
                        <Button
                            variant={createMode === "generate" ? "contained" : "outlined"}
                            onClick={() => setCreateMode("generate")}
                            fullWidth
                        >
                            Generate
                        </Button>
                    </Stack>

                    {createMode === "generate" ? (
                        <Stack spacing={1.5}>
                            <TextField
                                label="Project description"
                                placeholder='e.g. "Build a REST API for payments"'
                                value={bootstrapPrompt}
                                onChange={(e) => setBootstrapPrompt(e.target.value)}
                                multiline
                                minRows={4}
                            />
                            <Button
                                variant="outlined"
                                disabled={!bootstrapPrompt.trim() || bootstrapMutation.isPending}
                                onClick={() => bootstrapMutation.mutate()}
                            >
                                Generate draft plan
                            </Button>
                            {bootstrapDraft && (
                                <Paper sx={{ p: 1.5, borderRadius: 1, border: 1, borderColor: "divider" }}>
                                    <Typography variant="body2" color="text.secondary">
                                        Draft ready with goals, milestones, and starter tasks.
                                    </Typography>
                                    <Button
                                        size="small"
                                        sx={{ mt: 1 }}
                                        variant="contained"
                                        onClick={() => applyBootstrapMutation.mutate()}
                                        disabled={applyBootstrapMutation.isPending}
                                    >
                                        Create from draft
                                    </Button>
                                </Paper>
                            )}
                        </Stack>
                    ) : (
                        <>
                            <Stack direction="row" spacing={1} alignItems="center">
                                <Chip size="small" color={createStep === 1 ? "primary" : "default"} label="1. Basics" />
                                <Chip size="small" color={createStep === 2 ? "primary" : "default"} label="2. Optional setup" />
                            </Stack>

                            {createStep === 1 ? (
                                <Stack spacing={2}>
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
                                        helperText={companies.length === 0 ? "A default workspace will be created." : "Scopes company memory."}
                                    >
                                        {companies.map((c) => (
                                            <MenuItem key={c.id} value={c.id}>
                                                {c.name}
                                            </MenuItem>
                                        ))}
                                        {companies.length === 0 && <MenuItem value="">Default workspace</MenuItem>}
                                    </TextField>
                                    <TextField label="Description" {...register("description")} multiline minRows={3} />
                                    <TextField label="Goals" {...register("goals_markdown")} multiline minRows={4} />
                                    <Button variant="contained" onClick={() => setCreateStep(2)}>
                                        Continue
                                    </Button>
                                </Stack>
                            ) : (
                                <Stack spacing={2}>
                                    <Box>
                                        <Typography variant="subtitle2">Local repo</Typography>
                                        <Typography variant="body2" color="text.secondary">
                                            Optional for code-change projects.
                                        </Typography>
                                    </Box>
                                    <TextField
                                        label="Local repo path"
                                        placeholder="/home/polat/Desktop/Projects/my-repo"
                                        helperText="Leave blank for planning or knowledge-only projects."
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
                                            <Chip icon={<CheckCircleIcon />} color="success" variant="outlined" label="Ready" />
                                        ) : null}
                                        {hasLocalRepoPath && repoValidation && !repoValidation.valid ? (
                                            <Chip icon={<ErrorOutlineIcon />} color="error" variant="outlined" label="Blocked" />
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
                                        <Paper sx={{ p: 1.5, borderRadius: 1, border: 1, borderColor: repoValidation.valid ? "success.main" : "error.main" }}>
                                            <Stack spacing={1}>
                                                {repoValidation.blocked_reasons.length > 0 ? (
                                                    <Alert severity="error">
                                                        {repoValidation.blocked_reasons.join(" ")}
                                                    </Alert>
                                                ) : null}
                                                <Box sx={{ display: "grid", gap: 1, gridTemplateColumns: "repeat(2, minmax(0, 1fr))" }}>
                                                    <Box>
                                                        <Typography variant="caption" color="text.secondary">Branch</Typography>
                                                        <Typography variant="body2">{repoValidation.branch || "unknown"}</Typography>
                                                    </Box>
                                                    <Box>
                                                        <Typography variant="caption" color="text.secondary">Worktree</Typography>
                                                        <Typography variant="body2">{repoValidation.dirty ? "Uncommitted" : "Clean"}</Typography>
                                                    </Box>
                                                    <Box>
                                                        <Typography variant="caption" color="text.secondary">Diff size</Typography>
                                                        <Typography variant="body2">{Number(repoValidation.diff_bytes ?? 0).toLocaleString()} bytes</Typography>
                                                    </Box>
                                                    <Box>
                                                        <Typography variant="caption" color="text.secondary">Remotes</Typography>
                                                        <Typography variant="body2">{repoValidation.remotes ? "Configured" : "None"}</Typography>
                                                    </Box>
                                                </Box>
                                                <Button size="small" variant="text" onClick={() => setShowRepoDetails((value) => !value)}>
                                                    {showRepoDetails ? "Hide details" : "View details"}
                                                </Button>
                                                {showRepoDetails ? (
                                                    <Stack spacing={1}>
                                                        <Typography variant="caption" color="text.secondary">Last commit</Typography>
                                                        <Typography variant="caption" sx={{ overflowWrap: "anywhere" }}>
                                                            {repoValidation.last_commit || "None"}
                                                        </Typography>
                                                        <Typography variant="caption" color="text.secondary">Remotes</Typography>
                                                        <Typography component="pre" variant="caption" sx={{ m: 0, whiteSpace: "pre-wrap", overflowWrap: "anywhere", fontFamily: "monospace" }}>
                                                            {repoValidation.remotes || "No remotes configured"}
                                                        </Typography>
                                                        {repoValidation.status ? (
                                                            <>
                                                                <Typography variant="caption" color="text.secondary">Uncommitted changes</Typography>
                                                                <Typography component="pre" variant="caption" sx={{ m: 0, maxHeight: 160, overflow: "auto", whiteSpace: "pre-wrap", fontFamily: "monospace" }}>
                                                                    {repoValidation.status}
                                                                </Typography>
                                                            </>
                                                        ) : null}
                                                    </Stack>
                                                ) : null}
                                            </Stack>
                                        </Paper>
                                    ) : null}

                                    <Accordion
                                        expanded={advancedRepoOpen}
                                        onChange={(_, expanded) => setAdvancedRepoOpen(expanded)}
                                        disableGutters
                                        elevation={0}
                                        sx={{ border: 1, borderColor: "divider", borderRadius: 1, "&:before": { display: "none" } }}
                                    >
                                        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                                            <Typography variant="subtitle2">Advanced repo safeguards</Typography>
                                        </AccordionSummary>
                                        <AccordionDetails>
                                            <Stack spacing={2}>
                                                <TextField
                                                    select
                                                    label="Dirty worktree policy"
                                                    defaultValue="block"
                                                    helperText="Controls agent work when the repo has uncommitted changes."
                                                    {...register("dirty_worktree_policy")}
                                                >
                                                    <MenuItem value="block">Block agent work</MenuItem>
                                                    <MenuItem value="warn">Warn on dirty worktree</MenuItem>
                                                    <MenuItem value="allow">Allow dirty worktree</MenuItem>
                                                </TextField>
                                                <TextField label="Allowed branches" helperText="Comma-separated branch patterns." {...register("allowed_branches")} />
                                                <TextField label="File allowlist" helperText="Comma-separated glob patterns agents may read/write." {...register("file_allowlist")} />
                                                <TextField label="File denylist" helperText="Comma-separated glob patterns always blocked." {...register("file_denylist")} />
                                                <TextField label="Command allowlist" helperText="Comma-separated executable names allowed via code execution." {...register("command_allowlist")} />
                                                <TextField
                                                    label="Max diff bytes"
                                                    type="number"
                                                    inputProps={{ min: 1000, max: 5000000 }}
                                                    helperText="Allowed range: 1,000 to 5,000,000 bytes."
                                                    {...register("max_diff_bytes", { valueAsNumber: true })}
                                                />
                                            </Stack>
                                        </AccordionDetails>
                                    </Accordion>

                                    <TextField
                                        select
                                        label="Team"
                                        value={selectedTeamProfileId}
                                        onChange={(e) => setValue("team_profile_id", e.target.value)}
                                        helperText={teamProfiles.length > 0 ? "Optional execution team." : "Save a team profile from a template if needed."}
                                    >
                                        <MenuItem value="">None</MenuItem>
                                        {teamProfiles.map((profile) => (
                                            <MenuItem key={profile.id} value={profile.id}>
                                                {profile.name}
                                            </MenuItem>
                                        ))}
                                    </TextField>
                                    <TextField
                                        select
                                        label="Department"
                                        value={selectedDepartmentId}
                                        onChange={(e) => setValue("department_id", e.target.value)}
                                        helperText="Optional department for organizational tracking"
                                        fullWidth
                                    >
                                        <MenuItem value="">None</MenuItem>
                                        {departments.map((dept) => (
                                            <MenuItem key={dept.id} value={dept.id}>
                                                {dept.name}
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
                                    <Stack direction="row" spacing={1}>
                                        <Button variant="outlined" onClick={() => setCreateStep(1)} fullWidth>
                                            Back
                                        </Button>
                                        <Button type="submit" variant="contained" disabled={mutation.isPending || validateRepoMutation.isPending || repoValidationBlocked} fullWidth>
                                            Save project
                                        </Button>
                                    </Stack>
                                </Stack>
                            )}
                        </>
                    )}
                </Stack>
            </Drawer>
        </PageShell>
    );
}
