import { describe, expect, it } from "vitest";
import { computeTraceSummary, filterTraceSpans } from "./traceUtils";
import type { RunTraceSpan, TaskRun } from "../../api/orchestration";

const baseRun: TaskRun = {
    id: "run-1",
    parent_run_id: null,
    project_id: "proj-1",
    task_id: "task-1",
    triggered_by_user_id: null,
    orchestrator_agent_id: null,
    worker_agent_id: null,
    reviewer_agent_id: null,
    provider_config_id: null,
    brainstorm_id: null,
    run_mode: "single_agent",
    status: "completed",
    model_name: "gpt-4.1",
    attempt_number: 1,
    token_input: 100,
    token_output: 50,
    token_total: 150,
    estimated_cost_micros: 1200,
    latency_ms: 10_000,
    error_message: null,
    retry_count: 0,
    checkpoint_json: {},
    input_payload: {},
    output_payload: {},
    created_at: "2026-01-01T00:00:00Z",
    started_at: "2026-01-01T00:00:00Z",
    completed_at: "2026-01-01T00:00:10Z",
    cancelled_at: null,
};

const spans: RunTraceSpan[] = [
    {
        id: "evt:1",
        run_id: "run-1",
        kind: "model_attempt",
        title: "Model",
        status: "completed",
        message: null,
        started_at: "2026-01-01T00:00:01Z",
        finished_at: "2026-01-01T00:00:02Z",
        safe_payload: {},
        restricted: { has_restricted: false, restricted_fields: [] },
        source_event_id: "1",
        source_event_type: "llm_response",
        parent_span_id: null,
        tokens_input: 10,
        tokens_output: 5,
        cost_usd_micros: 100,
    },
    {
        id: "approval:1",
        run_id: "run-1",
        kind: "approval",
        title: "Approval",
        status: "approved",
        message: null,
        started_at: "2026-01-01T00:00:03Z",
        finished_at: "2026-01-01T00:00:08Z",
        safe_payload: {},
        restricted: { has_restricted: false, restricted_fields: [] },
        source_event_id: null,
        source_event_type: null,
        parent_span_id: null,
        tokens_input: 0,
        tokens_output: 0,
        cost_usd_micros: 0,
    },
    {
        id: "effect:1",
        run_id: "run-1",
        kind: "tool_effect",
        title: "External effect",
        status: "completed",
        message: null,
        started_at: "2026-01-01T00:00:09Z",
        finished_at: "2026-01-01T00:00:09Z",
        safe_payload: { external_result_id: "msg-123", action_key: "gmail.send_draft" },
        restricted: { has_restricted: false, restricted_fields: [] },
        source_event_id: null,
        source_event_type: null,
        parent_span_id: "approval:1",
        tokens_input: 0,
        tokens_output: 0,
        cost_usd_micros: 0,
    },
];

describe("run trace utils", () => {
    it("computes summary counts and human wait", () => {
        const stats = computeTraceSummary(baseRun, spans);
        expect(stats.modelCount).toBe(1);
        expect(stats.toolCount).toBe(1);
        expect(stats.approvalCount).toBe(1);
        expect(stats.externalEffectCount).toBe(1);
        expect(stats.humanWaitMs).toBe(5000);
    });

    it("filters spans by category", () => {
        expect(filterTraceSpans(spans, "tools")).toHaveLength(1);
        expect(filterTraceSpans(spans, "approvals")).toHaveLength(1);
        expect(filterTraceSpans(spans, "models")).toHaveLength(1);
    });
});
