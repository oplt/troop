export type HierarchyValidationNode = {
    id: string;
    data: {
        name: string;
        role: string;
        escalationPath?: string;
        linkedTemplateSlug?: string;
    };
};

export type HierarchyValidationEdge = {
    id: string;
    source: string;
    target: string;
    data?: { semantic?: string };
};

export type HierarchyValidationIssue = {
    id: string;
    severity: "error" | "warning";
    nodeId?: string;
    edgeId?: string;
    message: string;
};

/** Pure graph validation used by both the editor and non-visual validation tests. */
export function buildHierarchyValidationIssues(
    nodes: HierarchyValidationNode[],
    edges: HierarchyValidationEdge[],
    workspaceHasProviders = true,
): HierarchyValidationIssue[] {
    const issues: HierarchyValidationIssue[] = [];
    const incomingByNode = new Map<string, HierarchyValidationEdge[]>();

    for (const edge of edges) {
        incomingByNode.set(edge.target, [...(incomingByNode.get(edge.target) ?? []), edge]);
        if (edge.source === edge.target) {
            issues.push({
                id: `self-loop-${edge.id}`,
                severity: "error",
                edgeId: edge.id,
                nodeId: edge.source,
                message: "Self-loops are not allowed in the team graph.",
            });
        }
    }

    const managerRoots = nodes.filter((node) =>
        node.data.role === "manager" &&
        !(incomingByNode.get(node.id) ?? []).some((edge) => edge.data?.semantic === "delegates_to"),
    );
    if (nodes.some((node) => node.data.role === "manager") && managerRoots.length !== 1) {
        issues.push({
            id: "manager-root-count",
            severity: "warning",
            message: `Expected one manager root, found ${managerRoots.length}.`,
        });
    }

    if (nodes.length > 0 && !nodes.some((node) => node.data.role === "reviewer")) {
        issues.push({
            id: "reviewer-role-required",
            severity: "error",
            message: "Add at least one reviewer role before saving this team.",
        });
    }

    for (const node of nodes) {
        if (node.data.role !== "manager") {
            const hasHierarchyParent = (incomingByNode.get(node.id) ?? [])
                .some((edge) => edge.data?.semantic !== "collaborates_with");
            if (!hasHierarchyParent) {
                issues.push({
                    id: `orphan-${node.id}`,
                    severity: "error",
                    nodeId: node.id,
                    message: `${node.data.name} has no incoming manager, reviewer, or escalation relationship.`,
                });
            }
        }

        if (node.data.escalationPath) {
            const hasTarget = nodes.some((candidate) =>
                candidate.id === node.data.escalationPath ||
                candidate.data.name === node.data.escalationPath,
            );
            if (!hasTarget) {
                issues.push({
                    id: `invalid-escalation-${node.id}`,
                    severity: "warning",
                    nodeId: node.id,
                    message: `${node.data.name} has an escalation target that does not exist in this team graph.`,
                });
            }
        }

        if (node.data.linkedTemplateSlug && !workspaceHasProviders) {
            issues.push({
                id: `template-no-provider-${node.id}`,
                severity: "warning",
                nodeId: node.id,
                message: `${node.data.name} uses agent template "${node.data.linkedTemplateSlug}" but no LLM providers are configured in your workspace.`,
            });
        }
    }

    return issues;
}
