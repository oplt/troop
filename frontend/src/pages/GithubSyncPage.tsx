import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
    Alert,
    Box,
    Button,
    Chip,
    IconButton,
    MenuItem,
    Paper,
    Stack,
    TextField,
    Typography,
} from "@mui/material";
import { useMemo, useState } from "react";
import {
    createGithubConnection,
    deleteGithubConnection,
    getGithubAppInstallUrl,
    importGithubIssues,
    listAgents,
    listGithubConnections,
    listGithubIssueLinks,
    listGithubRepositories,
    listGithubSyncEvents,
    listOrchestrationProjects,
    refreshGithubIssueLink,
    syncGithubRepositories,
    updateOrchestrationTask,
} from "../api/orchestration";
import { Close as CloseIcon } from "@mui/icons-material";
import { useSnackbar } from "../app/snackbarContext";
import { CollapsibleSectionCard } from "../components/ui/CollapsibleSectionCard";
import { PageHeader } from "../components/ui/PageHeader";
import { PageShell } from "../components/ui/PageShell";
import { SectionCard } from "../components/ui/SectionCard";
import { useLiveSnapshotStream } from "../hooks/useLiveSnapshotStream";

type LinkedIssueAssignmentFieldProps = {
    projectId: string;
    assignedAgentId: string;
    onAssign: (agentId: string) => void;
    disabled?: boolean;
};

function LinkedIssueAssignmentField({
    projectId,
    assignedAgentId,
    onAssign,
    disabled = false,
}: LinkedIssueAssignmentFieldProps) {
    const { data: projectAgents = [] } = useQuery({
        queryKey: ["orchestration", "agents", projectId],
        queryFn: () => listAgents(projectId),
        enabled: Boolean(projectId),
    });
    const visibleAgents = useMemo(
        () =>
            projectAgents.filter(
                (agent) => agent.slug.toLowerCase() !== "test" && agent.name.trim().toLowerCase() !== "test",
            ),
        [projectAgents],
    );

    return (
        <TextField
            select
            size="small"
            label="Assigned agent"
            value={assignedAgentId}
            onChange={(event) => onAssign(event.target.value)}
            disabled={disabled}
            sx={{ minWidth: 220 }}
        >
            <MenuItem value="">Unassigned</MenuItem>
            {visibleAgents.map((agent) => (
                <MenuItem key={agent.id} value={agent.id}>{agent.name}</MenuItem>
            ))}
        </TextField>
    );
}

