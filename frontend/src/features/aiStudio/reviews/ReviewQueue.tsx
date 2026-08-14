import { Approval as ReviewIcon } from "@mui/icons-material";
import { Box, Stack, Typography } from "@mui/material";

import type { AiReviewItem } from "../../../api/ai";
import { EmptyState } from "../../../components/ui/EmptyState";
import { SectionCard } from "../../../components/ui/SectionCard";
import { borderedPanelSx } from "../styles";
import { ReviewCard } from "./ReviewCard";

type ReviewQueueProps = {
    reviews: AiReviewItem[];
    reviewNotesById: Record<string, string>;
    correctionsById: Record<string, string>;
    onReviewNotesChange: (reviewId: string, value: string) => void;
    onCorrectionChange: (reviewId: string, value: string) => void;
    onApprove: (reviewId: string) => void;
    onRequestChanges: (reviewId: string) => void;
    onReject: (reviewId: string) => void;
};

export function ReviewQueue({
    reviews,
    reviewNotesById,
    correctionsById,
    onReviewNotesChange,
    onCorrectionChange,
    onApprove,
    onRequestChanges,
    onReject,
}: ReviewQueueProps) {
    return (
        <SectionCard title="Reviews and evaluations" description="Route sensitive outputs through human approval.">
            <Stack spacing={2}>
                <Stack spacing={1.25}>
                    <Typography variant="subtitle2">Review queue</Typography>
                    {reviews.length > 0 ? (
                        reviews.map((review) => (
                            <Box key={review.id} sx={borderedPanelSx}>
                                <ReviewCard
                                    review={review}
                                    reviewNotes={reviewNotesById[review.id] ?? ""}
                                    correction={correctionsById[review.id] ?? ""}
                                    onReviewNotesChange={(value) => onReviewNotesChange(review.id, value)}
                                    onCorrectionChange={(value) => onCorrectionChange(review.id, value)}
                                    onApprove={() => onApprove(review.id)}
                                    onRequestChanges={() => onRequestChanges(review.id)}
                                    onReject={() => onReject(review.id)}
                                />
                            </Box>
                        ))
                    ) : (
                        <EmptyState
                            icon={<ReviewIcon />}
                            title="No reviews queued"
                            description="Review requests created from runs will appear here."
                        />
                    )}
                </Stack>
            </Stack>
        </SectionCard>
    );
}
