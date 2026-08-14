import { Box, Chip, Stack } from "@mui/material";
import {
    Background,
    Controls,
    MiniMap,
    ReactFlow,
    type NodeTypes,
    type OnEdgesChange,
    type OnNodesChange,
    type ReactFlowInstance,
    type Connection,
} from "@xyflow/react";
import { CanvasChrome } from "../../components/canvas/CanvasChrome";
import type { CanvasTheme } from "../../features/canvas/canvasTheme";
import type { TeamGraphEdge, TeamGraphNode } from "./hierarchyTypes";

type TeamGraphProps = {
    canvas: CanvasTheme;
    nodes: TeamGraphNode[];
    edges: TeamGraphEdge[];
    nodeTypes: NodeTypes;
    graphDirty: boolean;
    validationCount: number;
    showMiniMap: boolean;
    onShowMiniMapChange: (next: boolean) => void;
    onInit: (instance: ReactFlowInstance<TeamGraphNode, TeamGraphEdge>) => void;
    onNodesChange: OnNodesChange<TeamGraphNode>;
    onEdgesChange: OnEdgesChange<TeamGraphEdge>;
    onConnect: (connection: Connection) => void;
    onNodeClick: (nodeId: string) => void;
    onEdgeClick: (edgeId: string) => void;
    onPaneClick: () => void;
    onNodesDelete: (nodeIds: string[]) => void;
    onEdgesDelete: (edgeIds: string[]) => void;
    draggingHighlight: boolean;
    onDragOver: (event: React.DragEvent) => void;
    onDrop: (event: React.DragEvent) => void;
};

/** Main hierarchy team-builder XYFlow surface (lazy-loaded chunk). */
export function HierarchyTeamReactFlow({
    canvas,
    nodes,
    edges,
    nodeTypes,
    graphDirty,
    validationCount,
    showMiniMap,
    onShowMiniMapChange,
    onInit,
    onNodesChange,
    onEdgesChange,
    onConnect,
    onNodeClick,
    onEdgeClick,
    onPaneClick,
    onNodesDelete,
    onEdgesDelete,
    draggingHighlight,
    onDragOver,
    onDrop,
}: TeamGraphProps) {
    return (
        <Box
            onDragOver={onDragOver}
            onDrop={onDrop}
            sx={{
                position: "relative",
                borderRadius: 1,
                border: "1px solid",
                borderColor: draggingHighlight ? "primary.main" : "divider",
                bgcolor: canvas.surfaceBg,
            }}
        >
            <CanvasChrome
                dirty={graphDirty}
                validationCount={validationCount}
                showMiniMap={showMiniMap}
                onShowMiniMapChange={onShowMiniMapChange}
                height={{ xs: 560, xl: 720 }}
                aria-label="Team graph canvas"
                sx={{
                    "& > .MuiStack-root:first-of-type": { borderRadius: 0, borderLeft: 0, borderRight: 0, borderTop: 0 },
                    "& > [aria-label=\"Team graph canvas\"]": { border: 0, borderRadius: 0, height: { xs: 560, xl: 720 } },
                }}
            >
                {({ showMiniMap: miniMapVisible }) => (
                    <>
                        <ReactFlow
                            nodes={nodes}
                            edges={edges}
                            nodeTypes={nodeTypes}
                            onInit={onInit}
                            onNodesChange={onNodesChange}
                            onEdgesChange={onEdgesChange}
                            onConnect={onConnect}
                            onNodeClick={(_, node) => onNodeClick(node.id)}
                            onEdgeClick={(_, edge) => onEdgeClick(edge.id)}
                            onPaneClick={onPaneClick}
                            fitView
                            selectionOnDrag
                            deleteKeyCode={["Backspace", "Delete"]}
                            onNodesDelete={(deleted) => onNodesDelete(deleted.map((n) => n.id))}
                            onEdgesDelete={(deleted) => onEdgesDelete(deleted.map((e) => e.id))}
                            proOptions={{ hideAttribution: true }}
                        >
                            <Background color={canvas.backgroundDot} gap={18} size={1.1} />
                            {miniMapVisible ? <MiniMap pannable zoomable /> : null}
                            <Controls showInteractive={false} />
                        </ReactFlow>
                        <Stack
                            direction="row"
                            spacing={1}
                            flexWrap="wrap"
                            useFlexGap
                            sx={{
                                position: "absolute",
                                left: 12,
                                bottom: 12,
                                zIndex: 5,
                                pointerEvents: "none",
                            }}
                        >
                            <Chip size="small" label="Manager" />
                            <Chip size="small" label="Specialist" variant="outlined" />
                            <Chip size="small" label="Reviewer" variant="outlined" />
                            <Chip size="small" label="Drag templates · zoom/pan · save when dirty" variant="outlined" />
                        </Stack>
                    </>
                )}
            </CanvasChrome>
        </Box>
    );
}

type PreviewProps = {
    canvas: CanvasTheme;
    nodes: TeamGraphNode[];
    edges: TeamGraphEdge[];
    nodeTypes: NodeTypes;
    onNodesChange: OnNodesChange<TeamGraphNode>;
    onNodeClick: (nodeId: string) => void;
    onPaneClick: () => void;
};

/** Team-template composition preview (same XYFlow chunk). */
export function HierarchyTemplatePreviewFlow({
    canvas,
    nodes,
    edges,
    nodeTypes,
    onNodesChange,
    onNodeClick,
    onPaneClick,
}: PreviewProps) {
    return (
        <Box sx={{ height: 420, borderRadius: 1, overflow: "hidden", bgcolor: canvas.surfaceBgSoft }}>
            <ReactFlow
                nodes={nodes}
                edges={edges}
                nodeTypes={nodeTypes}
                onNodesChange={onNodesChange}
                onNodeClick={(_, node) => onNodeClick(node.id)}
                onPaneClick={onPaneClick}
                fitView
                deleteKeyCode={null}
                selectionOnDrag={false}
                proOptions={{ hideAttribution: true }}
            >
                <Background color={canvas.backgroundDot} gap={18} size={1.1} />
                <Controls showInteractive={false} />
            </ReactFlow>
        </Box>
    );
}

export default HierarchyTeamReactFlow;
