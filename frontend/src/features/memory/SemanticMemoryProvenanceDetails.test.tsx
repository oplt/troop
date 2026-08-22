import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { SemanticMemoryEntry } from "../../api/orchestration";
import { SemanticMemoryProvenanceDetails } from "./SemanticMemoryProvenanceDetails";

const entry: SemanticMemoryEntry = {
    id: "memory-2",
    owner_id: "owner-1",
    scope: "project",
    company_id: "company-1",
    project_id: "project-1",
    agent_id: "agent-1",
    entry_type: "fact",
    namespace: "project/project-1/facts",
    title: "Project deadline",
    body: "Deadline is 18 September",
    metadata: { document_id: "document-1" },
    source_chunk_id: "chunk-1",
    source_task_id: "task-1",
    source_run_id: "run-1",
    provenance: { source: "project_decision", source_agent_id: "agent-1" },
    confidence: 0.91,
    created_by_user_id: "owner-1",
    ttl_days: null,
    expires_at: null,
    deleted_at: null,
    retention_policy: "default",
    memory_version: 2,
    canonical_key: "project/project-1/deadline",
    valid_from: "2026-08-22T10:00:00Z",
    valid_until: null,
    status: "current",
    supersedes_memory_id: "memory-1",
    embedding_model: null,
    embedding_version: null,
    created_at: "2026-08-22T10:00:00Z",
    updated_at: "2026-08-22T10:00:00Z",
};

describe("SemanticMemoryProvenanceDetails", () => {
    it("shows source, creator, task, run, document, confidence, and lifecycle", () => {
        render(<SemanticMemoryProvenanceDetails entry={entry} />);

        expect(screen.getByText("project_decision")).toBeInTheDocument();
        expect(screen.getByText("owner-1")).toBeInTheDocument();
        expect(screen.getByText("task-1")).toBeInTheDocument();
        expect(screen.getByText("run-1")).toBeInTheDocument();
        expect(screen.getByText("document-1")).toBeInTheDocument();
        expect(screen.getByText("91%")).toBeInTheDocument();
        expect(screen.getByText("current")).toBeInTheDocument();
        expect(screen.getByText("memory-1")).toBeInTheDocument();
    });
});
