import { apiFetch } from "./client";
import type { AiEvaluationCase, AiEvaluationDataset, AiEvaluationRun } from "./aiTypes";
import { appendCursorParams, assertCursorPage, type CursorPage, type CursorToken } from "./pagination";

export type CreateAiDatasetCaseFromTracePayload = {
    run_id: string;
    source_trace_span_id?: string | null;
    correction?: Record<string, unknown> | null;
    expected_assertions?: Record<string, unknown> | null;
    notes?: string | null;
};

export async function listAiDatasets(): Promise<AiEvaluationDataset[]> {
    return apiFetch("/ai/evaluation-datasets");
}

export async function createAiDataset(payload: {
    name: string;
    description?: string;
}): Promise<AiEvaluationDataset> {
    return apiFetch("/ai/evaluation-datasets", { method: "POST", body: JSON.stringify(payload) });
}

export async function updateAiDataset(
    datasetId: string,
    payload: Partial<{ name: string; description: string | null }>,
): Promise<AiEvaluationDataset> {
    return apiFetch(`/ai/evaluation-datasets/${datasetId}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export async function listAiDatasetCases(datasetId: string): Promise<AiEvaluationCase[]> {
    return apiFetch(`/ai/evaluation-datasets/${datasetId}/cases`);
}

export async function createAiDatasetCase(
    datasetId: string,
    payload: {
        input_variables: Record<string, unknown>;
        expected_output_text?: string | null;
        expected_output_json?: Record<string, unknown> | null;
        expected_assertions?: Record<string, unknown> | null;
        notes?: string | null;
    },
): Promise<AiEvaluationCase> {
    return apiFetch(`/ai/evaluation-datasets/${datasetId}/cases`, {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

export async function createAiDatasetCaseFromTrace(
    datasetId: string,
    payload: CreateAiDatasetCaseFromTracePayload,
): Promise<AiEvaluationCase> {
    return apiFetch(`/ai/evaluation-datasets/${datasetId}/cases/from-trace`, {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

export async function listAiEvaluationRunsPage(
    options: { limit?: number; cursor?: CursorToken | null } = {},
): Promise<CursorPage<AiEvaluationRun>> {
    const params = new URLSearchParams();
    appendCursorParams(params, options);
    const query = params.size ? `?${params.toString()}` : "";
    return assertCursorPage(
        await apiFetch(`/ai/evaluation-runs${query}`),
        "/ai/evaluation-runs",
    );
}

export async function listAiEvaluationRuns(): Promise<AiEvaluationRun[]> {
    return (await listAiEvaluationRunsPage()).items;
}

export async function getAiEvaluationRun(evaluationRunId: string): Promise<AiEvaluationRun> {
    return apiFetch(`/ai/evaluation-runs/${encodeURIComponent(evaluationRunId)}`);
}

export async function getAiEvaluationScorecard(evaluationRunId: string): Promise<AiEvaluationRun["scorecard"]> {
    return apiFetch(`/ai/evaluation-runs/${encodeURIComponent(evaluationRunId)}/scorecard`);
}

export async function runAiEvaluation(
    datasetId: string,
    payload: {
        prompt_version_id: string;
        baseline_run_id?: string | null;
        workflow_version_id?: string | null;
        model_name?: string | null;
        qualitative_rubric?: Record<string, unknown> | null;
        regression_threshold?: number;
    },
): Promise<AiEvaluationRun> {
    return apiFetch(`/ai/evaluation-datasets/${datasetId}/run`, {
        method: "POST",
        body: JSON.stringify(payload),
    });
}
