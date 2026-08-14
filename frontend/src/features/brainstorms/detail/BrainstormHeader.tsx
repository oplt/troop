import { Alert, Button, Chip, Stack, Typography } from "@mui/material";
import { PlayArrow as StartIcon, Summarize as SummaryIcon } from "@mui/icons-material";

import type { Agent, Brainstorm, BrainstormParticipant } from "../../../api/orchestration";
import { formatDateTime, humanizeKey } from "../../../utils/formatters";
import { consensusChipColor } from "./formatUtils";

type BrainstormHeaderProps = {
    brainstorm: Brainstorm;
    participants: BrainstormParticipant[];
    agents: Agent[];
    isStarting: boolean;
    isRunningNextRound: boolean;
    isSummarizing: boolean;
    onStartOrNextRound: () => void;
    onForceSummary: () => void;
};

export function BrainstormHeader({
    brainstorm,
    participants,
    agents,
    isStarting,
    isRunningNextRound,
    isSummarizing,
    onStartOrNextRound,
    onForceSummary,
}: BrainstormHeaderProps) {
    const consensusColor = consensusChipColor(brainstorm.consensus_status);
    const roundsExhausted = brainstorm.current_round >= brainstorm.max_rounds;
    const roomClosed = brainstorm.status === "completed";

    return (
        <Stack spacing={1.25}>
            <Typography variant="body2" color="text.secondary">
                Status: {humanizeKey(brainstorm.status)}
            </Typography>
            <Typography variant="body2" color="text.secondary">
                Participants: {participants.length}
            </Typography>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={1} flexWrap="wrap" useFlexGap>
                <Button
                    size="small"
                    variant="contained"
                    startIcon={<StartIcon />}
                    onClick={onStartOrNextRound}
                    disabled={isStarting || isRunningNextRound || roomClosed || roundsExhausted}
                >
                    {brainstorm.current_round === 0 ? "Start round" : "Run another round"}
                </Button>
                <Button
                    size="small"
                    variant="outlined"
                    startIcon={<SummaryIcon />}
                    onClick={onForceSummary}
                    disabled={isSummarizing || roomClosed || participants.length < 2}
                >
                    Force final recommendation
                </Button>
            </Stack>
            <Typography variant="body2" color="text.secondary">
                Last updated: {formatDateTime(brainstorm.updated_at)}
            </Typography>
            <Typography variant="body2" color="text.secondary">
                Moderator:{" "}
                {agents.find((item) => item.id === brainstorm.moderator_agent_id)?.name ||
                    brainstorm.moderator_agent_id ||
                    "Auto"}
            </Typography>
            <Typography variant="subtitle2" sx={{ mt: 1 }}>
                Consensus
            </Typography>
            <Chip label={humanizeKey(brainstorm.consensus_status)} color={consensusColor} size="small" />
            {brainstorm.consensus_status === "conflict" ? (
                <Alert severity="warning">
                    The room detected split positions with low similarity. Use the moderator summary before spending
                    another round.
                </Alert>
            ) : null}
            <Typography variant="subtitle2" sx={{ mt: 1 }}>
                Latest round summary
            </Typography>
            <Typography variant="body2" color="text.secondary">
                {brainstorm.latest_round_summary || "No round summary yet."}
            </Typography>
            <Typography variant="subtitle2" sx={{ mt: 1 }}>
                Final output
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ whiteSpace: "pre-wrap" }}>
                {brainstorm.final_recommendation || brainstorm.summary || "No final output yet."}
            </Typography>
        </Stack>
    );
}
