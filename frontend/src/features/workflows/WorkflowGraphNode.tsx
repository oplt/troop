import { Box, Chip, Paper, Typography } from "@mui/material";
import { alpha, useTheme } from "@mui/material/styles";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { getCanvasTheme } from "../canvas/canvasTheme";
import { humanizeKey } from "../../utils/formatters";
import type { WorkflowNodeRunStatus } from "./runOverlay";
import type { WorkflowCanvasNode } from "./builderState";

export type WorkflowGraphNodeData = WorkflowCanvasNode["data"] & {
    runStatus?: WorkflowNodeRunStatus;
    selected?: boolean;
};

const STATUS_COLORS: Record<WorkflowNodeRunStatus, string> = {
    idle: "#667085",
    running: "#12b76a",
    completed: "#027a48",
    failed: "#d92d20",
    waiting: "#f79009",
    simulated: "#6941c6",
};

export function WorkflowGraphNode({ data, selected }: NodeProps<WorkflowCanvasNode>) {
    const theme = useTheme();
    const canvas = getCanvasTheme(theme);
    const runStatus = (data as WorkflowGraphNodeData).runStatus ?? "idle";
    const statusColor = STATUS_COLORS[runStatus];
    const isActive = runStatus === "running";
    const tone = theme.palette.primary.main;

    return (
        <Paper
            elevation={0}
            sx={{
                width: 196,
                borderRadius: 1,
                border: "2px solid",
                borderColor: selected ? "primary.main" : canvas.nodeBorder,
                bgcolor: runStatus === "failed" ? alpha("#d92d20", 0.04) : "background.paper",
                boxShadow: selected ? `0 0 0 1px ${alpha(tone, 0.2)}` : "none",
                overflow: "hidden",
                position: "relative",
            }}
        >
            <Handle
                type="target"
                position={Position.Top}
                style={{ background: tone, width: 10, height: 10, border: "2px solid white" }}
            />
            <Box sx={{ position: "absolute", left: 8, top: 8, display: "flex", alignItems: "center", gap: 0.75 }}>
                <Box
                    sx={{
                        width: 10,
                        height: 10,
                        borderRadius: "50%",
                        bgcolor: statusColor,
                        boxShadow: isActive ? `0 0 0 4px ${alpha(statusColor, 0.25)}` : "none",
                        animation: isActive ? "pulse 1.4s ease-in-out infinite" : "none",
                        "@keyframes pulse": {
                            "0%, 100%": { opacity: 1 },
                            "50%": { opacity: 0.45 },
                        },
                    }}
                />
                {runStatus !== "idle" && (
                    <Chip
                        label={humanizeKey(runStatus)}
                        size="small"
                        sx={{ height: 18, fontSize: "0.62rem", bgcolor: alpha(statusColor, 0.12), color: statusColor }}
                    />
                )}
            </Box>
            <Box sx={{ px: 1.25, pt: 3.5, pb: 1.25 }}>
                <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
                    {humanizeKey(data.nodeType)}
                </Typography>
                <Typography variant="subtitle2" sx={{ lineHeight: 1.25, wordBreak: "break-word" }}>
                    {data.label}
                </Typography>
            </Box>
            <Handle
                type="source"
                position={Position.Bottom}
                style={{ background: tone, width: 10, height: 10, border: "2px solid white" }}
            />
        </Paper>
    );
}

export const workflowNodeTypes = {
    workflow: WorkflowGraphNode,
};
