import { API_BASE, ApiRequestError, apiFetch, readCookie } from "./client";
import { appendCursorParams, assertCursorPage, type CursorPage, type CursorToken } from "./pagination";

export type RagDocument = {
    document_id: string;
    source_id: string;
    source_type: string;
    title: string;
    owner_user_id: string;
    project_id: string;
    checksum: string;
    chunk_count: number;
    ingestion_status: string;
    metadata: Record<string, unknown>;
    created_at: string;
    updated_at: string;
};

export type RagChunkMatch = {
    chunk_id: string;
    document_id: string;
    title: string;
    content: string;
    chunk_index: number;
    score: number;
    hit_kind: string;
    metadata: Record<string, unknown>;
};

export type RagCitation = {
    source_index: number;
    chunk_id: string;
    document_id: string;
    title: string;
    chunk_index: number;
    score: number;
    excerpt: string;
};

export type RagAnswer = {
    query: string;
    answer: string;
    grounded: boolean;
    context_found: boolean;
    model: string;
    provider: string;
    citations: RagCitation[];
};

export type RagAnswerPayload = {
    query: string;
    task_id?: string;
    top_k?: number;
    include_decisions?: boolean;
};

export type RagAnswerStreamEvent =
    | { type: "meta"; query: string; context_found: boolean; citations: RagCitation[] }
    | { type: "token"; text: string }
    | ({ type: "done" } & Omit<RagAnswer, "query" | "citations"> & Partial<Pick<RagAnswer, "query" | "citations">>);

const projectPath = (projectId: string) => `/rag/projects/${encodeURIComponent(projectId)}`;

export async function listRagDocumentsPage(
    projectId: string,
    options: { taskId?: string; limit?: number; cursor?: CursorToken | null } = {},
): Promise<CursorPage<RagDocument>> {
    const params = new URLSearchParams();
    if (options.taskId) params.set("task_id", options.taskId);
    appendCursorParams(params, options);
    const query = params.size ? `?${params.toString()}` : "";
    const endpoint = `${projectPath(projectId)}/documents`;
    return assertCursorPage(await apiFetch(`${endpoint}${query}`), endpoint);
}

export async function listRagDocuments(projectId: string, taskId?: string): Promise<RagDocument[]> {
    return (await listRagDocumentsPage(projectId, { taskId })).items;
}

export async function getRagDocument(projectId: string, documentId: string): Promise<RagDocument> {
    return apiFetch(`${projectPath(projectId)}/documents/${encodeURIComponent(documentId)}`);
}

export async function createRagDocument(
    projectId: string,
    payload: {
        title: string;
        content: string;
        task_id?: string;
        source_type?: string;
        metadata?: Record<string, unknown>;
        ttl_days?: number;
        queue_async?: boolean;
    },
): Promise<RagDocument> {
    return apiFetch(`${projectPath(projectId)}/documents`, { method: "POST", body: JSON.stringify(payload) });
}

export async function bulkCreateRagDocuments(
    projectId: string,
    payload: {
        documents: Array<{
            title: string;
            content: string;
            source_type?: string;
            metadata?: Record<string, unknown>;
        }>;
        task_id?: string;
        queue_async?: boolean;
    },
): Promise<RagDocument[]> {
    return apiFetch(`${projectPath(projectId)}/documents/bulk`, {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

export async function uploadRagDocument(
    projectId: string,
    file: File,
    options: { taskId?: string; queueAsync?: boolean } = {},
): Promise<RagDocument> {
    const formData = new FormData();
    formData.append("file", file);
    const params = new URLSearchParams();
    if (options.taskId) params.set("task_id", options.taskId);
    if (options.queueAsync === false) params.set("queue_async", "false");
    const query = params.size ? `?${params.toString()}` : "";
    return apiFetch(`${projectPath(projectId)}/documents/upload${query}`, { method: "POST", body: formData });
}

export async function deleteRagDocument(projectId: string, documentId: string): Promise<void> {
    return apiFetch(`${projectPath(projectId)}/documents/${encodeURIComponent(documentId)}`, { method: "DELETE" });
}

export async function reindexRagDocument(
    projectId: string,
    documentId: string,
): Promise<{ document_id: string; chunk_count: number; status: string }> {
    return apiFetch(`${projectPath(projectId)}/documents/${encodeURIComponent(documentId)}/reindex`, {
        method: "POST",
    });
}

export async function searchRag(
    projectId: string,
    payload: RagAnswerPayload & { source_kind?: string },
): Promise<RagChunkMatch[]> {
    return apiFetch(`${projectPath(projectId)}/search`, { method: "POST", body: JSON.stringify(payload) });
}

export async function answerRag(projectId: string, payload: RagAnswerPayload): Promise<RagAnswer> {
    return apiFetch(`${projectPath(projectId)}/answer`, { method: "POST", body: JSON.stringify(payload) });
}

export function parseRagSseBlock(block: string): RagAnswerStreamEvent | null {
    const payload = block
        .split(/\r?\n/)
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trimStart())
        .join("\n");
    if (!payload) return null;
    return JSON.parse(payload) as RagAnswerStreamEvent;
}

export async function streamRagAnswer(
    projectId: string,
    payload: RagAnswerPayload,
    options: { signal: AbortSignal; onEvent: (event: RagAnswerStreamEvent) => void },
): Promise<void> {
    const headers = new Headers({ "Content-Type": "application/json" });
    const csrfToken = readCookie("csrf_token");
    if (csrfToken) headers.set("X-CSRF-Token", csrfToken);
    const response = await fetch(`${API_BASE}${projectPath(projectId)}/answer/stream`, {
        method: "POST",
        body: JSON.stringify(payload),
        credentials: "include",
        headers,
        signal: options.signal,
    });
    if (!response.ok) {
        const detail = await response.json().catch(() => ({ detail: "Streaming answer failed" }));
        const message = typeof detail?.detail === "string" ? detail.detail : "Streaming answer failed";
        throw new ApiRequestError(message, response.status, detail);
    }
    if (!response.body) throw new Error("This browser did not provide a streaming response body.");

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
        const { done, value } = await reader.read();
        buffer += decoder.decode(value, { stream: !done });
        const blocks = buffer.split(/\r?\n\r?\n/);
        buffer = blocks.pop() ?? "";
        for (const block of blocks) {
            const event = parseRagSseBlock(block);
            if (event) options.onEvent(event);
        }
        if (done) break;
    }
    const finalEvent = parseRagSseBlock(buffer);
    if (finalEvent) options.onEvent(finalEvent);
}
