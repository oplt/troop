import { apiFetch } from "../client";

export type KnowledgeSearchResult = {
    hit_kind?: "chunk" | "decision";
    document_id: string;
    chunk_id: string;
    filename: string;
    chunk_index: number;
    score: number;
    content: string;
    metadata: Record<string, unknown>;
    decision_id?: string | null;
};

export type AgentMemoryEntry = {
    id: string;
    owner_id: string;
    agent_id: string;
    project_id: string | null;
    source_run_id: string | null;
    key: string;
    value_text: string;
    scope: string;
    status: string;
    approved_by_user_id: string | null;
    ttl_days: number | null;
    expires_at: string | null;
    deleted_at: string | null;
    metadata: Record<string, unknown>;
    created_at: string;
    updated_at: string;
};

export type AgentMemoryWriteResult = AgentMemoryEntry | PendingSemanticWriteResponse;

export type SemanticMemoryEntry = {
    id: string;
    owner_id: string;
    scope: string;
    company_id?: string | null;
    project_id: string | null;
    agent_id: string | null;
    entry_type: string;
    namespace: string;
    title: string;
    body: string;
    metadata: Record<string, unknown>;
    source_chunk_id: string | null;
    source_task_id: string | null;
    source_run_id: string | null;
    provenance: Record<string, unknown>;
    confidence: number;
    created_by_user_id: string | null;
    ttl_days: number | null;
    expires_at: string | null;
    deleted_at: string | null;
    retention_policy: string;
    memory_version: number;
    embedding_model: string | null;
    embedding_version: string | null;
    created_at: string;
    updated_at: string;
};

export type ProjectMemorySettings = {
    auto_promote_decisions: boolean;
    auto_promote_approved_agent_memory: boolean;
    auto_ingest_bypasses_semantic_approval: boolean;
    second_stage_rag: boolean;
    semantic_write_requires_approval: boolean;
    episodic_retrieval_depth: number;
    episodic_retention_days: number;
    episodic_archive_enabled: boolean;
    episodic_delete_index_after_archive: boolean;
    task_close_auto_promote_working_memory: boolean;
    enable_semantic_vector_search: boolean;
    enable_episodic_vector_search: boolean;
    deep_recall_mode: boolean;
    deep_recall_episodic_candidates: number;
    classifier_worker_enabled: boolean;
    compaction_on_task_close_enabled: boolean;
    task_close_archive_unpromoted_memory: boolean;
    task_close_low_value_archive_days: number;
    default_ttl_days: number;
    max_ttl_days: number;
    context_max_tokens: number;
};

/** Returned when semantic writes require human approval (HTTP 202). */

export type PendingSemanticWriteResponse = {
    pending: true;
    approval_id: string;
    approval_type: string;
};

export function isPendingSemanticWrite(
    r: unknown
): r is PendingSemanticWriteResponse {
    return (
        typeof r === "object" &&
        r !== null &&
        "pending" in r &&
        (r as PendingSemanticWriteResponse).pending === true &&
        typeof (r as PendingSemanticWriteResponse).approval_id === "string"
    );
}

export async function getProjectMemorySettings(projectId: string): Promise<ProjectMemorySettings> {
    return apiFetch(`/orchestration/projects/${projectId}/memory-settings`);
}

export async function patchProjectMemorySettings(
    projectId: string,
    patch: Partial<ProjectMemorySettings>
): Promise<ProjectMemorySettings> {
    return apiFetch(`/orchestration/projects/${projectId}/memory-settings`, {
        method: "PATCH",
        body: JSON.stringify(patch),
    });
}

export async function listSemanticMemory(
    projectId: string,
    params?: {
        q?: string;
        vec_q?: string;
        entry_type?: string;
        namespace_prefix?: string;
        source_task_id?: string;
        limit?: number;
    }
): Promise<SemanticMemoryEntry[]> {
    const sp = new URLSearchParams();
    if (params?.q) sp.set("q", params.q);
    if (params?.vec_q) sp.set("vec_q", params.vec_q);
    if (params?.entry_type) sp.set("entry_type", params.entry_type);
    if (params?.namespace_prefix) sp.set("namespace_prefix", params.namespace_prefix);
    if (params?.source_task_id) sp.set("source_task_id", params.source_task_id);
    if (params?.limit != null) sp.set("limit", String(params.limit));
    const qs = sp.toString();
    return apiFetch(
        `/orchestration/projects/${projectId}/semantic-memory${qs ? `?${qs}` : ""}`
    );
}

