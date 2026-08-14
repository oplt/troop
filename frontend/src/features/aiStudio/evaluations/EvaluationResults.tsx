import { Alert, Stack } from "@mui/material";

import type { AiEvaluationRun } from "../../../api/ai";
import { formatDateTime } from "../../../utils/formatters";

type EvaluationResultsProps = {
    evaluationRuns: AiEvaluationRun[];
};

export function EvaluationResults({ evaluationRuns }: EvaluationResultsProps) {
    if (evaluationRuns.length === 0) {
        return null;
    }

    return (
        <Stack spacing={1}>
            {evaluationRuns.map((run) => (
                <Alert key={run.id} severity={run.passed_cases === run.total_cases ? "success" : "warning"}>
                    {formatDateTime(run.created_at)}: {run.passed_cases}/{run.total_cases} passed, average score{" "}
                    {run.average_score}
                </Alert>
            ))}
        </Stack>
    );
}
