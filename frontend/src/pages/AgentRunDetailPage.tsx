import { useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import {
    Alert,
    Box,
    Button,
    Chip,
    Paper,
    Stack,
    Typography,
} from "@mui/material";
import { CheckCircle as CheckCircleIcon, StopCircle as StopCircleIcon } from "@mui/icons-material";
import {
    approveAgentRunPlan,
    cancelAgentRun,
    getAgentRun,
    getOrchestrationTask,
    listAgentRunArtifacts,
    listAgentRunSteps,
} from "../api/orchestration";
import { PageShell } from "../components/ui/PageShell";
import { queryKeys } from "../config/queryKeys";

function planFromPayload(payload: Record<string, unknown>) {
    const maybePlan = payload.plan;
    return Array.isArray(maybePlan) ? maybePlan as Array<Record<string, unknown>> : [];
}

export default function AgentRunDetailPage() {
    const { runId = "" } = useParams();
    const queryClient = useQueryClient();
    const { data: run, error: runError } = useQuery({
        queryKey: queryKeys.agentRuns.detail(runId),
        queryFn: () => getAgentRun(runId),
        enabled: !!runId,
    });
    const { data: steps = [] } = useQuery({
        queryKey: queryKeys.agentRuns.steps(runId),
        queryFn: () => listAgentRunSteps(runId),
        enabled: !!runId,
        refetchInterval: run?.status === "running" ? 1500 : false,
    });
    const { data: artifacts = [] } = useQuery({
        queryKey: queryKeys.agentRuns.artifacts(runId),
        queryFn: () => listAgentRunArtifacts(runId),
        enabled: !!runId,
    });
    const { data: task } = useQuery({
        queryKey: queryKeys.agentRuns.task(runId, run?.task_id ?? undefined),
        queryFn: () => getOrchestrationTask(run!.project_id, run!.task_id!),
        enabled: !!run?.project_id && !!run?.task_id,
    });

    const plan = useMemo(() => planFromPayload(run?.output_payload ?? {}), [run?.output_payload]);
    const approveMutation = useMutation({
        mutationFn: () => approveAgentRunPlan(runId),
        onSuccess: () => {
            void queryClient.invalidateQueries({ queryKey: queryKeys.agentRuns.detail(runId) });
        },
    });
    const cancelMutation = useMutation({
        mutationFn: () => cancelAgentRun(runId),
        onSuccess: () => {
            void queryClient.invalidateQueries({ queryKey: queryKeys.agentRuns.detail(runId) });
        },
    });

    return (
        <PageShell maxWidth="lg">
            {runError && <Alert severity="error">{runError instanceof Error ? runError.message : "Run failed to load."}</Alert>}
            <Paper sx={{ p: { xs: 2.5, md: 3 }, borderRadius: 1 }}>
                <Stack direction={{ xs: "column", md: "row" }} justifyContent="space-between" spacing={2}>
                    <Box>
                        <Typography variant="overline" color="text.secondary">
                            Agent run
                        </Typography>
                        <Typography variant="h3">{task?.title ?? run?.id ?? "Run"}</Typography>
                        <Typography color="text.secondary" sx={{ mt: 1 }}>
                            {task?.description ?? "Plan approval, execution trace, and generated artifacts."}
                        </Typography>
                    </Box>
                    {run && <Chip label={run.status} color={run.status === "completed" ? "success" : run.status === "failed" ? "error" : "default"} />}
                </Stack>
            </Paper>

            {run?.status === "awaiting_approval" && (
                <Alert
                    severity="info"
                    action={
                        <Stack direction="row" spacing={1}>
                            <Button
                                color="inherit"
                                startIcon={<CheckCircleIcon />}
                                disabled={approveMutation.isPending}
                                onClick={() => approveMutation.mutate()}
                            >
                                Approve
                            </Button>
                            <Button
                                color="inherit"
                                startIcon={<StopCircleIcon />}
                                disabled={cancelMutation.isPending}
                                onClick={() => cancelMutation.mutate()}
                            >
                                Cancel
                            </Button>
                        </Stack>
                    }
                >
                    Plan must be approved before placeholder execution creates steps or artifacts.
                </Alert>
            )}

            <Paper sx={{ p: { xs: 2, md: 3 }, borderRadius: 1 }}>
                <Typography variant="h5">Generated plan</Typography>
                <Stack spacing={1.25} sx={{ mt: 2 }}>
                    {plan.map((step, index) => (
                        <Box key={`${step.id ?? index}`} sx={{ p: 1.5, border: 1, borderColor: "divider", borderRadius: 1 }}>
                            <Typography variant="subtitle2">{index + 1}. {String(step.title ?? step.id ?? "Step")}</Typography>
                            <Typography variant="body2" color="text.secondary">Actor: {String(step.actor ?? "system")}</Typography>
                        </Box>
                    ))}
                    {plan.length === 0 && <Typography color="text.secondary">No structured plan stored.</Typography>}
                </Stack>
            </Paper>

            <Paper sx={{ p: { xs: 2, md: 3 }, borderRadius: 1 }}>
                <Typography variant="h5">Step timeline</Typography>
                <Stack spacing={1.25} sx={{ mt: 2 }}>
                    {steps.map((step) => (
                        <Box key={step.id} sx={{ p: 1.5, border: 1, borderColor: "divider", borderRadius: 1 }}>
                            <Stack direction="row" justifyContent="space-between" spacing={2}>
                                <Typography variant="subtitle2">{step.event_type}</Typography>
                                <Chip size="small" label={step.level} />
                            </Stack>
                            <Typography variant="body2" color="text.secondary">{step.message}</Typography>
                        </Box>
                    ))}
                    {steps.length === 0 && <Typography color="text.secondary">No run events yet.</Typography>}
                </Stack>
            </Paper>

            <Paper sx={{ p: { xs: 2, md: 3 }, borderRadius: 1 }}>
                <Typography variant="h5">Artifacts</Typography>
                <Stack spacing={1.25} sx={{ mt: 2 }}>
                    {artifacts.map((artifact) => (
                        <Box key={artifact.id} sx={{ p: 1.5, border: 1, borderColor: "divider", borderRadius: 1 }}>
                            <Typography variant="subtitle2">{artifact.name}</Typography>
                            <Typography variant="body2" color="text.secondary">{artifact.type} · {artifact.path_or_url ?? "stored in database"}</Typography>
                        </Box>
                    ))}
                    {artifacts.length === 0 && <Typography color="text.secondary">No artifacts created.</Typography>}
                </Stack>
            </Paper>
        </PageShell>
    );
}
