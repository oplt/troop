import { beforeEach, describe, expect, it, vi } from "vitest";

import { getNotifications, getNotificationsPage } from "./notifications";
import { listApprovals, listApprovalsPage } from "./orchestration/approvals";
import { listOrchestrationTasks, listOrchestrationTasksPage } from "./orchestration/projects";
import { listRuns, listRunsPage } from "./orchestration/runs";
import { assertCursorPage, isCursorPage } from "./pagination";

function jsonResponse(body: unknown, init: ResponseInit = { status: 200 }) {
    return new Response(JSON.stringify(body), {
        ...init,
        headers: {
            "Content-Type": "application/json",
            ...(init.headers ?? {}),
        },
    });
}

describe("cursor page contract", () => {
    it("accepts objects with an items array", () => {
        expect(isCursorPage({ items: [], next_cursor: null })).toBe(true);
        expect(isCursorPage([])).toBe(false);
        expect(isCursorPage({ next_cursor: null })).toBe(false);
    });

    it("throws a diagnostic error for non-page payloads", () => {
        expect(() => assertCursorPage([], "/notifications")).toThrow(
            /Expected a cursor page from \/notifications/,
        );
    });
});

describe("paginated list API wrappers", () => {
    beforeEach(() => {
        vi.restoreAllMocks();
    });

    it("unwraps notification CursorPage responses and preserves body_preview", async () => {
        const page = {
            items: [
                {
                    id: "n1",
                    type: "test",
                    title: "Hello",
                    body_preview: "Preview",
                    is_read: false,
                    created_at: "2026-08-14T10:00:00Z",
                },
            ],
            next_cursor: null,
        };
        vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(page)));

        await expect(getNotificationsPage()).resolves.toEqual(page);
        vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(page));
        await expect(getNotifications()).resolves.toEqual(page.items);
        expect(page.items[0].body_preview).toBe("Preview");
        expect(page.items[0]).not.toHaveProperty("body");
    });

    it("unwraps approval CursorPage responses into list items", async () => {
        const page = {
            items: [
                {
                    id: "appr-1",
                    project_id: "proj-1",
                    task_id: "task-1",
                    run_id: "run-1",
                    issue_link_id: null,
                    approval_type: "task_escalation",
                    status: "pending",
                    reason: "Needs review",
                    effect_hash: null,
                    effect_version: 1,
                    expires_at: null,
                    created_at: "2026-08-14T10:00:00Z",
                    resolved_at: null,
                },
            ],
            next_cursor: {
                created_at: "2026-08-14T10:00:00Z",
                id: "appr-1",
                position: null,
            },
        };
        vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(page)));

        await expect(listApprovalsPage()).resolves.toEqual(page);
        vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(page));
        const items = await listApprovals();
        expect(items).toEqual(page.items);
        expect(items[0]).not.toHaveProperty("payload");
    });

    it("unwraps run CursorPage responses without inventing full TaskRun fields", async () => {
        const page = {
            items: [
                {
                    id: "run-1",
                    parent_run_id: null,
                    project_id: "proj-1",
                    task_id: "task-1",
                    run_mode: "single_agent",
                    status: "in_progress",
                    model_name: "gpt-test",
                    attempt_number: 1,
                    token_input: 10,
                    token_output: 20,
                    token_total: 30,
                    estimated_cost_micros: 0,
                    latency_ms: 12,
                    error_message: null,
                    retry_count: 0,
                    created_at: "2026-08-14T10:00:00Z",
                    started_at: "2026-08-14T10:00:01Z",
                    completed_at: null,
                    cancelled_at: null,
                },
            ],
            next_cursor: null,
        };
        vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(page)));

        await expect(listRunsPage()).resolves.toEqual(page);
        vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(page));
        const items = await listRuns();
        expect(items).toEqual(page.items);
        expect(items.filter((run) => run.status === "in_progress")).toHaveLength(1);
        expect(items[0]).not.toHaveProperty("worker_agent_id");
        expect(items[0]).not.toHaveProperty("input_payload");
    });

    it("unwraps orchestration task CursorPage responses", async () => {
        const page = {
            items: [
                {
                    id: "task-1",
                    project_id: "proj-1",
                    title: "Ship checklist",
                    status: "queued",
                    priority: "normal",
                    task_type: "general",
                    position: 0,
                    assigned_agent_id: null,
                    human_assignee_id: null,
                    parent_task_id: null,
                    github_issue_number: null,
                    github_issue_url: null,
                    github_repository_full_name: null,
                    due_date: null,
                    labels: [],
                    dependency_ids: [],
                    has_result: false,
                    created_at: "2026-08-14T10:00:00Z",
                    updated_at: "2026-08-14T10:00:00Z",
                },
            ],
            next_cursor: null,
        };
        vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(page)));

        await expect(listOrchestrationTasksPage("proj-1")).resolves.toEqual(page);
        vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(page));
        const items = await listOrchestrationTasks("proj-1");
        expect(items).toEqual(page.items);
        expect(items.map((task) => task.title)).toEqual(["Ship checklist"]);
        expect(items[0]).not.toHaveProperty("description");
        expect(items[0]).not.toHaveProperty("metadata");
    });
});
