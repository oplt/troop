import { describe, expect, it } from "vitest";

import type { ProjectLiveSnapshot } from "../api/orchestration";
import {
    collectProjectLiveSnapshotInvalidationKeys,
    isProjectLiveSnapshot,
} from "./projectLiveSnapshotSync";

const baseSnapshot = (): ProjectLiveSnapshot => ({
    project_id: "proj-1",
    agent_counts: { total: 2 },
    resource_counts: {
        repositories: 1,
        documents: 3,
        decisions: 0,
        memory_entries: 4,
    },
    task_counts: { total: 5, open: 3, blocked: 0, review: 1 },
    run_counts: { total: 2, active: 1, failed: 0 },
    approval_counts: { pending: 0 },
    sync_counts: { pending: 0, failed: 0 },
    ingest_counts: { pending: 0, running: 0, failed: 0 },
    latest: {
        task_updated_at: "2026-06-18T10:00:00.000Z",
        run_created_at: "2026-06-18T09:00:00.000Z",
        sync_created_at: null,
    },
});

describe("isProjectLiveSnapshot", () => {
    it("accepts valid snapshot payloads", () => {
        expect(isProjectLiveSnapshot(baseSnapshot() as unknown as Record<string, unknown>)).toBe(true);
    });

    it("rejects malformed payloads", () => {
        expect(isProjectLiveSnapshot({ project_id: "x" })).toBe(false);
    });
});

describe("collectProjectLiveSnapshotInvalidationKeys", () => {
    it("returns no keys for the first snapshot baseline", () => {
        const snapshot = baseSnapshot();
        expect(collectProjectLiveSnapshotInvalidationKeys("proj-1", snapshot, null)).toEqual([]);
    });

    it("returns no keys when the snapshot is unchanged", () => {
        const snapshot = baseSnapshot();
        expect(collectProjectLiveSnapshotInvalidationKeys("proj-1", snapshot, snapshot)).toEqual([]);
    });

    it("invalidates run queries when run counts change", () => {
        const previous = baseSnapshot();
        const next = {
            ...previous,
            run_counts: { ...previous.run_counts, active: 2 },
        };
        const keys = collectProjectLiveSnapshotInvalidationKeys("proj-1", next, previous);
        expect(keys).toContainEqual(["orchestration", "project", "proj-1", "runs"]);
        expect(keys).not.toContainEqual(["orchestration", "approvals"]);
    });

    it("invalidates approvals only when pending approval count changes", () => {
        const previous = baseSnapshot();
        const next = {
            ...previous,
            approval_counts: { pending: 1 },
        };
        const keys = collectProjectLiveSnapshotInvalidationKeys("proj-1", next, previous);
        expect(keys).toEqual([["orchestration", "approvals"]]);
    });

    it("invalidates task and execution queries when task timestamps change", () => {
        const previous = baseSnapshot();
        const next = {
            ...previous,
            latest: {
                ...previous.latest,
                task_updated_at: "2026-06-18T10:05:00.000Z",
            },
        };
        const keys = collectProjectLiveSnapshotInvalidationKeys("proj-1", next, previous, {
            expandedTaskId: "task-9",
        });
        expect(keys).toContainEqual(["orchestration", "project", "proj-1", "tasks"]);
        expect(keys).toContainEqual(["orchestration", "project", "proj-1", "task-exec"]);
        expect(keys).toContainEqual(["orchestration", "project", "proj-1", "tasks", "task-9", "timeline"]);
    });

    it("invalidates knowledge when document counts change", () => {
        const previous = baseSnapshot();
        const next = {
            ...previous,
            resource_counts: { ...previous.resource_counts, documents: 4 },
        };
        const keys = collectProjectLiveSnapshotInvalidationKeys("proj-1", next, previous);
        expect(keys).toContainEqual(["orchestration", "project", "proj-1", "documents"]);
        expect(keys).toContainEqual(["orchestration", "project", "proj-1", "knowledge"]);
        expect(keys).not.toContainEqual(["orchestration", "project", "proj-1", "runs"]);
    });
});
