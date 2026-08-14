import { Button, Chip, Stack, TextField, Typography } from "@mui/material";

import type { AiReviewItem } from "../../../api/ai";

type ReviewCardProps = {
    review: AiReviewItem;
    reviewNotes: string;
    correction: string;
    onReviewNotesChange: (value: string) => void;
    onCorrectionChange: (value: string) => void;
    onApprove: () => void;
    onRequestChanges: () => void;
    onReject: () => void;
};

export function ReviewCard({
    review,
    reviewNotes,
    correction,
    onReviewNotesChange,
    onCorrectionChange,
    onApprove,
    onRequestChanges,
    onReject,
}: ReviewCardProps) {
    return (
        <Stack spacing={1}>
            <Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" spacing={1}>
                <Typography variant="body2">Run {review.run_id.slice(0, 8)}</Typography>
                <Chip label={review.status} size="small" variant="outlined" />
            </Stack>
            <TextField
                label="Reviewer notes"
                value={reviewNotes}
                onChange={(event) => onReviewNotesChange(event.target.value)}
                fullWidth
                size="small"
            />
            <TextField
                label="Corrected output"
                value={correction}
                onChange={(event) => onCorrectionChange(event.target.value)}
                fullWidth
                size="small"
                multiline
                minRows={2}
            />
            <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
                <Button size="small" variant="outlined" color="success" onClick={onApprove}>
                    Approve
                </Button>
                <Button size="small" variant="outlined" color="warning" onClick={onRequestChanges}>
                    Request changes
                </Button>
                <Button size="small" variant="outlined" color="error" onClick={onReject}>
                    Reject
                </Button>
            </Stack>
        </Stack>
    );
}
