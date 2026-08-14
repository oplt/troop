import { Box, Button, Chip, Stack, Typography } from "@mui/material";

import type { AiRun } from "../../../api/ai";
import { formatDateTime } from "../../../utils/formatters";
import { formatCostMicros } from "../formatUtils";
import { borderedPanelSx } from "../styles";
import { RunFeedbackForm } from "./RunFeedbackForm";

type RunResultCardProps = {
    run: AiRun;
    feedbackComment: string;
    correction: string;
    onRequestReview: () => void;
    onThumbsUp: () => void;
    onThumbsDown: () => void;
    onFeedbackCommentChange: (value: string) => void;
    onCorrectionChange: (value: string) => void;
};

export function RunResultCard({
    run,
    feedbackComment,
    correction,
    onRequestReview,
    onThumbsUp,
    onThumbsDown,
    onFeedbackCommentChange,
    onCorrectionChange,
}: RunResultCardProps) {
    return (
        <Box sx={borderedPanelSx}>
            <Stack spacing={1}>
                <Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" spacing={1}>
                    <Typography variant="subtitle2">
                        {run.provider_key}/{run.model_name}
                    </Typography>
                    <Chip
                        label={run.status}
                        size="small"
                        color={run.status === "completed" ? "success" : "warning"}
                        variant="outlined"
                    />
                </Stack>
                <Typography variant="body2" color="text.secondary">
                    {run.output_text?.slice(0, 280) ||
                        JSON.stringify(run.output_json, null, 2).slice(0, 280) ||
                        "No output"}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                    {formatDateTime(run.created_at)} • {run.total_tokens} tokens •{" "}
                    {formatCostMicros(run.estimated_cost_micros)}
                </Typography>
                <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
                    <Button size="small" variant="outlined" onClick={onRequestReview}>
                        Request review
                    </Button>
                    <Button size="small" variant="outlined" color="success" onClick={onThumbsUp}>
                        Thumbs up
                    </Button>
                    <Button size="small" variant="outlined" color="warning" onClick={onThumbsDown}>
                        Thumbs down
                    </Button>
                </Stack>
                <RunFeedbackForm
                    feedbackComment={feedbackComment}
                    correction={correction}
                    onFeedbackCommentChange={onFeedbackCommentChange}
                    onCorrectionChange={onCorrectionChange}
                />
            </Stack>
        </Box>
    );
}
