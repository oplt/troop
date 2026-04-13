import type { TaskRun } from "../api/orchestration";

export type OrchestrationSelectionMeta = {
    worker_agent_rationale?: string;
    model_rationale?: string;
    worker_agent_id_source?: string;
    model_source?: string;
};

export function readOrchestrationSelectionMeta(run: TaskRun | null | undefined): OrchestrationSelectionMeta {
    if (!run?.input_payload) return {};
    const raw = run.input_payload.orchestration_meta;
    if (!raw || typeof raw !== "object") return {};
    const m = raw as Record<string, unknown>;
    return {
        worker_agent_rationale: typeof m.worker_agent_rationale === "string" ? m.worker_agent_rationale : undefined,
        model_rationale: typeof m.model_rationale === "string" ? m.model_rationale : undefined,
        worker_agent_id_source: typeof m.worker_agent_id_source === "string" ? m.worker_agent_id_source : undefined,
        model_source: typeof m.model_source === "string" ? m.model_source : undefined,
    };
}
