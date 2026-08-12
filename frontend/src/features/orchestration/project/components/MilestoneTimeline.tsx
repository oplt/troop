import { memo, useMemo } from "react";
import { Box, Chip, Paper, Typography } from "@mui/material";
import { alpha, useTheme } from "@mui/material/styles";
import { humanizeKey } from "../../../../utils/formatters";

export type MilestoneTimelineItem = {
    id: string;
    title: string;
    due_date: string | null;
    status: string;
};

function statusColor(status: string): "success" | "warning" | "default" {
    if (status === "completed") return "success";
    if (status === "in_progress" || status === "active") return "warning";
    return "default";
}

export const MilestoneTimeline = memo(function MilestoneTimeline({ milestones }: { milestones: MilestoneTimelineItem[] }) {
    const theme = useTheme();
    const sorted = useMemo(
        () => [...milestones].sort((a, b) => (a.due_date ? Date.parse(a.due_date) : Infinity) - (b.due_date ? Date.parse(b.due_date) : Infinity)),
        [milestones],
    );
    if (sorted.length === 0) return null;

    const dated = sorted.filter((item) => item.due_date);
    const firstDue = dated[0]?.due_date ? Date.parse(dated[0].due_date) : null;
    const lastDue = dated.at(-1)?.due_date ? Date.parse(dated.at(-1)!.due_date!) : null;
    const range = firstDue !== null && lastDue !== null ? Math.max(lastDue - firstDue, 1) : null;

    return (
        <Box sx={{ display: "grid", gap: 1.25 }}>
            <Box sx={{ position: "relative", px: 1, pt: 1.5 }}>
                <Box sx={{ position: "absolute", top: 14, left: 16, right: 16, height: 2, backgroundColor: theme.palette.divider }} />
                <Box sx={{ display: "flex", gap: 1.5, overflowX: "auto", pb: 0.5 }}>
                    {sorted.map((milestone) => {
                        const due = milestone.due_date ? new Date(milestone.due_date) : null;
                        const position = firstDue !== null && range !== null && due
                            ? `${Math.min(100, Math.max(0, ((due.getTime() - firstDue) / range) * 100))}%`
                            : "50%";
                        const completed = milestone.status === "completed";
                        const accent = completed ? theme.palette.success.main : theme.palette.primary.main;
                        return (
                            <Paper key={milestone.id} variant="outlined" sx={{ position: "relative", minWidth: 180, p: 1.5, borderRadius: 1, borderColor: completed ? theme.palette.success.main : theme.palette.divider, backgroundColor: alpha(accent, 0.06) }}>
                                <Box sx={{ position: "absolute", top: -10, left: `clamp(14px, ${position}, calc(100% - 14px))`, width: 12, height: 12, borderRadius: "50%", backgroundColor: accent, border: `2px solid ${theme.palette.background.paper}`, transform: "translateX(-50%)" }} />
                                <Chip label={humanizeKey(milestone.status)} size="small" color={statusColor(milestone.status)} sx={{ mb: 1 }} />
                                <Typography variant="subtitle2">{milestone.title}</Typography>
                                <Typography variant="caption" color="text.secondary">
                                    {due ? `Due ${due.toLocaleDateString()}` : "No due date"}
                                </Typography>
                            </Paper>
                        );
                    })}
                </Box>
            </Box>
        </Box>
    );
});
