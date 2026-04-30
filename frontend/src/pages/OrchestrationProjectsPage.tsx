import { useForm, useWatch } from "react-hook-form";
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
    Drawer,
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
    CheckCircle as CheckCircleIcon,
    Delete as DeleteIcon,
    ErrorOutline as ErrorOutlineIcon,
    ExpandLess as ExpandLessIcon,
    ExpandMore as ExpandMoreIcon,
    Hub as ProjectIcon,
    Refresh as RefreshIcon,
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
    return {
        enabled: Boolean(repoPath),
        repo_path: repoPath,
        dirty_worktree_policy: values.dirty_worktree_policy || "block",
        allowed_branches: splitList(values.allowed_branches),
        file_allowlist: splitList(values.file_allowlist),
        file_denylist: splitList(values.file_denylist),
        command_allowlist: splitList(values.command_allowlist),
        max_diff_bytes: Math.max(1, Math.floor(Number(values.max_diff_bytes) || 200000)),
        task_branch_prefix: "troop",
        auto_merge_on_success: true,
        merge_target_branch: "main",
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
            allowed_branches: "main, master, develop, troop/*",
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
        const list = [...projects];
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


            <Box
                sx={{
                    display: "grid",
                    gap: 2,
                    gridTemplateColumns: "1fr",
                    alignItems: "start",
                }}

            >
                <Stack spacing={2}>
                    <Paper sx={{ p: 2, borderRadius: 3 }}>
                        <Stack direction={{ xs: "column", sm: "row" }} spacing={2} alignItems={{ sm: "center" }}>
                            <Button variant="contained" color="primary" onClick={() => setDrawerOpen(true)} sx={{ mb: 3 }}>
                                New project
                            </Button>
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
                                                            const localRepo = project.settings.local_repo as { enabled?: boolean; repo_path?: string; dirty_worktree_policy?: string } | undefined;
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
                                                                            {localRepo?.enabled ? (
                                                                                <Chip size="small" variant="outlined" label={`Repo: ${localRepo.repo_path ?? "local"}`} />
                                                                            ) : null}
                                                                        </Stack>
                                                                        {localRepo?.enabled ? (
                                                                            <Typography variant="caption" color="text.secondary">
                                                                                Dirty policy: {humanizeKey(String(localRepo.dirty_worktree_policy ?? "block"))}
                                                                            </Typography>
                                                                        ) : null}
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
                        label="Slug"
                        helperText="Lowercase letters, numbers, dashes. Auto-generated from name if blank."
                        inputProps={{ maxLength: 255, pattern: "[a-z0-9][a-z0-9\\-]*" }}
                        {...register("slug", { pattern: /^[a-z0-9][a-z0-9-]*$/ })}
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
                        inputProps={{ min: 1 }}
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
