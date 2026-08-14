import { Stack, TextField } from "@mui/material";

type RunFeedbackFormProps = {
    feedbackComment: string;
    correction: string;
    onFeedbackCommentChange: (value: string) => void;
    onCorrectionChange: (value: string) => void;
};

export function RunFeedbackForm({
    feedbackComment,
    correction,
    onFeedbackCommentChange,
    onCorrectionChange,
}: RunFeedbackFormProps) {
    return (
        <Stack spacing={1}>
            <TextField
                label="Feedback note"
                value={feedbackComment}
                onChange={(event) => onFeedbackCommentChange(event.target.value)}
                fullWidth
                size="small"
            />
            <TextField
                label="Correction"
                value={correction}
                onChange={(event) => onCorrectionChange(event.target.value)}
                fullWidth
                size="small"
                multiline
                minRows={2}
            />
        </Stack>
    );
}
