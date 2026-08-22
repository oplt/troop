import { memo, useMemo } from "react";
import { Box } from "@mui/material";
import type { TaskListItem } from "../../api/orchestration";
import { useTheme } from "@mui/material/styles";
import { EmptyState } from "../../components/ui/EmptyState";
import { AccountTree as DagIcon } from "@mui/icons-material";

export const DagView = memo(function DagView({
    tasks,
    selectedDagTaskId,
    onSelectTask,
}: {
    tasks: TaskListItem[];
    selectedDagTaskId: string | null;
    onSelectTask: (taskId: string) => void;
}) {
    const theme = useTheme();
    const STATUS_COLORS: Record<string, string> = {
        completed: "#4caf50",
        approved: "#2e7d32",
        synced_to_github: "#4caf50",
        failed: "#f44336",
        in_progress: "#2196f3",
        queued: "#ff9800",
        planned: "#607d8b",
        blocked: "#9c27b0",
        backlog: "#9e9e9e",
        needs_review: "#ff9800",
    };

    const taskIndex = useMemo(() => Object.fromEntries(tasks.map((t, i) => [t.id, i])), [tasks]);

    const COLS = Math.min(4, tasks.length);
    const NODE_W = 160;
    const NODE_H = 50;
    const GAP_X = 60;
    const GAP_Y = 40;
    const PADDING = 20;

    const positions = useMemo(() => {
        return tasks.map((_, i) => ({
            x: PADDING + (i % COLS) * (NODE_W + GAP_X),
            y: PADDING + Math.floor(i / COLS) * (NODE_H + GAP_Y),
        }));
    }, [tasks, COLS]);

    const svgW = PADDING * 2 + COLS * (NODE_W + GAP_X) - GAP_X;
    const svgH = PADDING * 2 + Math.ceil(tasks.length / COLS) * (NODE_H + GAP_Y) - GAP_Y;

    const edges = useMemo(() => {
        const result: Array<{ x1: number; y1: number; x2: number; y2: number }> = [];
        for (const task of tasks) {
            for (const depId of task.dependency_ids ?? []) {
                const srcIdx = taskIndex[depId];
                const dstIdx = taskIndex[task.id];
                if (srcIdx === undefined || dstIdx === undefined) continue;
                const src = positions[srcIdx];
                const dst = positions[dstIdx];
                result.push({
                    x1: src.x + NODE_W / 2,
                    y1: src.y + NODE_H,
                    x2: dst.x + NODE_W / 2,
                    y2: dst.y,
                });
            }
        }
        return result;
    }, [tasks, positions, taskIndex]);

    if (tasks.length === 0) {
        return <EmptyState icon={<DagIcon />} title="No tasks yet" description="Add tasks to see the dependency graph." />;
    }

    return (
        <Box sx={{ overflow: "auto" }}>
            <svg width={svgW} height={svgH} style={{ display: "block" }}>
                <defs>
                    <marker id="arrow" markerWidth="8" markerHeight="8" refX="4" refY="4" orient="auto">
                        <path d="M0,0 L0,8 L8,4 z" fill="#999" />
                    </marker>
                </defs>
                {edges.map((edge, i) => (
                    <line
                        key={i}
                        x1={edge.x1} y1={edge.y1} x2={edge.x2} y2={edge.y2}
                        stroke="#999" strokeWidth={1.5} markerEnd="url(#arrow)"
                    />
                ))}
                {tasks.map((task, i) => {
                    const pos = positions[i];
                    const color = STATUS_COLORS[task.status] ?? "#9e9e9e";
                    const selected = task.id === selectedDagTaskId;
                    return (
                        <g
                            key={task.id}
                            role="button"
                            tabIndex={0}
                            style={{ cursor: "pointer" }}
                            onClick={() => onSelectTask(task.id)}
                            onKeyDown={(e) => {
                                if (e.key === "Enter" || e.key === " ") {
                                    e.preventDefault();
                                    onSelectTask(task.id);
                                }
                            }}
                        >
                            <rect
                                x={pos.x} y={pos.y} width={NODE_W} height={NODE_H}
                                rx={8} ry={8}
                                fill={color + "22"}
                                stroke={selected ? theme.palette.primary.main : color}
                                strokeWidth={selected ? 3 : 1.5}
                            />
                            <text
                                x={pos.x + NODE_W / 2} y={pos.y + 18}
                                textAnchor="middle" fontSize={11} fontWeight="600" fill={color}
                            >
                                {task.title.length > 20 ? task.title.slice(0, 19) + "…" : task.title}
                            </text>
                            <text
                                x={pos.x + NODE_W / 2} y={pos.y + 34}
                                textAnchor="middle" fontSize={10} fill="#888"
                            >
                                {task.status}
                            </text>
                        </g>
                    );
                })}
            </svg>
        </Box>
    );
});

// ── Main Page ────────────────────────────────────────────────

