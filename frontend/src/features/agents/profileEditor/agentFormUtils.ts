import type { Agent } from "../../../api/orchestration";
import { DEFAULT_AGENT_MARKDOWN, type AgentProfileForm } from "./types";

export function commaSeparatedList(value: string) {
    return value
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
}

export function agentProfileForm(agent: Agent | null): AgentProfileForm {
    const policy = agent?.model_policy ?? {};
    const budget = agent?.budget ?? {};
    const memory = agent?.memory_policy ?? {};
    const output = agent?.output_schema ?? {};

    return {
        name: agent?.name ?? "New Specialist",
        slug: agent?.slug ?? "new-specialist",
        role: agent?.role ?? "specialist",
        description: agent?.description ?? "",
        capabilities: (agent?.capabilities ?? []).join(", "),
        allowed_tools: agent?.allowed_tools ?? [],
        permissions: typeof agent?.permissions === "string" ? agent.permissions : "read-only",
        escalation_path: agent?.escalation_path ?? "manager",
        task_filters: (agent?.task_filters ?? []).join(", "),
        provider: String(policy.provider ?? ""),
        model: String(policy.model ?? ""),
        fallback_model: String(policy.fallback_model ?? ""),
        max_context: String(policy.max_context ?? ""),
        temperature: String(policy.temperature ?? "0.2"),
        max_tokens: String(policy.max_tokens ?? ""),
        reasoning_level: String(policy.reasoning_level ?? "medium"),
        reasoning_effort: String(policy.reasoning_effort ?? policy.reasoning_level ?? "medium"),
        tool_calling: policy.tool_calling !== false,
        structured_output: Boolean(policy.structured_output),
        timeout_seconds: String(policy.timeout_seconds ?? agent?.timeout_seconds ?? "900"),
        retry_count: String(policy.retry_count ?? agent?.retry_limit ?? "1"),
        memory_scope: String(memory.scope ?? "project-only"),
        token_budget: String(budget.token_budget ?? "4000"),
        time_budget_seconds: String(budget.time_budget_seconds ?? "300"),
        retry_budget: String(budget.retry_budget ?? "1"),
        budget_cap_usd: String(budget.cost_cap_usd ?? budget.budget_cap_usd ?? ""),
        output_format: String(output.format ?? "checklist"),
    };
}

export function agentContractPayload(form: AgentProfileForm, projectId: string, markdown: string) {
    const model_policy = {
        provider: form.provider.trim() || undefined,
        model: form.model.trim() || undefined,
        fallback_model: form.fallback_model.trim() || undefined,
        max_context: form.max_context ? Number(form.max_context) : undefined,
        max_tokens: form.max_tokens ? Number(form.max_tokens) : undefined,
        temperature: form.temperature ? Number(form.temperature) : undefined,
        reasoning_level: form.reasoning_level || undefined,
        reasoning_effort: form.reasoning_effort || undefined,
        tool_calling: form.tool_calling,
        structured_output: form.structured_output,
        timeout_seconds: form.timeout_seconds ? Number(form.timeout_seconds) : undefined,
        retry_count: form.retry_count ? Number(form.retry_count) : undefined,
        permissions: form.permissions,
        escalation_path: form.escalation_path.trim() || undefined,
    };

    return {
        name: form.name.trim(),
        slug: form.slug.trim(),
        role: form.role.trim() || "specialist",
        description: form.description.trim() || null,
        capabilities: commaSeparatedList(form.capabilities),
        allowed_tools: form.allowed_tools,
        permissions: form.permissions,
        escalation_path: form.escalation_path.trim() || null,
        task_filters: commaSeparatedList(form.task_filters),
        model_policy,
        memory_policy: { scope: form.memory_scope },
        budget: {
            token_budget: Number(form.token_budget),
            time_budget_seconds: Number(form.time_budget_seconds),
            retry_budget: Number(form.retry_budget),
            cost_cap_usd: form.budget_cap_usd ? Number(form.budget_cap_usd) : undefined,
        },
        timeout_seconds: Number(form.timeout_seconds),
        retry_limit: Number(form.retry_count),
        output_schema: { format: form.output_format },
        project_id: projectId || null,
        source_markdown: markdown,
    };
}

export function defaultAgentMarkdown() {
    return DEFAULT_AGENT_MARKDOWN;
}
