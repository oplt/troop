import { Stack, Typography } from "@mui/material";

type GuardrailsPanelProps = {
    stopConditions: Record<string, unknown>;
};

export function GuardrailsPanel({ stopConditions }: GuardrailsPanelProps) {
    return (
        <Stack spacing={1}>
            <Typography variant="body2" color="text.secondary">
                Stop on consensus: {stopConditions.stop_on_consensus ? "yes" : "no"} · Accept soft consensus:{" "}
                {stopConditions.accept_soft_consensus ? "yes" : "no"}
            </Typography>
            <Typography variant="body2" color="text.secondary">
                Escalate on no consensus: {stopConditions.escalate_on_no_consensus ? "yes" : "no"} · Conflict requires
                moderation: {stopConditions.conflict_requires_moderation ? "yes" : "no"}
            </Typography>
            <Typography variant="body2" color="text.secondary">
                Cost cap: ${Number(stopConditions.max_cost_usd ?? 0).toFixed(2)} · Loop threshold:{" "}
                {(Number(stopConditions.max_repetition_score ?? 0) * 100).toFixed(1)}%
            </Typography>
            <Typography variant="body2" color="text.secondary">
                Soft-consensus floor: {(Number(stopConditions.soft_consensus_min_similarity ?? 0) * 100).toFixed(1)}% ·
                Conflict ceiling: {(Number(stopConditions.conflict_pairwise_max_similarity ?? 0) * 100).toFixed(1)}%
            </Typography>
        </Stack>
    );
}