export async function listCompanySemanticMemory(
    companyId: string,
    params?: {
        q?: string;
        entry_type?: string;
        namespace_prefix?: string;
        limit?: number;
    }
): Promise<SemanticMemoryEntry[]> {
    const sp = new URLSearchParams();
    if (params?.q) sp.set("q", params.q);
    if (params?.entry_type) sp.set("entry_type", params.entry_type);
    if (params?.namespace_prefix) sp.set("namespace_prefix", params.namespace_prefix);
    if (params?.limit != null) sp.set("limit", String(params.limit));
    const qs = sp.toString();
    return apiFetch(`/orchestration/companies/${companyId}/semantic-memory${qs ? `?${qs}` : ""}`);
}

export type ProceduralPlaybook = {
    id: string;
    owner_id: string;
    project_id: string;
    slug: string;
    title: string;
    body_md: string;
    version: number;
    tags: string[];
    namespace: string;
    created_at: string;
    updated_at: string;
};

export async function listProceduralPlaybooks(projectId: string): Promise<ProceduralPlaybook[]> {
    return apiFetch(`/orchestration/projects/${projectId}/procedural-playbooks`);
}

export type TaskMemoryCoordination = {
    shared: string;
    private: Record<string, string>;
};

export async function getTaskMemoryCoordination(
    projectId: string,
    taskId: string
): Promise<TaskMemoryCoordination> {
    return apiFetch(`/orchestration/projects/${projectId}/tasks/${taskId}/memory-coordination`);
}

export async function patchTaskMemoryCoordination(
    projectId: string,
    taskId: string,
    patch: { shared?: string; private?: Record<string, string> }
): Promise<TaskMemoryCoordination> {
    return apiFetch(`/orchestration/projects/${projectId}/tasks/${taskId}/memory-coordination`, {
        method: "PATCH",
        body: JSON.stringify(patch),
    });
}

export async function createSemanticMemory(
    projectId: string,
    body: {
        entry_type: string;
        title: string;
        body: string;
        scope?: string;
        namespace?: string | null;
        metadata?: Record<string, unknown>;
        ttl_days?: number;
        retention_policy?: string;
    }
): Promise<SemanticMemoryEntry | PendingSemanticWriteResponse> {
    return apiFetch(`/orchestration/projects/${projectId}/semantic-memory`, {
        method: "POST",
        body: JSON.stringify(body),
    });
}

export async function promoteWorkingMemoryToSemantic(
    projectId: string,
    payload: { run_id: string; entry_type?: string; title?: string | null }
): Promise<SemanticMemoryEntry> {
    return apiFetch(
        `/orchestration/projects/${projectId}/semantic-memory/promote-from-working-memory`,
        { method: "POST", body: JSON.stringify(payload) }
    );
}

export async function deleteSemanticMemory(
    projectId: string,
    entryId: string
): Promise<void | PendingSemanticWriteResponse> {
    return apiFetch(`/orchestration/projects/${projectId}/semantic-memory/${entryId}`, {
        method: "DELETE",
    });
}

export type SemanticConflictGroup = {
    group_key: string;
    kind?: "title_duplicate" | "duplicate" | "contradicts" | string;
    similarity?: number | null;
    reason?: string | null;
    entries: Array<{
        id: string;
        title: string | null;
        namespace: string;
        updated_at: string;
    }>;
};

export async function listSemanticMemoryConflicts(
    projectId: string
): Promise<SemanticConflictGroup[]> {
    return apiFetch(`/orchestration/projects/${projectId}/semantic-memory/conflicts`);
}

export async function mergeSemanticMemoryEntries(
    projectId: string,
    body: {
        canonical_entry_id: string;
        merge_entry_ids: string[];
        link_relation?: string;
    }
): Promise<SemanticMemoryEntry> {
    return apiFetch(`/orchestration/projects/${projectId}/semantic-memory/merge`, {
        method: "POST",
        body: JSON.stringify(body),
    });
}

export type KnowledgeGraphEdge = {
    id: string;
    owner_id: string;
    project_id: string;
    source_kind: string;
    source_id: string;
    target_kind: string;
    target_id: string;
    relation_type: string;
    metadata: Record<string, unknown>;
    created_at: string;
};

export async function listKnowledgeGraphEdges(
    projectId: string,
    params:
        | { source_kind: string; source_id: string; limit?: number }
        | { target_kind: string; target_id: string; limit?: number }
): Promise<KnowledgeGraphEdge[]> {
    const sp = new URLSearchParams();
    if ("source_kind" in params) {
        sp.set("source_kind", params.source_kind);
        sp.set("source_id", params.source_id);
    } else {
        sp.set("target_kind", params.target_kind);
        sp.set("target_id", params.target_id);
    }
    if (params.limit != null) sp.set("limit", String(params.limit));
    const qs = sp.toString();
    return apiFetch(`/orchestration/projects/${projectId}/knowledge-graph/edges?${qs}`);
}