export function GithubSyncPanel() {
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();
    const [connectionForm, setConnectionForm] = useState({ name: "", api_url: "https://api.github.com", token: "" });
    const [importForm, setImportForm] = useState({ project_id: "", repository_id: "", issue_numbers: "" });
    const [filters, setFilters] = useState({ project_id: "", repository_id: "", event_status: "", event_type: "", issue_status: "" });

    const { data: projects = [] } = useQuery({ queryKey: ["orchestration", "projects"], queryFn: listOrchestrationProjects });
    const { data: connections = [] } = useQuery({ queryKey: ["orchestration", "github", "connections"], queryFn: listGithubConnections });
    const { data: repositories = [] } = useQuery({ queryKey: ["orchestration", "github", "repositories"], queryFn: listGithubRepositories });
    const { data: issueLinks = [] } = useQuery({
        queryKey: ["orchestration", "github", "issues"],
        queryFn: () => listGithubIssueLinks(),
    });
    const { data: syncEvents = [] } = useQuery({
        queryKey: ["orchestration", "github", "events"],
        queryFn: () => listGithubSyncEvents(),
    });

    useLiveSnapshotStream("/orchestration/github/sync-events/stream", {
        onSnapshot: () => {
            void queryClient.invalidateQueries({ queryKey: ["orchestration", "github", "issues"] });
            void queryClient.invalidateQueries({ queryKey: ["orchestration", "github", "events"] });
        },
    });

    const installAppMutation = useMutation({
        mutationFn: getGithubAppInstallUrl,
        onSuccess: (data) => {
            window.location.href = data.install_url;
        },
        onError: (error) => {
            showToast({ message: error instanceof Error ? error.message : "Couldn't start GitHub App install. Check GitHub connectivity and retry.", severity: "error" });
        },
    });

    const connectionMutation = useMutation({
        mutationFn: createGithubConnection,
        onSuccess: async () => {
            setConnectionForm({ name: "", api_url: "https://api.github.com", token: "" });
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "github"] });
            showToast({ message: "GitHub connection saved.", severity: "success" });
        },
    });

    const syncReposMutation = useMutation({
        mutationFn: syncGithubRepositories,
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "github", "repositories"] });
        },
    });
    const deleteConnectionMutation = useMutation({
        mutationFn: deleteGithubConnection,
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "github"] });
            showToast({ message: "GitHub legacy token removed.", severity: "success" });
        },
        onError: (error) => {
            showToast({ message: error instanceof Error ? error.message : "Couldn't delete GitHub connection.", severity: "error" });
        },
    });

    const importMutation = useMutation({
        mutationFn: importGithubIssues,
        onSuccess: async (_, variables) => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "github"] });
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "project", variables.project_id] });
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "project", variables.project_id, "tasks"] });
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "project", variables.project_id, "issues"] });
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "project", variables.project_id, "sync-events"] });
            showToast({ message: "Issues imported into internal tasks.", severity: "success" });
        },
    });
    const assignMutation = useMutation({
        mutationFn: ({ projectId, taskId, agentId }: { projectId: string; taskId: string; agentId: string }) =>
            updateOrchestrationTask(projectId, taskId, { assigned_agent_id: agentId || null }),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "github", "issues"] });
            showToast({ message: "Issue assignment mirrored to internal task.", severity: "success" });
        },
    });
    const refreshIssueMutation = useMutation({
        mutationFn: refreshGithubIssueLink,
        onSuccess: async (_, issueLinkId) => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "github", "issues"] });
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "github", "events"] });
            const refreshed = issueLinks.find((item) => item.id === issueLinkId);
            const projectId = refreshed?.metadata?.project_id;
            if (typeof projectId === "string" && projectId) {
                await queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId] });
                await queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "tasks"] });
                await queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "issues"] });
            }
            showToast({ message: "Linked issue refreshed from GitHub.", severity: "success" });
        },
        onError: (error) => {
            showToast({ message: error instanceof Error ? error.message : "Couldn't refresh linked issue.", severity: "error" });
        },
    });
    const repositoryById = useMemo(
        () => new Map(repositories.map((repository) => [repository.id, repository])),
        [repositories],
    );
    const filteredIssueLinks = useMemo(
        () =>
            issueLinks.filter((item) => {
                if (filters.project_id && String(item.metadata?.project_id || "") !== filters.project_id) return false;
                if (filters.repository_id && item.repository_id !== filters.repository_id) return false;
                if (filters.issue_status && item.sync_status !== filters.issue_status) return false;
                return true;
            }),
        [filters.issue_status, filters.project_id, filters.repository_id, issueLinks],
    );
    const filteredSyncEvents = useMemo(
        () =>
            syncEvents.filter((event) => {
                if (filters.project_id && String(event.payload?.project_id || "") !== filters.project_id) return false;
                if (filters.repository_id && event.repository_id !== filters.repository_id) return false;
                if (filters.event_status && event.status !== filters.event_status) return false;
                if (filters.event_type && !event.action.includes(filters.event_type)) return false;
                return true;
            }),
        [filters.event_status, filters.event_type, filters.project_id, filters.repository_id, syncEvents],
    );
    const syncFailures = filteredSyncEvents.filter((event) => event.status === "failed" || event.status === "error");
    const retryQueue = filteredSyncEvents.filter((event) => event.status === "queued" || event.status === "pending");
    const branchViolations = filteredSyncEvents.filter((event) => event.action.includes("branch") || String(event.detail || "").toLowerCase().includes("branch"));
    const prSyncEvents = filteredSyncEvents.filter((event) => event.action.includes("pull_request") || event.action.includes("create_pr"));
    const issueHistoryRows = useMemo(
        () =>
            [...filteredIssueLinks].sort((left, right) => {
                const rightUpdated = new Date(right.updated_at || right.last_synced_at || right.created_at).getTime();
                const leftUpdated = new Date(left.updated_at || left.last_synced_at || left.created_at).getTime();
                return rightUpdated - leftUpdated;
            }),
        [filteredIssueLinks],
    );

    return (
        <Stack spacing={2}>
            <SectionCard title="Console filters" description="Narrow the sync console by project, repository, event type, or status.">
                <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                    <TextField select label="Project" value={filters.project_id} onChange={(event) => setFilters((current) => ({ ...current, project_id: event.target.value }))} fullWidth>
                        <MenuItem value="">All projects</MenuItem>
                        {projects.map((project) => <MenuItem key={project.id} value={project.id}>{project.name}</MenuItem>)}
                    </TextField>
                    <TextField select label="Repository" value={filters.repository_id} onChange={(event) => setFilters((current) => ({ ...current, repository_id: event.target.value }))} fullWidth>
                        <MenuItem value="">All repositories</MenuItem>
                        {repositories.map((repository) => <MenuItem key={repository.id} value={repository.id}>{repository.full_name}</MenuItem>)}
                    </TextField>
                    <TextField select label="Event status" value={filters.event_status} onChange={(event) => setFilters((current) => ({ ...current, event_status: event.target.value }))} fullWidth>
                        <MenuItem value="">All statuses</MenuItem>
                        {["queued", "pending", "completed", "failed"].map((status) => <MenuItem key={status} value={status}>{status}</MenuItem>)}
                    </TextField>
                    <TextField select label="Event type" value={filters.event_type} onChange={(event) => setFilters((current) => ({ ...current, event_type: event.target.value }))} fullWidth>
                        <MenuItem value="">All events</MenuItem>
                        {["issues", "issue_comment", "pull_request", "pull_request_review", "projects_v2_item", "branch"].map((value) => <MenuItem key={value} value={value}>{value}</MenuItem>)}
                    </TextField>
                </Stack>
            </SectionCard>

            <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", xl: "360px 360px minmax(0, 1fr)" } }}>
            <SectionCard title="Connection" description="GitHub App installations are the primary setup path. Legacy token mode remains available only as a fallback.">
                <Stack spacing={2}>
                    <Button variant="contained" onClick={() => installAppMutation.mutate()} disabled={installAppMutation.isPending}>
                        Install GitHub App
                    </Button>
                    <Typography variant="caption" color="text.secondary">
                        The install flow stores the GitHub App `installation_id` and uses installation tokens for API calls. Multiple org installs are supported as separate connections.
                    </Typography>
                    <TextField label="Legacy connection name" value={connectionForm.name} onChange={(event) => setConnectionForm((current) => ({ ...current, name: event.target.value }))} />
                    <TextField label="Legacy API URL" value={connectionForm.api_url} onChange={(event) => setConnectionForm((current) => ({ ...current, api_url: event.target.value }))} />
                    <TextField label="Legacy token" type="password" value={connectionForm.token} onChange={(event) => setConnectionForm((current) => ({ ...current, token: event.target.value }))} />
                    <Button variant="outlined" onClick={() => connectionMutation.mutate(connectionForm)} disabled={!connectionForm.name || !connectionForm.token}>
                        Save legacy token connection
                    </Button>
                    {connectionMutation.isError && <Alert severity="error">{connectionMutation.error instanceof Error ? connectionMutation.error.message : "Couldn't save GitHub connection. Verify token and retry."}</Alert>}
                    {connections.map((connection) => (
                        <Paper key={connection.id} sx={{ p: 1.5, borderRadius: 3 }}>
                            <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={1}>
                                <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap sx={{ mb: 0.5 }}>
                                    <Chip label={connection.connection_mode === "github_app" ? "GitHub App" : "Legacy token"} size="small" color="secondary" variant="outlined" />
                                    {connection.organization_login && <Chip label={connection.organization_login} size="small" variant="outlined" />}
                                </Stack>
                                {connection.connection_mode !== "github_app" ? (
                                    <IconButton
                                        size="small"
                                        color="error"
                                        aria-label={`Delete ${connection.name}`}
                                        onClick={() => deleteConnectionMutation.mutate(connection.id)}
                                        disabled={deleteConnectionMutation.isPending}
                                    >
                                        <CloseIcon fontSize="small" />
                                    </IconButton>
                                ) : null}
                            </Stack>
                            <Typography variant="subtitle2">{connection.name}</Typography>
                            <Typography variant="caption" color="text.secondary">
                                {connection.account_login || "Unknown account"} • {connection.connection_mode === "github_app" ? `installation ${connection.installation_id}` : connection.token_hint}
                            </Typography>
                            <Button size="small" sx={{ mt: 1, px: 0 }} onClick={() => syncReposMutation.mutate(connection.id)}>Sync repos</Button>
                        </Paper>
                    ))}
                </Stack>
            </SectionCard>

            <SectionCard title="Issue import" description="Convert GitHub issues into internal orchestration tasks.">
                <Stack spacing={2}>
                    <TextField select label="Project" value={importForm.project_id} onChange={(event) => setImportForm((current) => ({ ...current, project_id: event.target.value }))}>
                        {projects.map((project) => <MenuItem key={project.id} value={project.id}>{project.name}</MenuItem>)}
                    </TextField>
                    <TextField select label="Repository" value={importForm.repository_id} onChange={(event) => setImportForm((current) => ({ ...current, repository_id: event.target.value }))}>
                        {repositories.map((repository) => <MenuItem key={repository.id} value={repository.id}>{repository.full_name}</MenuItem>)}
                    </TextField>
                    <TextField label="Issue numbers" helperText="Comma-separated, blank means import current open issues." value={importForm.issue_numbers} onChange={(event) => setImportForm((current) => ({ ...current, issue_numbers: event.target.value }))} />
                    <Button
                        variant="contained"
                        onClick={() => importMutation.mutate({
                            project_id: importForm.project_id,
                            repository_id: importForm.repository_id,
                            issue_numbers: importForm.issue_numbers.split(",").map((value) => Number(value.trim())).filter((value) => !Number.isNaN(value)),
                        })}
                    >
                        Import issues
                    </Button>
                </Stack>
            </SectionCard>

            <Stack spacing={2}>
                <CollapsibleSectionCard
                    title="Repositories"
                    description="Connected repos, last sync state, and install coverage."
                    count={repositories.length}
                >
                    <Stack spacing={1.25}>
                        {repositories.map((repository) => (
                            <Paper key={repository.id} sx={{ p: 1.5, borderRadius: 3 }}>
                                <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap sx={{ mb: 0.5 }}>
                                    <Chip size="small" variant="outlined" label={repository.full_name} />
                                    {repository.project_id ? <Chip size="small" color="secondary" variant="outlined" label={`project ${repository.project_id.slice(0, 8)}`} /> : null}
                                    <Chip size="small" color={repository.is_active ? "success" : "default"} label={repository.is_active ? "active" : "inactive"} />
                                </Stack>
                                <Typography variant="caption" color="text.secondary">
                                    {repository.default_branch || "no default branch"} {repository.last_synced_at ? `• synced ${new Date(repository.last_synced_at).toLocaleString()}` : "• never synced"}
                                </Typography>
                            </Paper>
                        ))}
                    </Stack>
                </CollapsibleSectionCard>
                <CollapsibleSectionCard
                    title="Linked issues"
                    description="Current internal mapping between GitHub issues and orchestration tasks."
                    count={filteredIssueLinks.length}
                >
                    <Stack spacing={1.25}>
                        {filteredIssueLinks.map((item) => (
                            <Paper key={item.id} sx={{ p: 1.5, borderRadius: 3 }}>
                                <Typography variant="subtitle2">#{item.issue_number} {item.title}</Typography>
                                <Typography variant="caption" color="text.secondary">
                                    {repositoryById.get(item.repository_id)?.full_name || item.repository_id} • {item.state} • sync {item.sync_status} • task {item.task_id || "pending"}
                                </Typography>
                                <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
                                    Imported {new Date(String(item.metadata?.imported_at || item.created_at)).toLocaleString()} • Updated {new Date(item.updated_at || item.last_synced_at || item.created_at).toLocaleString()}
                                </Typography>
                                {item.last_error ? <Alert severity="error" sx={{ mt: 1 }}>{item.last_error}</Alert> : null}
                                <Stack direction={{ xs: "column", md: "row" }} spacing={1} sx={{ mt: 1 }}>
                                    {item.task_id && typeof item.metadata?.project_id === "string" ? (
                                        <LinkedIssueAssignmentField
                                            projectId={String(item.metadata.project_id)}
                                            assignedAgentId={String(item.metadata?.assigned_agent_id ?? "")}
                                            onAssign={(agentId) => assignMutation.mutate({
                                                projectId: String(item.metadata?.project_id),
                                                taskId: item.task_id!,
                                                agentId,
                                            })}
                                            disabled={assignMutation.isPending}
                                        />
                                    ) : null}
                                    <Button
                                        size="small"
                                        variant="outlined"
                                        onClick={() => refreshIssueMutation.mutate(item.id)}
                                        disabled={refreshIssueMutation.isPending}
                                    >
                                        Update
                                    </Button>
                                </Stack>
                            </Paper>
                        ))}
                    </Stack>
                </CollapsibleSectionCard>
                <CollapsibleSectionCard
                    title="Sync history"
                    description="One row per linked issue, showing when it was imported and when it was last updated."
                    count={issueHistoryRows.length}
                >
                    <Stack spacing={1.25}>
                        <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                            <Chip size="small" color="error" label={`Failures ${syncFailures.length}`} />
                            <Chip size="small" color="warning" label={`Retry queue ${retryQueue.length}`} />
                            <Chip size="small" color="info" label={`PR sync ${prSyncEvents.length}`} />
                            <Chip size="small" variant="outlined" label={`Branch violations ${branchViolations.length}`} />
                        </Stack>
                        {syncFailures.slice(0, 5).map((event) => (
                            <Alert key={event.id} severity="error">
                                {event.action} • {event.detail || "No detail available."}
                            </Alert>
                        ))}
                        {retryQueue.slice(0, 5).map((event) => (
                            <Alert key={event.id} severity="warning">
                                {event.action} waiting in queue.
                            </Alert>
                        ))}
                        {branchViolations.slice(0, 5).map((event) => (
                            <Alert key={event.id} severity="info">
                                {event.action} • {event.detail || "Branch policy signal detected."}
                            </Alert>
                        ))}
                        {issueHistoryRows.map((item) => (
                            <Paper key={item.id} sx={{ p: 1.25, borderRadius: 3 }}>
                                <Stack spacing={0.75}>
                                    <Typography variant="body2">
                                        #{item.issue_number} • {item.title} • {repositoryById.get(item.repository_id)?.full_name || item.repository_id}
                                    </Typography>
                                    <Typography variant="caption" color="text.secondary">
                                        Imported {new Date(String(item.metadata?.imported_at || item.created_at)).toLocaleString()} • Updated {new Date(item.updated_at || item.last_synced_at || item.created_at).toLocaleString()}
                                    </Typography>
                                    <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                                        <Chip size="small" variant="outlined" label={item.state} />
                                        <Chip size="small" variant="outlined" label={`sync ${item.sync_status}`} />
                                        <Chip size="small" variant="outlined" label={item.task_id ? `task ${item.task_id.slice(0, 8)}` : "task pending"} />
                                    </Stack>
                                    {item.last_error ? <Alert severity="error">{item.last_error}</Alert> : null}
                                </Stack>
                            </Paper>
                        ))}
                    </Stack>
                </CollapsibleSectionCard>
            </Stack>
        </Box>
        </Stack>
    );
}

export default function GithubSyncPage() {
    return (
        <PageShell maxWidth="xl">
            <PageHeader
                eyebrow="Integration"
                title="GitHub Sync"
                description="Connect repositories, sync issue metadata, import work into the platform, and review outbound sync activity."
            />
            <GithubSyncPanel />
        </PageShell>
    );
}
