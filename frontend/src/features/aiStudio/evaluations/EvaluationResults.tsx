import { Alert, Chip, Stack, Typography } from "@mui/material";

import type { AiEvaluationRun } from "../../../api/ai";
import { formatDateTime } from "../../../utils/formatters";

type EvaluationResultsProps = {
    evaluationRuns: AiEvaluationRun[];
};

function recommendationColor(
    recommendation: string | undefined,
): "success" | "warning" | "error" | "default" {
    if (recommendation === "approve") return "success";
    if (recommendation === "review") return "warning";
    if (recommendation === "block") return "error";
    return "default";
}

function numericMetric(metrics: Record<string, unknown>, key: string): number {
    const value = metrics[key];
    return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

export function EvaluationResults({ evaluationRuns }: EvaluationResultsProps) {
    if (evaluationRuns.length === 0) {
        return null;
    }

    return (
        <Stack spacing={1}>
            {evaluationRuns.map((run) => {
                const recommendation = run.scorecard?.regression?.publish_recommendation;
                const metrics = run.metrics;
                return (
                    <Alert
                        key={run.id}
                        severity={run.passed_cases === run.total_cases ? "success" : "warning"}
                    >
                        <Stack spacing={0.75}>
                            <Typography variant="body2">
                                {formatDateTime(run.created_at)}: {run.passed_cases}/{run.total_cases} passed · avg score{" "}
                                {run.average_score}
                            </Typography>
                            {metrics && (
                                <Typography variant="caption" color="text.secondary">
                                    Success {Math.round(numericMetric(metrics, "task_success_rate") * 100)}% · schema{" "}
                                    {Math.round(numericMetric(metrics, "schema_validity_rate") * 100)}% · latency{" "}
                                    {numericMetric(metrics, "avg_latency_ms")} ms · tokens{" "}
                                    {numericMetric(metrics, "total_tokens")}
                                </Typography>
                            )}
                            <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                                {recommendation && (
                                    <Chip
                                        size="small"
                                        label={`Publish: ${recommendation}`}
                                        color={recommendationColor(recommendation)}
                                    />
                                )}
                                {run.scorecard?.regression?.detected && (
                                    <Chip size="small" color="error" variant="outlined" label="Regression detected" />
                                )}
                                {run.judge_version_id && (
                                    <Chip size="small" variant="outlined" label={`Judge ${run.judge_version_id}`} />
                                )}
                            </Stack>
                        </Stack>
                    </Alert>
                );
            })}
        </Stack>
    );
}
