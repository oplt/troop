import type { Edge } from "@xyflow/react";
import type { WorkflowCanvasNode } from "./builderState";
import type { WorkflowValidationResponse } from "../../api/workforce";

export type WorkflowValidationIssue = {
    message: string;
    nodeId?: string;
    severity: "error" | "warning" | "info";
    source: "client" | "server";
};

const NODE_ID_IN_ERROR = /`([^`]+)`/;

export function clientValidationIssues(nodes: WorkflowCanvasNode[], edges: Edge[]): WorkflowValidationIssue[] {
    const issues: WorkflowValidationIssue[] = [];
    if (nodes.length === 0) {
        issues.push({ message: "Add at least one node.", severity: "error", source: "client" });
    }
    if (!nodes.some((node) => node.data.nodeType === "trigger")) {
        issues.push({ message: "A workflow needs a trigger node.", severity: "error", source: "client" });
    }
    const ids = new Set(nodes.map((node) => node.id));
    if (edges.some((edge) => !ids.has(edge.source) || !ids.has(edge.target))) {
        issues.push({ message: "An edge references a missing node.", severity: "error", source: "client" });
    }
    for (const node of nodes) {
        if (["trigger", "tool"].includes(node.data.nodeType) && !node.data.config.connector_installation_id) {
            issues.push({
                message: `${node.data.label}: select an explicit connection.`,
                nodeId: node.id,
                severity: "error",
                source: "client",
            });
        }
        if (node.data.nodeType === "approval" && !node.data.config.action) {
            issues.push({
                message: `${node.data.label}: select an approval action.`,
                nodeId: node.id,
                severity: "error",
                source: "client",
            });
        }
    }
    return issues;
}

export function serverValidationIssues(report: WorkflowValidationResponse): WorkflowValidationIssue[] {
    const issues: WorkflowValidationIssue[] = [];
    for (const message of report.errors ?? []) {
        issues.push({
            message,
            nodeId: extractNodeIdFromMessage(message),
            severity: "error",
            source: "server",
        });
    }
    for (const message of report.warnings ?? []) {
        const unreachableMatch = message.match(/^unreachable nodes from entry: (.+)$/);
        if (unreachableMatch) {
            for (const nodeId of unreachableMatch[1].split(",").map((item) => item.trim()).filter(Boolean)) {
                issues.push({
                    message: `Unreachable from entry: ${nodeId}`,
                    nodeId,
                    severity: "warning",
                    source: "server",
                });
            }
            continue;
        }
        issues.push({
            message,
            nodeId: extractNodeIdFromMessage(message),
            severity: "warning",
            source: "server",
        });
    }
    for (const message of report.infos ?? []) {
        issues.push({ message, severity: "info", source: "server" });
    }
    for (const item of report.external_write_nodes ?? []) {
        issues.push({
            message: `External write: ${item.tool_slug} on node ${item.node_id}`,
            nodeId: String(item.node_id),
            severity: "info",
            source: "server",
        });
    }
    return issues;
}

function extractNodeIdFromMessage(message: string): string | undefined {
    const match = message.match(NODE_ID_IN_ERROR);
    return match?.[1];
}

export function mergeValidationIssues(
    client: WorkflowValidationIssue[],
    server: WorkflowValidationIssue[],
): WorkflowValidationIssue[] {
    const seen = new Set<string>();
    const merged: WorkflowValidationIssue[] = [];
    for (const issue of [...client, ...server]) {
        const key = `${issue.severity}:${issue.nodeId ?? ""}:${issue.message}`;
        if (seen.has(key)) continue;
        seen.add(key);
        merged.push(issue);
    }
    return merged;
}

export function validationErrorCount(issues: WorkflowValidationIssue[]): number {
    return issues.filter((issue) => issue.severity === "error").length;
}
