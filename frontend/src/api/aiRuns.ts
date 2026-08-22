import { apiFetch } from "./client";
import type { AiFeedback, AiReviewItem, AiRun } from "./aiTypes";
import { appendCursorParams, assertCursorPage, type CursorPage, type CursorToken } from "./pagination";

export type CreateAiRunPayload = {
    prompt_template_key?: string;
    prompt_version_id?: string;
    variables: Record<string, unknown>;
    retrieval_query?: string;
    document_ids: string[];
    top_k: number;
    review_required: boolean;
};

export async function listAiRunsPage(
    options: { limit?: number; cursor?: CursorToken | null } = {},
): Promise<CursorPage<AiRun>> {
    const params = new URLSearchParams();
    appendCursorParams(params, options);
    const query = params.size ? `?${params.toString()}` : "";
    return assertCursorPage(await apiFetch(`/ai/runs${query}`), "/ai/runs");
}

export async function listAiRuns(): Promise<AiRun[]> {
    return (await listAiRunsPage()).items;
}

export async function getAiRun(runId: string): Promise<AiRun> {
    return apiFetch(`/ai/runs/${encodeURIComponent(runId)}`);
}

export async function createAiRun(payload: CreateAiRunPayload, queueAsync = false): Promise<AiRun> {
    const query = queueAsync ? "?queue_async=true" : "";
    return apiFetch(`/ai/runs${query}`, { method: "POST", body: JSON.stringify(payload) });
}

export async function listAiReviews(): Promise<AiReviewItem[]> {
    return apiFetch("/ai/reviews");
}

export async function createAiReview(
    runId: string,
    payload: { assigned_to_user_id?: string | null } = {},
): Promise<AiReviewItem> {
    return apiFetch(`/ai/runs/${runId}/reviews`, { method: "POST", body: JSON.stringify(payload) });
}

export async function decideAiReview(
    reviewId: string,
    payload: {
        status: "approved" | "rejected" | "changes_requested";
        reviewer_notes?: string;
        corrected_output?: string;
    },
): Promise<AiReviewItem> {
    return apiFetch(`/ai/reviews/${reviewId}/decision`, { method: "POST", body: JSON.stringify(payload) });
}

export async function listAiFeedback(runId: string): Promise<AiFeedback[]> {
    return apiFetch(`/ai/runs/${runId}/feedback`);
}

export async function createAiFeedback(
    runId: string,
    payload: { rating: -1 | 1; comment?: string; corrected_output?: string },
): Promise<AiFeedback> {
    return apiFetch(`/ai/runs/${runId}/feedback`, { method: "POST", body: JSON.stringify(payload) });
}
