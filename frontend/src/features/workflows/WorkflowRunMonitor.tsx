import { Alert, Box, Chip, CircularProgress, Paper, Stack, Typography } from "@mui/material";
import type { WorkflowStepRun } from "../../api/integrations";
import { formatDateTime, humanizeKey } from "../../utils/formatters";
import { safeRunValue } from "./builderState";

export function WorkflowStepTimeline({ steps }: { steps: WorkflowStepRun[] }) {
    if (!steps.length) return <Alert severity="info">No workflow steps have been recorded yet.</Alert>;
    return (
        <Stack component="ol" spacing={1} sx={{ m: 0, pl: 3 }}>
            {steps.map((step) => {
                const started = step.started_at ? new Date(step.started_at).getTime() : null;
                const finished = step.finished_at ? new Date(step.finished_at).getTime() : null;
                const duration = started !== null && finished !== null ? Math.max(0, finished - started) : null;
                const output = step.output_json ?? {};
                const nestedResult = output.result && typeof output.result === "object"
                    ? (output.result as Record<string, unknown>)
                    : null;
                const simulated = output.simulated === true || nestedResult?.simulated === true;
                return (
                    <Paper component="li" key={step.id} variant="outlined" sx={{ p: 1.5, borderRadius: 1 }}>
                        <Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" gap={1}>
                            <Box>
                                <Typography variant="subtitle2">{step.node_id} · {humanizeKey(step.node_type)}</Typography>
                                <Typography variant="caption" color="text.secondary">
                                    {step.started_at ? formatDateTime(step.started_at) : "Not started"}
                                    {duration !== null ? ` · ${duration} ms` : ""} · retries {step.retry_count}
                                </Typography>
                            </Box>
                            <Stack direction="row" spacing={0.75}>
                                {simulated && <Chip label="simulated" size="small" color="secondary" variant="outlined" />}
                                <Chip label={humanizeKey(step.status)} size="small" color={step.status === "completed" || step.status === "succeeded" ? "success" : step.status === "failed" ? "error" : step.status.includes("waiting") ? "warning" : "default"} />
                            </Stack>
                        </Stack>
                        {step.error && <Alert severity="error" sx={{ mt: 1 }}>{step.error}</Alert>}
                        {(Object.keys(step.input_json).length > 0 || Object.keys(step.output_json).length > 0) && (
                            <Box component="pre" sx={{ mt: 1, mb: 0, p: 1, bgcolor: "action.hover", borderRadius: 1, overflow: "auto", fontSize: "0.72rem", whiteSpace: "pre-wrap" }}>
                                {JSON.stringify(safeRunValue({ input: step.input_json, output: step.output_json }), null, 2)}
                            </Box>
                        )}
                    </Paper>
                );
            })}
        </Stack>
    );
}

export function WorkflowRunMonitor({
    runId,
    loading,
    error,
    steps,
}: {
    runId: string;
    loading: boolean;
    error: boolean;
    steps: WorkflowStepRun[];
}) {
    return (
        <Paper component="section" aria-labelledby="workflow-run-heading" variant="outlined" sx={{ p: 2, borderRadius: 1 }}>
            <Typography id="workflow-run-heading" variant="h6">Workflow run {runId.slice(0, 8)}</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                Live node overlay reflects step status. Metadata is redacted before rendering.
            </Typography>
            {loading ? <CircularProgress size={24} /> : error ? (
                <Alert severity="warning">The workflow step endpoint is not available on this server yet.</Alert>
            ) : (
                <WorkflowStepTimeline steps={steps} />
            )}
        </Paper>
    );
}
