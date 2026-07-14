import { useCallback } from "react";
import { useEdgesState, useNodesState, type Edge, type Node } from "@xyflow/react";

/** Owns the React Flow graph state separately from library/template state. */
export function useHierarchyGraphState<TNode extends Node, TEdge extends Edge>(
    initialGraph: { nodes: TNode[]; edges: TEdge[] },
) {
    const [nodes, setNodes, onNodesChange] = useNodesState<TNode>(initialGraph.nodes);
    const [edges, setEdges, onEdgesChange] = useEdgesState<TEdge>(initialGraph.edges);
    const replaceGraph = useCallback(
        (next: { nodes: TNode[]; edges: TEdge[] }) => {
            setNodes(next.nodes);
            setEdges(next.edges);
        },
        [setEdges, setNodes],
    );

    return { nodes, edges, setNodes, setEdges, onNodesChange, onEdgesChange, replaceGraph };
}
