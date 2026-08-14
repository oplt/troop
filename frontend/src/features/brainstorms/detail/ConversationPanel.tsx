import { Alert, Avatar, Box, Chip, Paper, Stack, Typography } from "@mui/material";

import type { Agent, BrainstormMessage } from "../../../api/orchestration";
import { formatDateTime } from "../../../utils/formatters";
import { agentInitials } from "./formatUtils";

type ConversationPanelProps = {
    groupedMessages: Array<[number, BrainstormMessage[]]>;
    agents: Agent[];
};

export function ConversationPanel({ groupedMessages, agents }: ConversationPanelProps) {
    return (
        <Stack spacing={2}>
            {groupedMessages.length === 0 ? (
                <Alert severity="info">No discussion messages yet.</Alert>
            ) : (
                groupedMessages.map(([round, roundMessages]) => (
                    <Box key={round}>
                        <Typography variant="overline" color="text.secondary">
                            Round {round}
                        </Typography>
                        <Stack spacing={1.25} sx={{ mt: 1 }}>
                            {roundMessages.map((message) => {
                                const agent = agents.find((item) => item.id === message.agent_id);
                                return (
                                    <Paper key={message.id} sx={{ p: 1.5, borderRadius: 1 }}>
                                        <Stack direction="row" spacing={1.5} alignItems="flex-start">
                                            <Avatar sx={{ width: 34, height: 34 }}>
                                                {agentInitials(agent?.name || "AI")}
                                            </Avatar>
                                            <Box sx={{ flex: 1 }}>
                                                <Stack
                                                    direction="row"
                                                    spacing={1}
                                                    alignItems="center"
                                                    flexWrap="wrap"
                                                    useFlexGap
                                                >
                                                    <Typography variant="subtitle2">
                                                        {agent?.name || "Moderator"}
                                                    </Typography>
                                                    <Chip label={message.message_type} size="small" variant="outlined" />
                                                    <Typography variant="caption" color="text.secondary">
                                                        {formatDateTime(message.created_at)}
                                                    </Typography>
                                                </Stack>
                                                <Typography variant="body2" sx={{ mt: 0.75, whiteSpace: "pre-wrap" }}>
                                                    {message.content}
                                                </Typography>
                                            </Box>
                                        </Stack>
                                    </Paper>
                                );
                            })}
                        </Stack>
                    </Box>
                ))
            )}
        </Stack>
    );
}
