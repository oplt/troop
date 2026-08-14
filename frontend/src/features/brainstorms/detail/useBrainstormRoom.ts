import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { Brainstorm } from "../../../api/orchestration";
import {
    addBrainstormParticipant,
    exportBrainstormArtifact,
    forceBrainstormSummary,
    getBrainstormDiscourseInsights,
    listAgents,
    listBrainstormMessages,
    listBrainstormParticipants,
    listProjectAgents,
    promoteBrainstorm,
    promoteBrainstormAdr,
    promoteBrainstormDocument,
    removeBrainstormParticipant,
    startBrainstorm,
    startBrainstormNextRound,
    updateBrainstormParticipant,
} from "../../../api/orchestration";
import { useSnackbar } from "../../../app/snackbarContext";
import { humanizeKey } from "../../../utils/formatters";
import { groupMessagesByRound } from "./formatUtils";

type UseBrainstormRoomOptions = {
    brainstormId: string;
    brainstorm: Brainstorm;
};

export function useBrainstormRoom({ brainstormId, brainstorm }: UseBrainstormRoomOptions) {
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();
    const [newParticipantId, setNewParticipantId] = useState("");
    const [participantStances, setParticipantStances] = useState<Record<string, string>>({});

    const { data: participants = [] } = useQuery({
        queryKey: ["orchestration", "brainstorm", brainstormId, "participants"],
        queryFn: () => listBrainstormParticipants(brainstormId),
        enabled: Boolean(brainstormId),
    });
    const { data: messages = [] } = useQuery({
        queryKey: ["orchestration", "brainstorm", brainstormId, "messages"],
        queryFn: () => listBrainstormMessages(brainstormId),
        enabled: Boolean(brainstormId),
    });
    const { data: discourse } = useQuery({
        queryKey: ["orchestration", "brainstorm", brainstormId, "discourse-insights"],
        queryFn: () => getBrainstormDiscourseInsights(brainstormId),
        enabled: Boolean(brainstormId),
    });
    const { data: agents = [] } = useQuery({
        queryKey: ["orchestration", "agents"],
        queryFn: () => listAgents(),
    });
    const { data: projectMembers = [] } = useQuery({
        queryKey: ["orchestration", "project", brainstorm.project_id, "agents"],
        queryFn: () => listProjectAgents(brainstorm.project_id),
        enabled: Boolean(brainstorm.project_id),
    });

    const projectAgentIds = useMemo(() => new Set(projectMembers.map((member) => member.agent_id)), [projectMembers]);
    const projectAgents = agents.filter((agent) => projectAgentIds.has(agent.id));
    const groupedMessages = useMemo(() => groupMessagesByRound(messages), [messages]);
    const stopConditions = brainstorm.stop_conditions ?? {};
    const roundSummaries = useMemo(
        () => (brainstorm.decision_log ?? []).filter((entry) => entry.type === "round_summary"),
        [brainstorm.decision_log],
    );
    const finalEntries = useMemo(
        () => (brainstorm.decision_log ?? []).filter((entry) => entry.type === "final_output"),
        [brainstorm.decision_log],
    );

    const refreshAll = async () => {
        await Promise.all([
            queryClient.invalidateQueries({ queryKey: ["orchestration", "brainstorm", brainstormId] }),
            queryClient.invalidateQueries({ queryKey: ["orchestration", "brainstorm", brainstormId, "participants"] }),
            queryClient.invalidateQueries({ queryKey: ["orchestration", "brainstorm", brainstormId, "messages"] }),
            queryClient.invalidateQueries({
                queryKey: ["orchestration", "brainstorm", brainstormId, "discourse-insights"],
            }),
            brainstorm.project_id
                ? queryClient.invalidateQueries({
                      queryKey: ["orchestration", "brainstorm", brainstorm.project_id, "runs"],
                  })
                : Promise.resolve(),
            queryClient.invalidateQueries({ queryKey: ["orchestration", "brainstorms"] }),
        ]);
    };

    const promoteTasksMutation = useMutation({
        mutationFn: () => promoteBrainstorm(brainstormId),
        onSuccess: async (tasks) => {
            await refreshAll();
            showToast({ message: `${tasks.length} tasks promoted.`, severity: "success" });
        },
    });
    const promoteAdrMutation = useMutation({
        mutationFn: () => promoteBrainstormAdr(brainstormId),
        onSuccess: async () => {
            await refreshAll();
            showToast({ message: "Brainstorm promoted to ADR.", severity: "success" });
        },
    });
    const promoteDocumentMutation = useMutation({
        mutationFn: () => promoteBrainstormDocument(brainstormId),
        onSuccess: async () => {
            await refreshAll();
            showToast({ message: "Brainstorm promoted to project document.", severity: "success" });
        },
    });
    const startMutation = useMutation({
        mutationFn: () => startBrainstorm(brainstormId),
        onSuccess: async () => {
            await refreshAll();
            showToast({ message: "Brainstorm round queued.", severity: "success" });
        },
    });
    const nextRoundMutation = useMutation({
        mutationFn: () => startBrainstormNextRound(brainstormId),
        onSuccess: async () => {
            await refreshAll();
            showToast({ message: "Next brainstorm round queued.", severity: "success" });
        },
    });
    const summaryMutation = useMutation({
        mutationFn: () => forceBrainstormSummary(brainstormId),
        onSuccess: async () => {
            await refreshAll();
            showToast({ message: "Final recommendation generated.", severity: "success" });
        },
    });
    const addParticipantMutation = useMutation({
        mutationFn: () => addBrainstormParticipant(brainstormId, { agent_id: newParticipantId }),
        onSuccess: async () => {
            setNewParticipantId("");
            await refreshAll();
            showToast({ message: "Participant added.", severity: "success" });
        },
    });
    const removeParticipantMutation = useMutation({
        mutationFn: (participantId: string) => removeBrainstormParticipant(brainstormId, participantId),
        onSuccess: refreshAll,
    });
    const stanceMutation = useMutation({
        mutationFn: ({ participantId, stance }: { participantId: string; stance: string }) =>
            updateBrainstormParticipant(brainstormId, participantId, { stance: stance.trim() || null }),
        onSuccess: refreshAll,
    });
    const exportArtifactMutation = useMutation({
        mutationFn: () => exportBrainstormArtifact(brainstormId),
        onSuccess: async (artifact) => {
            await refreshAll();
            showToast({
                message: `${humanizeKey(artifact.output_type)} exported to ${humanizeKey(artifact.artifact_kind)}.`,
                severity: "success",
            });
        },
    });

    return {
        participants,
        agents,
        projectAgents,
        groupedMessages,
        discourse,
        stopConditions,
        roundSummaries,
        finalEntries,
        newParticipantId,
        setNewParticipantId,
        participantStances,
        setParticipantStances,
        promoteTasksMutation,
        promoteAdrMutation,
        promoteDocumentMutation,
        startMutation,
        nextRoundMutation,
        summaryMutation,
        addParticipantMutation,
        removeParticipantMutation,
        stanceMutation,
        exportArtifactMutation,
    };
}
