import type { Edge } from "@xyflow/react";
import type { WorkflowStepRun } from "../../api/integrations";
import type { WorkflowCanvasNode } from "./builderState";

export type WorkflowNodeRunStatus =
    | "idle"
    | "running"
    | "completed"
    | "failed"
    | "waiting"
    | "simulated";

export function buildNodeRunStatusMap(
    nodes: WorkflowCanvasNode[],
    steps: WorkflowStepRun[],
    currentNodeId: string | null | undefined,
    runStatus: string | null | undefined,
): Map<string, WorkflowNodeRunStatus> {
    const byNode = new Map<string, WorkflowNodeRunStatus>();
    for (const node of nodes) {
        byNode.set(node.id, "idle");
    }

    for (const step of steps) {
        const nodeId = step.node_id;
        if (!byNode.has(nodeId)) continue;
        const output = step.output_json ?? {};
        const nestedResult = output.result && typeof output.result === "object"
            ? (output.result as Record<string, unknown>)
            : null;
        if (output.simulated === true || nestedResult?.simulated === true) {
            byNode.set(nodeId, "simulated");
            continue;
        }
        if (step.status === "failed") {
            byNode.set(nodeId, "failed");
        } else if (step.status === "completed" || step.status === "succeeded") {
            byNode.set(nodeId, "completed");
        } else if (step.status.includes("waiting") || step.status === "paused") {
            byNode.set(nodeId, "waiting");
        }
    }

    if (currentNodeId && byNode.has(currentNodeId)) {
        const current = byNode.get(currentNodeId);
        if (runStatus === "running" && current !== "completed" && current !== "failed" && current !== "simulated") {
            byNode.set(currentNodeId, "running");
        }
    }

    return byNode;
}

export function resolveEntryNodeId(nodes: WorkflowCanvasNode[]): string | null {
    return nodes.find((node) => node.data.nodeType === "trigger")?.id ?? nodes[0]?.id ?? null;
}

export function canSafelyRunFromNode(
    nodeId: string | null,
    nodes: WorkflowCanvasNode[],
    edges: Edge[],
): boolean {
    if (!nodeId) return false;
    const entryId = resolveEntryNodeId(nodes);
    if (nodeId === entryId) return true;

    const node = nodes.find((item) => item.id === nodeId);
    if (!node || node.data.nodeType !== "trigger") return false;

    const predecessors = collectPredecessors(nodeId, edges);
    return predecessors.size === 0;
}

function collectPredecessors(nodeId: string, edges: Edge[]): Set<string> {
    const result = new Set<string>();
    const queue = edges.filter((edge) => edge.target === nodeId).map((edge) => edge.source);
    while (queue.length) {
        const current = queue.pop();
        if (!current || result.has(current)) continue;
        result.add(current);
        queue.push(...edges.filter((edge) => edge.target === current).map((edge) => edge.source));
    }
    return result;
}
