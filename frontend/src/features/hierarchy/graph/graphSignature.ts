type GraphNodeSnapshot = {
    id: string;
    type?: string;
    position: { x: number; y: number };
    data: unknown;
};

type GraphEdgeSnapshot = {
    id: string;
    source: string;
    target: string;
    data?: unknown;
    label?: unknown;
};

/** Stable persistence signature; intentionally excludes transient React Flow metadata. */
export function graphSignature(nodes: GraphNodeSnapshot[], edges: GraphEdgeSnapshot[]): string {
    return JSON.stringify({
        nodes: nodes.map(({ id, type, position, data }) => ({ id, type, position, data })),
        edges: edges.map(({ id, source, target, data, label }) => ({ id, source, target, data, label })),
    });
}
