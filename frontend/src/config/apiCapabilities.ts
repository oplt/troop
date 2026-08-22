import type { OpenApiPath } from "../api/generated/openapi";

export type CapabilityExposure = "ui-required" | "ui-advanced" | "api-only" | "internal" | "deprecated";

export type ApiCapability = {
    capability: string;
    endpoint: OpenApiPath;
    method: "GET" | "POST" | "PATCH" | "DELETE";
    exposure: CapabilityExposure;
    route: string;
    surface: string;
};

/** High-value user workflows. The generated audit carries operation-level coverage. */
export const API_CAPABILITIES = [
    { capability: "ai.runs.list", endpoint: "/api/v1/ai/runs", method: "GET", exposure: "ui-required", route: "/ai", surface: "test" },
    { capability: "ai.runs.inspect", endpoint: "/api/v1/ai/runs/{run_id}", method: "GET", exposure: "ui-required", route: "/ai", surface: "test" },
    { capability: "ai.runs.create", endpoint: "/api/v1/ai/runs", method: "POST", exposure: "ui-required", route: "/ai", surface: "test" },
    { capability: "ai.datasets.update", endpoint: "/api/v1/ai/evaluation-datasets/{dataset_id}", method: "PATCH", exposure: "ui-required", route: "/ai", surface: "test" },
    { capability: "ai.datasets.from-trace", endpoint: "/api/v1/ai/evaluation-datasets/{dataset_id}/cases/from-trace", method: "POST", exposure: "ui-required", route: "/runs/:runId", surface: "evaluation" },
    { capability: "rag.documents.list", endpoint: "/api/v1/rag/projects/{project_id}/documents", method: "GET", exposure: "ui-required", route: "/projects/:projectId", surface: "knowledge" },
    { capability: "rag.documents.bulk", endpoint: "/api/v1/rag/projects/{project_id}/documents/bulk", method: "POST", exposure: "ui-required", route: "/projects/:projectId", surface: "knowledge" },
    { capability: "rag.documents.reindex", endpoint: "/api/v1/rag/projects/{project_id}/documents/{document_id}/reindex", method: "POST", exposure: "ui-required", route: "/projects/:projectId", surface: "knowledge" },
    { capability: "rag.search", endpoint: "/api/v1/rag/projects/{project_id}/search", method: "POST", exposure: "ui-required", route: "/projects/:projectId", surface: "knowledge" },
    { capability: "rag.answer", endpoint: "/api/v1/rag/projects/{project_id}/answer", method: "POST", exposure: "ui-required", route: "/projects/:projectId", surface: "knowledge" },
    { capability: "rag.answer.stream", endpoint: "/api/v1/rag/projects/{project_id}/answer/stream", method: "POST", exposure: "ui-required", route: "/projects/:projectId", surface: "knowledge" },
    { capability: "memory.project.list", endpoint: "/api/v1/orchestration/projects/{project_id}/semantic-memory", method: "GET", exposure: "ui-required", route: "/projects/:projectId", surface: "knowledge" },
] as const satisfies readonly ApiCapability[];
