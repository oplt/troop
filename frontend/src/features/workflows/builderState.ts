import type { Edge, Node } from "@xyflow/react";

export const WORKFLOW_NODE_TYPES = [
    "trigger",
    "agent",
    "skill",
    "tool",
    "condition",
    "router",
    "parallel",
    "approval",
    "human_input",
    "delay",
    "subworkflow",
] as const;

export type WorkflowNodeType = typeof WORKFLOW_NODE_TYPES[number];

export type WorkflowNodeData = {
    label: string;
    nodeType: WorkflowNodeType;
    config: Record<string, unknown>;
};

export type WorkflowCanvasNode = Node<WorkflowNodeData>;

export function createWorkflowNode(type: WorkflowNodeType, index: number): WorkflowCanvasNode {
    return {
        id: `node_${Date.now()}_${index}`,
        type: "default",
        position: { x: 100 + (index % 3) * 260, y: 80 + Math.floor(index / 3) * 160 },
        data: {
            label: type.replaceAll("_", " "),
            nodeType: type,
            config: {},
        },
    };
}

export function toWorkflowPayload(nodes: WorkflowCanvasNode[], edges: Edge[]) {
    return {
        nodes: nodes.map((node) => ({
            id: node.id,
            type: node.data.nodeType,
            label: node.data.label,
            config: node.data.config,
            position: node.position,
        })),
        edges: edges.map((edge) => ({
            id: edge.id,
            from: edge.source,
            to: edge.target,
            source_handle: edge.sourceHandle ?? null,
            target_handle: edge.targetHandle ?? null,
            label: typeof edge.label === "string" ? edge.label : undefined,
        })),
        entry_node_id: nodes.find((node) => node.data.nodeType === "trigger")?.id ?? nodes[0]?.id ?? null,
    };
}

export function validateWorkflow(nodes: WorkflowCanvasNode[], edges: Edge[]): string[] {
    const errors: string[] = [];
    if (nodes.length === 0) errors.push("Add at least one node.");
    if (!nodes.some((node) => node.data.nodeType === "trigger")) errors.push("A workflow needs a trigger node.");
    const ids = new Set(nodes.map((node) => node.id));
    if (edges.some((edge) => !ids.has(edge.source) || !ids.has(edge.target))) errors.push("An edge references a missing node.");
    for (const node of nodes) {
        if (["trigger", "tool"].includes(node.data.nodeType) && !node.data.config.connector_installation_id) {
            errors.push(`${node.data.label}: select an explicit connection.`);
        }
        if (node.data.nodeType === "approval" && !node.data.config.action) {
            errors.push(`${node.data.label}: select an approval action.`);
        }
    }
    return errors;
}

export function emailTelegramStarter(): { nodes: WorkflowCanvasNode[]; edges: Edge[] } {
    const specs: Array<[string, WorkflowNodeType, string, Record<string, unknown>]> = [
        ["gmail_trigger", "trigger", "Gmail: new email", { event_type: "gmail_new_message" }],
        ["get_thread", "tool", "Fetch Gmail thread", { operation: "gmail.get_thread" }],
        ["triage", "agent", "Classify incoming email", { input_mapping: "$.email" }],
        ["should_reply", "condition", "Reply required?", { expression: "$.triage.should_reply == true" }],
        ["draft_reply", "agent", "Draft response", { skill: "email-response-drafter", input_mapping: "$.thread" }],
        ["create_draft", "tool", "Create Gmail draft", { operation: "gmail.create_draft" }],
        ["approve_send", "approval", "Telegram approval", { action: "gmail.send_draft", delivery_channel: "telegram" }],
        ["send_draft", "tool", "Send approved draft", { operation: "gmail.send_draft" }],
    ];
    const nodes = specs.map(([id, nodeType, label, config], index) => ({
        id,
        type: "default",
        position: { x: index % 2 === 0 ? 120 : 440, y: index * 120 },
        data: { label, nodeType, config },
    })) satisfies WorkflowCanvasNode[];
    const edges = nodes.slice(0, -1).map((node, index) => ({
        id: `edge_${node.id}_${nodes[index + 1].id}`,
        source: node.id,
        target: nodes[index + 1].id,
        label: node.id === "should_reply" ? "true" : undefined,
    }));
    return { nodes, edges };
}

const SECRET_KEY = /(token|secret|password|authorization|credential|access_key|refresh_key|api_key|cookie|oauth)/i;

export function safeRunValue(value: unknown): unknown {
    if (Array.isArray(value)) return value.map(safeRunValue);
    if (!value || typeof value !== "object") return value;
    return Object.fromEntries(
        Object.entries(value as Record<string, unknown>)
            .filter(([key]) => !SECRET_KEY.test(key))
            .map(([key, item]) => [key, safeRunValue(item)]),
    );
}
