import { Button, Divider, MenuItem, Stack, TextField } from "@mui/material";

import type { Agent, Brainstorm, BrainstormParticipant } from "../../../api/orchestration";
import { ParticipantRow } from "./ParticipantRow";

type ParticipantsPanelProps = {
    brainstorm: Brainstorm;
    participants: BrainstormParticipant[];
    agents: Agent[];
    projectAgents: Agent[];
    newParticipantId: string;
    participantStances: Record<string, string>;
    isAdding: boolean;
    isRemoving: boolean;
    onNewParticipantChange: (agentId: string) => void;
    onAddParticipant: () => void;
    onStanceChange: (participantId: string, stance: string) => void;
    onStanceBlur: (participantId: string, stance: string) => void;
    onRemoveParticipant: (participantId: string) => void;
};

export function ParticipantsPanel({
    brainstorm,
    participants,
    agents,
    projectAgents,
    newParticipantId,
    participantStances,
    isAdding,
    isRemoving,
    onNewParticipantChange,
    onAddParticipant,
    onStanceChange,
    onStanceBlur,
    onRemoveParticipant,
}: ParticipantsPanelProps) {
    const roomLocked = brainstorm.status === "running" || brainstorm.status === "completed";

    return (
        <Stack spacing={1}>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
                <TextField
                    select
                    size="small"
                    label="Add project agent"
                    value={newParticipantId}
                    onChange={(event) => onNewParticipantChange(event.target.value)}
                    disabled={roomLocked}
                    fullWidth
                >
                    <MenuItem value="">Select an agent</MenuItem>
                    {projectAgents
                        .filter((agent) => !participants.some((participant) => participant.agent_id === agent.id))
                        .map((agent) => (
                            <MenuItem key={agent.id} value={agent.id}>
                                {agent.name}
                            </MenuItem>
                        ))}
                </TextField>
                <Button
                    variant="outlined"
                    onClick={onAddParticipant}
                    disabled={!newParticipantId || isAdding || roomLocked}
                >
                    Add
                </Button>
            </Stack>
            <Divider />
            {participants.map((participant) => {
                const agent = agents.find((item) => item.id === participant.agent_id);
                const stance = participantStances[participant.id] ?? participant.stance ?? "";
                return (
                    <ParticipantRow
                        key={participant.id}
                        participant={participant}
                        agent={agent}
                        stance={stance}
                        canEdit={!roomLocked}
                        canRemove={participants.length > 2 && !roomLocked}
                        isRemoving={isRemoving}
                        onStanceChange={(value) => onStanceChange(participant.id, value)}
                        onStanceBlur={() => onStanceBlur(participant.id, stance)}
                        onRemove={() => onRemoveParticipant(participant.id)}
                    />
                );
            })}
        </Stack>
    );
}
