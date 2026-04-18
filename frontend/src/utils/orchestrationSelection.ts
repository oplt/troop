import type { TaskRun } from "../api/orchestration";

export type OrchestrationSelectionMeta = {
    worker_agent_rationale?: string;
    model_rationale?: string;
    worker_agent_id_source?: string;
    model_source?: string;
    routing_inputs?: Record<string, unknown>;
    routing_policy_snapshot?: Record<string, unknown>;
};

export function readOrchestrationSelectionMeta(run: TaskRun | null | undefined): OrchestrationSelectionMeta {
    if (!run?.input_payload) return {};
    const raw = run.input_payload.orchestration_meta;
    if (!raw || typeof raw !== "object") return {};
    const m = raw as Record<string, unknown>;
    return {
        worker_agent_rationale:
            typeof m.agent_selection_reason === "string"
                ? m.agent_selection_reason
                : typeof m.worker_agent_rationale === "string"
                    ? m.worker_agent_rationale
                    : undefined,
        model_rationale:
            typeof m.model_selection_reason === "string"
                ? m.model_selection_reason
                : typeof m.model_rationale === "string"
                    ? m.model_rationale
                    : undefined,
        worker_agent_id_source: typeof m.worker_agent_id_source === "string" ? m.worker_agent_id_source : undefined,
        model_source: typeof m.model_source === "string" ? m.model_source : undefined,
        routing_inputs: typeof m.routing_inputs === "object" && m.routing_inputs !== null ? m.routing_inputs as Record<string, unknown> : undefined,
        routing_policy_snapshot: typeof m.routing_policy_snapshot === "object" && m.routing_policy_snapshot !== null ? m.routing_policy_snapshot as Record<string, unknown> : undefined,
    };
}
