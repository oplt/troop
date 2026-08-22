import { apiFetch } from "./client";
import type { AiChunkMatch, AiDocument, AiDocumentIngestResponse } from "./aiTypes";
import { appendCursorParams, assertCursorPage, type CursorPage, type CursorToken } from "./pagination";

export async function listAiDocumentsPage(
    options: { limit?: number; cursor?: CursorToken | null } = {},
): Promise<CursorPage<AiDocument>> {
    const params = new URLSearchParams();
    appendCursorParams(params, options);
    const query = params.size ? `?${params.toString()}` : "";
    return assertCursorPage(await apiFetch(`/ai/documents${query}`), "/ai/documents");
}

export async function listAiDocuments(): Promise<AiDocument[]> {
    return (await listAiDocumentsPage()).items;
}

export async function createAiDocument(payload: {
    title: string;
    description?: string;
    content: string;
    content_type?: string;
    metadata?: Record<string, unknown>;
}): Promise<AiDocumentIngestResponse> {
    return apiFetch("/ai/documents", { method: "POST", body: JSON.stringify(payload) });
}

export async function getAiDocument(documentId: string): Promise<AiDocument> {
    return apiFetch(`/ai/documents/${documentId}`);
}

export async function uploadAiDocument(file: File, description?: string): Promise<AiDocumentIngestResponse> {
    const formData = new FormData();
    formData.append("file", file);
    if (description) formData.append("description", description);
    return apiFetch("/ai/documents/upload", { method: "POST", body: formData });
}

export async function retrieveAiChunks(payload: {
    query: string;
    document_ids: string[];
    top_k: number;
}): Promise<AiChunkMatch[]> {
    return apiFetch("/ai/retrieve", { method: "POST", body: JSON.stringify(payload) });
}
