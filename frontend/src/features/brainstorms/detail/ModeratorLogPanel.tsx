import { Paper, Stack, Typography } from "@mui/material";

import type { Brainstorm } from "../../../api/orchestration";
import { humanizeKey } from "../../../utils/formatters";

type ModeratorLogPanelProps = {
    brainstorm: Brainstorm;
    roundSummaries: Array<Record<string, unknown>>;
    finalEntries: Array<Record<string, unknown>>;
};

export function ModeratorLogPanel({ brainstorm, roundSummaries, finalEntries }: ModeratorLogPanelProps) {
    return (
        <Stack spacing={1}>
            {roundSummaries.map((entry, index) => (
                <Paper key={`round-summary-${index}`} variant="outlined" sx={{ p: 1.25, borderRadius: 1 }}>
                    <Typography variant="subtitle2">Round {String(entry.round ?? index + 1)}</Typography>
                    <Typography variant="caption" color="text.secondary">
                        Consensus: {humanizeKey(String(entry.consensus_kind ?? "open"))}
                        {" · "}
                        Conflict: {entry.conflict_signal ? "yes" : "no"}
                        {" · "}
                        Repetition:{" "}
                        {entry.repetition_score != null
                            ? `${(Number(entry.repetition_score) * 100).toFixed(1)}%`
                            : "n/a"}
                    </Typography>
                    <Typography variant="body2" color="text.secondary" sx={{ mt: 0.75, whiteSpace: "pre-wrap" }}>
                        {String(entry.summary ?? "")}
                    </Typography>
                </Paper>
            ))}
            {finalEntries.map((entry, index) => (
                <Paper key={`final-output-${index}`} variant="outlined" sx={{ p: 1.25, borderRadius: 1 }}>
                    <Typography variant="subtitle2">Final output</Typography>
                    <Typography variant="caption" color="text.secondary">
                        Reason: {humanizeKey(String(entry.reason ?? "completed"))} · Output:{" "}
                        {humanizeKey(String(entry.output_type ?? brainstorm.output_type))}
                    </Typography>
                    <Typography variant="body2" color="text.secondary" sx={{ mt: 0.75, whiteSpace: "pre-wrap" }}>
                        {String(entry.content ?? "")}
                    </Typography>
                </Paper>
            ))}
            {roundSummaries.length === 0 && finalEntries.length === 0 ? (
                <Typography variant="body2" color="text.secondary">
                    No moderator records yet.
                </Typography>
            ) : null}
        </Stack>
    );
}
