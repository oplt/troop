import type { Edge } from "@xyflow/react";
import type { WorkflowCanvasNode, WorkflowNodeType } from "./builderState";

type ApiNode = {
    id: string;
    type?: string;
    label?: string;
    config?: Record<string, unknown>;
    position?: { x?: number; y?: number };
};

type ApiEdge = {
    id?: string;
    from?: string;
    to?: string;
    source?: string;
    target?: string;
    label?: string;
    source_handle?: string | null;
    target_handle?: string | null;
};

export function canvasFromWorkflowPayload(
    nodes: ApiNode[],
    edges: ApiEdge[],
): { nodes: WorkflowCanvasNode[]; edges: Edge[] } {
    const canvasNodes: WorkflowCanvasNode[] = nodes.map((node, index) => ({
        id: String(node.id),
        type: "workflow",
        position: {
            x: Number(node.position?.x ?? 100 + (index % 3) * 260),
            y: Number(node.position?.y ?? 80 + Math.floor(index / 3) * 160),
        },
        data: {
            label: String(node.label ?? node.type ?? node.id).replaceAll("_", " "),
            nodeType: (node.type ?? "tool") as WorkflowNodeType,
            config: { ...(node.config ?? {}) },
        },
    }));

    const canvasEdges: Edge[] = edges.map((edge, index) => {
        const source = String(edge.from ?? edge.source ?? "");
        const target = String(edge.to ?? edge.target ?? "");
        return {
            id: String(edge.id ?? `edge_${source}_${target}_${index}`),
            source,
            target,
            label: edge.label,
            sourceHandle: edge.source_handle ?? undefined,
            targetHandle: edge.target_handle ?? undefined,
        };
    });

    return { nodes: canvasNodes, edges: canvasEdges };
}
