import { Box, Button, Chip, Paper, Skeleton, Stack, Typography } from "@mui/material";
import { useNavigate } from "react-router-dom";

import type { GithubSyncEvent, OrchestrationProject, TaskRun } from "../../../api/orchestration";
import { SectionCard } from "../../../components/ui/SectionCard";
import { StatusChip } from "../../../components/ui/StatusChip";
import { formatDateTime, humanizeKey } from "../../../utils/formatters";

type RunLedgerPanelProps = {
    runs: TaskRun[];
    syncEvents: GithubSyncEvent[];
    projects: OrchestrationProject[];
    isRunsLoading: boolean;
    isSyncLoading: boolean;
};

export function RunLedgerPanel({
    runs,
    syncEvents,
    projects,
    isRunsLoading,
    isSyncLoading,
}: RunLedgerPanelProps) {
    const navigate = useNavigate();

    return (
        <Stack spacing={2}>
            <SectionCard
                title="Runs"
                description="Execution history with model and token metadata. Use Inspect for the live event stream."
            >
                {isRunsLoading && (
                    <Stack spacing={1.5} role="status" aria-busy="true" aria-label="Loading runs">
                        <Skeleton variant="rounded" height={72} sx={{ borderRadius: 1 }} />
                        <Skeleton variant="rounded" height={72} sx={{ borderRadius: 1 }} />
                    </Stack>
                )}
                <Stack spacing={1.5}>
                    {runs.map((run) => (
                        <Paper key={run.id} sx={{ p: 2, borderRadius: 1 }}>
                            <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
                                <Box>
                                    <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                                        <Chip label={humanizeKey(run.run_mode)} size="small" variant="outlined" />
                                        <StatusChip status={run.status} kind="run" size="small" />
                                    </Stack>
                                    <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                                        {run.model_name || "default model"} • {run.token_total.toLocaleString()} tokens •{" "}
                                        {run.latency_ms ?? 0} ms
                                    </Typography>
                                    <Typography variant="caption" color="text.secondary">
                                        Project {projects.find((p) => p.id === run.project_id)?.name ?? run.project_id.slice(0, 8)} •{" "}
                                        {formatDateTime(run.created_at)}
                                    </Typography>
                                </Box>
                                <Button size="small" variant="outlined" onClick={() => navigate(`/runs/${run.id}`)}>
                                    Inspect
                                </Button>
                            </Stack>
                        </Paper>
                    ))}
                    {runs.length === 0 && !isRunsLoading && (
                        <Typography variant="body2" color="text.secondary">
                            No runs match the current filters.
                        </Typography>
                    )}
                </Stack>
            </SectionCard>

            <SectionCard title="GitHub sync events" description="Webhook and sync pipeline activity (filtered by date only).">
                {isSyncLoading && (
                    <Skeleton variant="rounded" height={56} sx={{ borderRadius: 1 }} aria-label="Loading sync events" />
                )}
                <Stack spacing={1.25}>
                    {syncEvents.map((event) => (
                        <Paper key={event.id} sx={{ p: 1.5, borderRadius: 1 }}>
                            <Typography variant="body2">
                                {event.action} • {event.status}
                            </Typography>
                            <Typography variant="caption" color="text.secondary">
                                {event.detail || "—"} • {formatDateTime(event.created_at)}
                            </Typography>
                        </Paper>
                    ))}
                    {syncEvents.length === 0 && !isSyncLoading && (
                        <Typography variant="body2" color="text.secondary">
                            No sync events in range.
                        </Typography>
                    )}
                </Stack>
            </SectionCard>
        </Stack>
    );
}
