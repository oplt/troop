import { Chip, Stack, Typography } from "@mui/material";

import type { BrainstormDiscourseInsights } from "../../../api/orchestration";
import { humanizeKey } from "../../../utils/formatters";

type DiscourseSignalsPanelProps = {
    discourse: BrainstormDiscourseInsights | undefined;
};

export function DiscourseSignalsPanel({ discourse }: DiscourseSignalsPanelProps) {
    if (!discourse) {
        return (
            <Typography variant="body2" color="text.secondary">
                Computing discourse hints…
            </Typography>
        );
    }

    return (
        <Stack spacing={1}>
            <Typography variant="body2" color="text.secondary">
                Messages: {discourse.message_count} · Rounds with traffic: {discourse.rounds_with_messages} · Adjacent
                same-agent ratio: {(discourse.same_agent_streak_ratio * 100).toFixed(1)}%
            </Typography>
            <Typography variant="body2" color="text.secondary">
                Last round repetition (adjacent):{" "}
                {discourse.last_round_repetition_score != null && discourse.last_round_repetition_score !== undefined
                    ? `${(Number(discourse.last_round_repetition_score) * 100).toFixed(1)}%`
                    : "n/a"}
                {" · "}Pairwise min similarity:{" "}
                {discourse.last_round_pairwise_min_similarity != null
                    ? `${(Number(discourse.last_round_pairwise_min_similarity) * 100).toFixed(1)}%`
                    : "n/a"}
            </Typography>
            <Typography variant="body2" color="text.secondary">
                Consensus signal: {discourse.consensus_kind ? humanizeKey(String(discourse.consensus_kind)) : "n/a"}
                {discourse.conflict_signal ? " · Possible stalemate / split positions" : ""}
            </Typography>
            <Typography variant="caption" color="text.secondary">
                Repeated terms (heuristic)
            </Typography>
            <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                {discourse.top_repeated_terms.length === 0 ? (
                    <Typography variant="body2" color="text.secondary">
                        Not enough text yet.
                    </Typography>
                ) : (
                    discourse.top_repeated_terms.map((term) => (
                        <Chip key={term} size="small" variant="outlined" label={term} />
                    ))
                )}
            </Stack>
        </Stack>
    );
}
