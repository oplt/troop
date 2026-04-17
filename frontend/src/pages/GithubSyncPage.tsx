import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
    Alert,
    Box,
    Button,
    Chip,
    MenuItem,
    Paper,
    Stack,
    TextField,
    Typography,
} from "@mui/material";
import { useState } from "react";
import {
    createGithubConnection,
    getGithubAppInstallUrl,
    importGithubIssues,
    listAgents,
    listGithubConnections,
    listGithubIssueLinks,
    listGithubRepositories,
    listGithubSyncEvents,
    listOrchestrationProjects,
    syncGithubRepositories,
    updateOrchestrationTask,
} from "../api/orchestration";
import { useSnackbar } from "../app/snackbarContext";
import { PageHeader } from "../components/ui/PageHeader";
import { PageShell } from "../components/ui/PageShell";
import { SectionCard } from "../components/ui/SectionCard";

export function GithubSyncPanel() {
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();
    const [connectionForm, setConnectionForm] = useState({ name: "", api_url: "https://api.github.com", token: "" });
    const [importForm, setImportForm] = useState({ project_id: "", repository_id: "", issue_numbers: "" });

    const { data: projects = [] } = useQuery({ queryKey: ["orchestration", "projects"], queryFn: listOrchestrationProjects });
    const { data: agents = [] } = useQuery({ queryKey: ["orchestration", "agents"], queryFn: () => listAgents() });
    const { data: connections = [] } = useQuery({ queryKey: ["orchestration", "github", "connections"], queryFn: listGithubConnections });
    const { data: repositories = [] } = useQuery({ queryKey: ["orchestration", "github", "repositories"], queryFn: listGithubRepositories });
    const { data: issueLinks = [] } = useQuery({
        queryKey: ["orchestration", "github", "issues"],
        queryFn: () => listGithubIssueLinks(),
        refetchInterval: 5000,
    });
    const { data: syncEvents = [] } = useQuery({
        queryKey: ["orchestration", "github", "events"],
        queryFn: () => listGithubSyncEvents(),
        refetchInterval: 5000,
    });

    const installAppMutation = useMutation({
        mutationFn: getGithubAppInstallUrl,
        onSuccess: (data) => {
            window.location.href = data.install_url;
        },
        onError: (error) => {
            showToast({ message: error instanceof Error ? error.message : "Failed to start GitHub App installation.", severity: "error" });
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

    const importMutation = useMutation({
        mutationFn: importGithubIssues,
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "github"] });
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "project"] });
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

    return (
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
                    {connectionMutation.isError && <Alert severity="error">{connectionMutation.error instanceof Error ? connectionMutation.error.message : "Failed to save connection."}</Alert>}
                    {connections.map((connection) => (
                        <Paper key={connection.id} sx={{ p: 1.5, borderRadius: 3 }}>
                            <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap sx={{ mb: 0.5 }}>
                                <Chip label={connection.connection_mode === "github_app" ? "GitHub App" : "Legacy token"} size="small" color="secondary" variant="outlined" />
                                {connection.organization_login && <Chip label={connection.organization_login} size="small" variant="outlined" />}
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
                <SectionCard title="Linked issues" description="Current internal mapping between GitHub issues and orchestration tasks.">
                    <Stack spacing={1.25}>
                        {issueLinks.map((item) => (
                            <Paper key={item.id} sx={{ p: 1.5, borderRadius: 3 }}>
                                <Typography variant="subtitle2">#{item.issue_number} {item.title}</Typography>
                                <Typography variant="caption" color="text.secondary">{item.state} • task {item.task_id || "pending"}</Typography>
                                {item.task_id && typeof item.metadata?.project_id === "string" && (
                                    <TextField
                                        select
                                        size="small"
                                        label="Assigned agent"
                                        value={String(item.metadata?.assigned_agent_id ?? "")}
                                        onChange={(event) => assignMutation.mutate({
                                            projectId: String(item.metadata.project_id),
                                            taskId: item.task_id!,
                                            agentId: event.target.value,
                                        })}
                                        sx={{ mt: 1, minWidth: 220 }}
                                    >
                                        <MenuItem value="">Unassigned</MenuItem>
                                        {agents.map((agent) => (
                                            <MenuItem key={agent.id} value={agent.id}>{agent.name}</MenuItem>
                                        ))}
                                    </TextField>
                                )}
                            </Paper>
                        ))}
                    </Stack>
                </SectionCard>
                <SectionCard title="Sync history" description="Auditable history for imports and outbound actions.">
                    <Stack spacing={1.25}>
                        {syncEvents.map((event) => (
                            <Box key={event.id}>
                                <Typography variant="body2">{event.action} • {event.status}</Typography>
                                <Typography variant="caption" color="text.secondary">{event.detail || "No detail available."}</Typography>
                            </Box>
                        ))}
                    </Stack>
                </SectionCard>
            </Stack>
        </Box>
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