export async function createKnowledgeGraphEdge(
    projectId: string,
    body: {
        source_kind: string;
        source_id: string;
        target_kind: string;
        target_id: string;
        relation_type: string;
        metadata?: Record<string, unknown>;
    }
): Promise<KnowledgeGraphEdge> {
    return apiFetch(`/orchestration/projects/${projectId}/knowledge-graph/edges`, {
        method: "POST",
        body: JSON.stringify(body),
    });
}

export async function deleteKnowledgeGraphEdge(projectId: string, edgeId: string): Promise<void> {
    return apiFetch(`/orchestration/projects/${projectId}/knowledge-graph/edges/${edgeId}`, {
        method: "DELETE",
    });
}

export type EpisodicSearchResponse = { hits: Array<Record<string, unknown>> };

export async function searchEpisodicMemory(
    projectId: string,
    params?: {
        q?: string;
        vec_q?: string;
        limit?: number;
        since?: string;
        until?: string;
        task_id?: string;
        kinds?: string;
    }
): Promise<EpisodicSearchResponse> {
    const sp = new URLSearchParams();
    if (params?.q) sp.set("q", params.q);
    if (params?.vec_q) sp.set("vec_q", params.vec_q);
    if (params?.limit != null) sp.set("limit", String(params.limit));
    if (params?.since) sp.set("since", params.since);
    if (params?.until) sp.set("until", params.until);
    if (params?.task_id) sp.set("task_id", params.task_id);
    if (params?.kinds) sp.set("kinds", params.kinds);
    const qs = sp.toString();
    return apiFetch(
        `/orchestration/projects/${projectId}/episodic-memory/search${qs ? `?${qs}` : ""}`
    );
}

export type EpisodicArchiveManifest = {
    id: string;
    object_key: string;
    period_start: string;
    period_end: string;
    record_count: number;
    byte_size: number;
    stats_json: Record<string, unknown>;
    created_at: string;
};

export async function listEpisodicArchives(projectId: string): Promise<EpisodicArchiveManifest[]> {
    return apiFetch(`/orchestration/projects/${projectId}/episodic-memory/archives`);
}

export async function reindexEpisodicMemory(
    projectId: string,
    limit: number = 200
): Promise<{ indexed: number }> {
    return apiFetch(
        `/orchestration/projects/${projectId}/episodic-memory/reindex?limit=${encodeURIComponent(String(limit))}`,
        { method: "POST" }
    );
}

export async function getMemoryMetrics(): Promise<Record<string, unknown>> {
    return apiFetch("/orchestration/memory-metrics");
}

export async function searchProjectKnowledge(
    projectId: string,
    query: string,
    taskId?: string,
    options?: { includeDecisions?: boolean },
): Promise<KnowledgeSearchResult[]> {
    const params = new URLSearchParams({ q: query });
    if (taskId) params.set("task_id", taskId);
    if (options?.includeDecisions) params.set("include_decisions", "true");
    return apiFetch(`/orchestration/projects/${projectId}/knowledge?${params.toString()}`);
}

export async function listProjectMemory(projectId: string, options?: { agentId?: string; status?: string }): Promise<AgentMemoryEntry[]> {
    const params = new URLSearchParams();
    if (options?.agentId) params.set("agent_id", options.agentId);
    if (options?.status) params.set("status", options.status);
    const suffix = params.toString() ? `?${params.toString()}` : "";
    return apiFetch(`/orchestration/projects/${projectId}/memory${suffix}`);
}

export async function createProjectMemory(
    projectId: string,
    payload: { agent_id: string; key: string; value_text: string; scope: "project-only" | "long-term"; ttl_days?: number },
): Promise<AgentMemoryWriteResult> {
    return apiFetch(`/orchestration/projects/${projectId}/memory`, {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

export async function deleteProjectMemoryEntry(projectId: string, memoryId: string): Promise<void> {
    return apiFetch(`/orchestration/projects/${projectId}/memory/${memoryId}`, { method: "DELETE" });
}

export type MemoryIngestJob = {
    id: string;
    project_id: string | null;
    job_type: string;
    status: "pending" | "running" | "completed" | "failed" | string;
    error_text: string | null;
    created_at: string;
    started_at: string | null;
    finished_at: string | null;
    payload: Record<string, unknown>;
};

export async function listProjectMemoryIngestJobs(
    projectId: string,
    limit: number = 60
): Promise<MemoryIngestJob[]> {
    const safe = Math.max(1, Math.min(limit, 300));
    return apiFetch(`/orchestration/projects/${projectId}/memory-ingest-jobs?limit=${safe}`);
}
