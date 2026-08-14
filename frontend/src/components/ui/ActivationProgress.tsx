import { Button, LinearProgress, Stack, Typography } from "@mui/material";
import { useNavigate } from "react-router-dom";

import type { ActivationStatus } from "../../api/orchestration/analytics";
import { formatDurationSeconds } from "../../utils/formatters";

type ActivationProgressProps = {
    status: ActivationStatus;
    title?: string;
    description?: string;
};

/** Action-oriented activation checklist derived from product milestones. */
export function ActivationProgress({
    status,
    title = "Activation progress",
    description = "Track the path from first integration to first governed external effect.",
}: ActivationProgressProps) {
    const navigate = useNavigate();
    const progress = status.total_count > 0 ? (status.completed_count / status.total_count) * 100 : 0;
    const next = status.next_step;

    return (
        <Stack spacing={1.5}>
            <Stack spacing={0.5}>
                <Typography variant="subtitle1">{title}</Typography>
                <Typography variant="body2" color="text.secondary">
                    {description}
                </Typography>
            </Stack>
            <LinearProgress variant="determinate" value={progress} sx={{ height: 8, borderRadius: 1 }} />
            <Typography variant="caption" color="text.secondary">
                {status.completed_count} of {status.total_count} milestones
                {status.activated && status.seconds_to_activate != null
                    ? ` · activated in ${formatDurationSeconds(status.seconds_to_activate)}`
                    : ""}
            </Typography>
            <Stack spacing={0.75}>
                {status.milestones.map((milestone) => (
                    <Typography
                        key={milestone.key}
                        variant="body2"
                        color={milestone.completed ? "text.secondary" : "text.primary"}
                        sx={{ textDecoration: milestone.completed ? "line-through" : "none" }}
                    >
                        {milestone.completed ? "✓" : "○"} {milestone.label}
                        {milestone.completed && milestone.seconds_from_baseline != null
                            ? ` (${formatDurationSeconds(milestone.seconds_from_baseline)})`
                            : ""}
                    </Typography>
                ))}
            </Stack>
            {next ? (
                <Button variant="contained" sx={{ alignSelf: "flex-start" }} onClick={() => navigate(next.path)}>
                    {next.cta}
                </Button>
            ) : (
                <Typography variant="body2" color="success.main">
                    Workspace activation complete.
                </Typography>
            )}
        </Stack>
    );
}
