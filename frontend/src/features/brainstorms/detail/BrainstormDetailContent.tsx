import { Box, Stack } from "@mui/material";
import { useNavigate } from "react-router-dom";

import type { Brainstorm } from "../../../api/orchestration";
import { PageShell } from "../../../components/ui/PageShell";
import { SectionCard } from "../../../components/ui/SectionCard";
import { BrainstormHeader } from "./BrainstormHeader";
import { ConversationPanel } from "./ConversationPanel";
import { DiscourseSignalsPanel } from "./DiscourseSignalsPanel";
import { GuardrailsPanel } from "./GuardrailsPanel";
import { ModeratorLogPanel } from "./ModeratorLogPanel";
import { ParticipantsPanel } from "./ParticipantsPanel";
import { PromotionPanel } from "./PromotionPanel";
import { useBrainstormRoom } from "./useBrainstormRoom";

type BrainstormDetailContentProps = {
    brainstormId: string;
    brainstorm: Brainstorm;
};

export function BrainstormDetailContent({ brainstormId, brainstorm }: BrainstormDetailContentProps) {
    const navigate = useNavigate();
    const room = useBrainstormRoom({ brainstormId, brainstorm });

    return (
        <PageShell maxWidth="xl">
            <Box
                sx={{
                    display: "grid",
                    gap: 2,
                    gridTemplateColumns: { xs: "1fr", xl: "minmax(0, 1.6fr) 360px" },
                    alignItems: "start",
                }}
            >
                <SectionCard title="Discussion thread" description="Chat-style transcript grouped by round.">
                    <ConversationPanel groupedMessages={room.groupedMessages} agents={room.agents} />
                </SectionCard>

                <Stack spacing={2}>
                    <SectionCard
                        title="Room status"
                        description="Participants, consensus signal, summaries, and promotion actions."
                    >
                        <BrainstormHeader
                            brainstorm={brainstorm}
                            participants={room.participants}
                            agents={room.agents}
                            isStarting={room.startMutation.isPending}
                            isRunningNextRound={room.nextRoundMutation.isPending}
                            isSummarizing={room.summaryMutation.isPending}
                            onStartOrNextRound={() =>
                                (brainstorm.current_round === 0 ? room.startMutation : room.nextRoundMutation).mutate()
                            }
                            onForceSummary={() => room.summaryMutation.mutate()}
                        />
                    </SectionCard>

                    <SectionCard
                        title="Discourse signals"
                        description="Lightweight repetition and vocabulary hints to spot circular debate before you burn more rounds."
                    >
                        <DiscourseSignalsPanel discourse={room.discourse} />
                    </SectionCard>

                    <SectionCard title="Guardrails" description="Room mode, stop conditions, and moderator thresholds.">
                        <GuardrailsPanel stopConditions={room.stopConditions} />
                    </SectionCard>

                    <SectionCard
                        title="Moderator log"
                        description="Round summaries and finalization records captured in the room decision log."
                    >
                        <ModeratorLogPanel
                            brainstorm={brainstorm}
                            roundSummaries={room.roundSummaries}
                            finalEntries={room.finalEntries}
                        />
                    </SectionCard>

                    <SectionCard title="Participants" description="Agents currently taking part in the room.">
                        <ParticipantsPanel
                            brainstorm={brainstorm}
                            participants={room.participants}
                            agents={room.agents}
                            projectAgents={room.projectAgents}
                            newParticipantId={room.newParticipantId}
                            participantStances={room.participantStances}
                            isAdding={room.addParticipantMutation.isPending}
                            isRemoving={room.removeParticipantMutation.isPending}
                            onNewParticipantChange={room.setNewParticipantId}
                            onAddParticipant={() => room.addParticipantMutation.mutate()}
                            onStanceChange={(participantId, stance) =>
                                room.setParticipantStances((current) => ({ ...current, [participantId]: stance }))
                            }
                            onStanceBlur={(participantId, stance) =>
                                room.stanceMutation.mutate({ participantId, stance })
                            }
                            onRemoveParticipant={(participantId) => room.removeParticipantMutation.mutate(participantId)}
                        />
                    </SectionCard>

                    <SectionCard title="Promote output" description="Turn the final room output into operational records.">
                        <PromotionPanel
                            brainstorm={brainstorm}
                            isPromotingTasks={room.promoteTasksMutation.isPending}
                            isPromotingAdr={room.promoteAdrMutation.isPending}
                            isPromotingDocument={room.promoteDocumentMutation.isPending}
                            isExporting={room.exportArtifactMutation.isPending}
                            onPromoteTasks={() => room.promoteTasksMutation.mutate()}
                            onPromoteAdr={() => room.promoteAdrMutation.mutate()}
                            onPromoteDocument={() => room.promoteDocumentMutation.mutate()}
                            onExportArtifact={() => room.exportArtifactMutation.mutate()}
                            onOpenProject={() => navigate(`/projects/${brainstorm.project_id}`)}
                        />
                    </SectionCard>
                </Stack>
            </Box>
        </PageShell>
    );
}
