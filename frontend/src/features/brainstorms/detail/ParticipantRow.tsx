import { Avatar, Box, Button, Stack, TextField, Typography } from "@mui/material";
import { DeleteOutline as RemoveIcon } from "@mui/icons-material";

import type { Agent, BrainstormParticipant } from "../../../api/orchestration";
import { agentInitials } from "./formatUtils";

type ParticipantRowProps = {
    participant: BrainstormParticipant;
    agent: Agent | undefined;
    stance: string;
    canEdit: boolean;
    canRemove: boolean;
    isRemoving: boolean;
    onStanceChange: (value: string) => void;
    onStanceBlur: () => void;
    onRemove: () => void;
};

export function ParticipantRow({
    participant,
    agent,
    stance,
    canEdit,
    canRemove,
    isRemoving,
    onStanceChange,
    onStanceBlur,
    onRemove,
}: ParticipantRowProps) {
    return (
        <Stack direction="row" spacing={1} alignItems="center">
            <Avatar sx={{ width: 28, height: 28 }}>{agentInitials(agent?.name || "AI")}</Avatar>
            <Box sx={{ flex: 1, minWidth: 0 }}>
                <Typography variant="body2">{agent?.name || participant.agent_id}</Typography>
                <TextField
                    size="small"
                    variant="standard"
                    placeholder="Optional stance or focus"
                    value={stance}
                    onChange={(event) => onStanceChange(event.target.value)}
                    onBlur={onStanceBlur}
                    disabled={!canEdit}
                    fullWidth
                />
            </Box>
            <Button
                size="small"
                color="error"
                aria-label={`Remove ${agent?.name || "participant"}`}
                onClick={onRemove}
                disabled={!canRemove || isRemoving}
            >
                <RemoveIcon fontSize="small" />
            </Button>
        </Stack>
    );
}
