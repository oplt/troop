import type { WorkflowNodeType } from "./builderState";

/** Typed config shapes per node type — serialized to backend `config` JSON. */
export type TriggerNodeConfig = {
    connector_installation_id?: string;
    trigger_type?: string;
    event_type?: string;
};

export type AgentNodeConfig = {
    agent_id?: string;
    skill_id?: string;
    skill?: string;
    input_mapping?: string;
};

export type SkillNodeConfig = {
    skill_id?: string;
};

export type ToolNodeConfig = {
    connector_installation_id?: string;
    tool?: string;
    tool_slug?: string;
    operation?: string;
    params?: Record<string, unknown>;
    argument_mapping?: string;
};

export type ConditionNodeConfig = {
    expression?: string;
    operator?: string;
    left?: unknown;
    right?: unknown;
};

export type RouterNodeConfig = {
    rules?: string;
};

export type ParallelNodeConfig = {
    completion_policy?: string;
    join_policy?: string;
};

export type ApprovalNodeConfig = {
    action?: string;
    delivery_channel?: string;
    approvers?: string;
};

export type HumanInputNodeConfig = {
    prompt?: string;
};

export type DelayNodeConfig = {
    delay_seconds?: number;
};

export type SubworkflowNodeConfig = {
    workflow_id?: string;
    subworkflow_id?: string;
};

export type WorkflowNodeConfigByType = {
    trigger: TriggerNodeConfig;
    agent: AgentNodeConfig;
    skill: SkillNodeConfig;
    tool: ToolNodeConfig;
    condition: ConditionNodeConfig;
    router: RouterNodeConfig;
    parallel: ParallelNodeConfig;
    approval: ApprovalNodeConfig;
    human_input: HumanInputNodeConfig;
    delay: DelayNodeConfig;
    subworkflow: SubworkflowNodeConfig;
};

export type WorkflowNodeConfig = WorkflowNodeConfigByType[WorkflowNodeType];

export function nodeConfigFor<T extends WorkflowNodeType>(
    _nodeType: T,
    raw: Record<string, unknown>,
): WorkflowNodeConfigByType[T] {
    return raw as WorkflowNodeConfigByType[T];
}

export const NODE_TYPE_DESCRIPTIONS: Record<WorkflowNodeType, string> = {
    trigger: "Starts the workflow when an external event or manual run occurs.",
    agent: "Runs an agent with optional skill binding and input mapping.",
    skill: "Invokes a published skill directly.",
    tool: "Executes a connector operation with schema-validated parameters.",
    condition: "Branches based on an expression over workflow variables.",
    router: "Routes to multiple branches using routing rules.",
    parallel: "Runs branches concurrently with a join policy.",
    approval: "Pauses for human approval before continuing.",
    human_input: "Collects structured input from a human operator.",
    delay: "Waits for a configured duration before continuing.",
    subworkflow: "Embeds another workflow as a nested run.",
};
