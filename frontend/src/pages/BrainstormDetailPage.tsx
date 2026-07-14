import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
    Alert,
    Avatar,
    Box,
    Button,
    Chip,
    Divider,
    MenuItem,
    Paper,
    Stack,
    TextField,
    Typography,
} from "@mui/material";
import {
    Assignment as TaskIcon,
    Description as DocumentIcon,
    DeleteOutline as RemoveIcon,
    PlayArrow as StartIcon,
    Rule as AdrIcon,
    Summarize as SummaryIcon,
} from "@mui/icons-material";
import { useNavigate, useParams } from "react-router-dom";
import {
    addBrainstormParticipant,
    exportBrainstormArtifact,
    forceBrainstormSummary,
    getBrainstorm,
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
} from "../api/orchestration";
import { useSnackbar } from "../app/snackbarContext";
import { PageShell } from "../components/ui/PageShell";
import { SectionCard } from "../components/ui/SectionCard";
import { formatDateTime, humanizeKey } from "../utils/formatters";

function initials(value: string) {
    return value
        .split(" ")
        .map((part) => part[0] ?? "")
        .join("")
        .slice(0, 2)
        .toUpperCase();
}

export default function BrainstormDetailPage() {
    const { brainstormId = "" } = useParams();
    const navigate = useNavigate();
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();

    const { data: brainstorm, isLoading } = useQuery({
        queryKey: ["orchestration", "brainstorm", brainstormId],
        queryFn: () => getBrainstorm(brainstormId),
        enabled: Boolean(brainstormId),
    });
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
        queryKey: ["orchestration", "project", brainstorm?.project_id, "agents"],
        queryFn: () => listProjectAgents(brainstorm!.project_id),
        enabled: Boolean(brainstorm?.project_id),
    });
    const projectAgentIds = useMemo(() => new Set(projectMembers.map((member) => member.agent_id)), [projectMembers]);
    const projectAgents = agents.filter((agent) => projectAgentIds.has(agent.id));
    const [newParticipantId, setNewParticipantId] = useState("");
    const [participantStances, setParticipantStances] = useState<Record<string, string>>({});
    const groupedMessages = useMemo(() => {
        const grouped = new Map<number, typeof messages>();
        messages.forEach((message) => {
            const bucket = grouped.get(message.round_number) ?? [];
            bucket.push(message);
            grouped.set(message.round_number, bucket);
        });
        return [...grouped.entries()].sort((left, right) => left[0] - right[0]);
    }, [messages]);

    const consensusColor =
        brainstorm?.consensus_status === "consensus" || brainstorm?.consensus_status === "soft_consensus"
            ? "success"
            : brainstorm?.consensus_status === "loop_detected" || brainstorm?.consensus_status === "conflict"
                ? "warning"
                : "default";
    const stopConditions = brainstorm?.stop_conditions ?? {};
    const roundSummaries = useMemo(
        () => (brainstorm?.decision_log ?? []).filter((entry) => entry.type === "round_summary"),
        [brainstorm?.decision_log],
    );
    const finalEntries = useMemo(
        () => (brainstorm?.decision_log ?? []).filter((entry) => entry.type === "final_output"),
        [brainstorm?.decision_log],
    );

    const refreshAll = async () => {
        await Promise.all([
            queryClient.invalidateQueries({ queryKey: ["orchestration", "brainstorm", brainstormId] }),
            queryClient.invalidateQueries({ queryKey: ["orchestration", "brainstorm", brainstormId, "participants"] }),
            queryClient.invalidateQueries({ queryKey: ["orchestration", "brainstorm", brainstormId, "messages"] }),
            queryClient.invalidateQueries({ queryKey: ["orchestration", "brainstorm", brainstormId, "discourse-insights"] }),
            brainstorm?.project_id
                ? queryClient.invalidateQueries({ queryKey: ["orchestration", "brainstorm", brainstorm.project_id, "runs"] })
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
            showToast({ message: `${humanizeKey(artifact.output_type)} exported to ${humanizeKey(artifact.artifact_kind)}.`, severity: "success" });
        },
    });

    if (isLoading || !brainstorm) {
        return (
            <PageShell maxWidth="xl">
                <Typography color="text.secondary">Loading brainstorm room...</Typography>
            </PageShell>
        );
    }

    return (
        <PageShell maxWidth="xl">

            <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", xl: "minmax(0, 1.6fr) 360px" }, alignItems: "start" }}>
                <SectionCard title="Discussion thread" description="Chat-style transcript grouped by round.">
                    <Stack spacing={2}>
                        {groupedMessages.length === 0 ? (
                            <Alert severity="info">No discussion messages yet.</Alert>
                        ) : (
                            groupedMessages.map(([round, roundMessages]) => (
                                <Box key={round}>
                                    <Typography variant="overline" color="text.secondary">Round {round}</Typography>
                                    <Stack spacing={1.25} sx={{ mt: 1 }}>
                                        {roundMessages.map((message) => {
                                            const agent = agents.find((item) => item.id === message.agent_id);
                                            return (
                                                <Paper key={message.id} sx={{ p: 1.5, borderRadius: 1 }}>
                                                    <Stack direction="row" spacing={1.5} alignItems="flex-start">
                                                        <Avatar sx={{ width: 34, height: 34 }}>
                                                            {initials(agent?.name || "AI")}
                                                        </Avatar>
                                                        <Box sx={{ flex: 1 }}>
                                                            <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                                                                <Typography variant="subtitle2">{agent?.name || "Moderator"}</Typography>
                                                                <Chip label={message.message_type} size="small" variant="outlined" />
                                                                <Typography variant="caption" color="text.secondary">{formatDateTime(message.created_at)}</Typography>
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
                </SectionCard>

                <Stack spacing={2}>
                    <SectionCard title="Room status" description="Participants, consensus signal, summaries, and promotion actions.">
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
                                    onClick={() => (brainstorm.current_round === 0 ? startMutation : nextRoundMutation).mutate()}
                                    disabled={startMutation.isPending || nextRoundMutation.isPending || brainstorm.status === "completed" || brainstorm.current_round >= brainstorm.max_rounds}
                                >
                                    {brainstorm.current_round === 0 ? "Start round" : "Run another round"}
                                </Button>
                                <Button
                                    size="small"
                                    variant="outlined"
                                    startIcon={<SummaryIcon />}
                                    onClick={() => summaryMutation.mutate()}
                                    disabled={summaryMutation.isPending || brainstorm.status === "completed" || participants.length < 2}
                                >
                                    Force final recommendation
                                </Button>
                            </Stack>
                            <Typography variant="body2" color="text.secondary">
                                Last updated: {formatDateTime(brainstorm.updated_at)}
                            </Typography>
                            <Typography variant="body2" color="text.secondary">
                                Moderator: {agents.find((item) => item.id === brainstorm.moderator_agent_id)?.name || brainstorm.moderator_agent_id || "Auto"}
                            </Typography>
                            <Typography variant="subtitle2" sx={{ mt: 1 }}>Consensus</Typography>
                            <Chip label={humanizeKey(brainstorm.consensus_status)} color={consensusColor} size="small" />
                            {brainstorm.consensus_status === "conflict" ? (
                                <Alert severity="warning">The room detected split positions with low similarity. Use the moderator summary before spending another round.</Alert>
                            ) : null}
                            <Typography variant="subtitle2" sx={{ mt: 1 }}>Latest round summary</Typography>
                            <Typography variant="body2" color="text.secondary">
                                {brainstorm.latest_round_summary || "No round summary yet."}
                            </Typography>
                            <Typography variant="subtitle2" sx={{ mt: 1 }}>Final output</Typography>
                            <Typography variant="body2" color="text.secondary" sx={{ whiteSpace: "pre-wrap" }}>
                                {brainstorm.final_recommendation || brainstorm.summary || "No final output yet."}
                            </Typography>
                        </Stack>
                    </SectionCard>

                    <SectionCard
                        title="Discourse signals"
                        description="Lightweight repetition and vocabulary hints to spot circular debate before you burn more rounds."
                    >
                        {discourse ? (
                            <Stack spacing={1}>
                                <Typography variant="body2" color="text.secondary">
                                    Messages: {discourse.message_count} · Rounds with traffic: {discourse.rounds_with_messages}{" "}
                                    · Adjacent same-agent ratio: {(discourse.same_agent_streak_ratio * 100).toFixed(1)}%
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
                        ) : (
                            <Typography variant="body2" color="text.secondary">
                                Computing discourse hints…
                            </Typography>
                        )}
                    </SectionCard>

                    <SectionCard title="Guardrails" description="Room mode, stop conditions, and moderator thresholds.">
                        <Stack spacing={1}>
                            <Typography variant="body2" color="text.secondary">
                                Stop on consensus: {stopConditions.stop_on_consensus ? "yes" : "no"} · Accept soft consensus: {stopConditions.accept_soft_consensus ? "yes" : "no"}
                            </Typography>
                            <Typography variant="body2" color="text.secondary">
                                Escalate on no consensus: {stopConditions.escalate_on_no_consensus ? "yes" : "no"} · Conflict requires moderation: {stopConditions.conflict_requires_moderation ? "yes" : "no"}
                            </Typography>
                            <Typography variant="body2" color="text.secondary">
                                Cost cap: ${Number(stopConditions.max_cost_usd ?? 0).toFixed(2)} · Loop threshold: {(Number(stopConditions.max_repetition_score ?? 0) * 100).toFixed(1)}%
                            </Typography>
                            <Typography variant="body2" color="text.secondary">
                                Soft-consensus floor: {(Number(stopConditions.soft_consensus_min_similarity ?? 0) * 100).toFixed(1)}% · Conflict ceiling: {(Number(stopConditions.conflict_pairwise_max_similarity ?? 0) * 100).toFixed(1)}%
                            </Typography>
                        </Stack>
                    </SectionCard>

                    <SectionCard title="Moderator log" description="Round summaries and finalization records captured in the room decision log.">
                        <Stack spacing={1}>
                            {roundSummaries.map((entry, index) => (
                                <Paper key={`round-summary-${index}`} variant="outlined" sx={{ p: 1.25, borderRadius: 1 }}>
                                    <Typography variant="subtitle2">Round {String(entry.round ?? index + 1)}</Typography>
                                    <Typography variant="caption" color="text.secondary">
                                        Consensus: {humanizeKey(String(entry.consensus_kind ?? "open"))}
                                        {" · "}
                                        Conflict: {entry.conflict_signal ? "yes" : "no"}
                                        {" · "}
                                        Repetition: {entry.repetition_score != null ? `${(Number(entry.repetition_score) * 100).toFixed(1)}%` : "n/a"}
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
                                        Reason: {humanizeKey(String(entry.reason ?? "completed"))} · Output: {humanizeKey(String(entry.output_type ?? brainstorm.output_type))}
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
                    </SectionCard>

                    <SectionCard title="Participants" description="Agents currently taking part in the room.">
                        <Stack spacing={1}>
                            <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
                                <TextField
                                    select
                                    size="small"
                                    label="Add project agent"
                                    value={newParticipantId}
                                    onChange={(event) => setNewParticipantId(event.target.value)}
                                    disabled={brainstorm.status === "running" || brainstorm.status === "completed"}
                                    fullWidth
                                >
                                    <MenuItem value="">Select an agent</MenuItem>
                                    {projectAgents
                                        .filter((agent) => !participants.some((participant) => participant.agent_id === agent.id))
                                        .map((agent) => (
                                            <MenuItem key={agent.id} value={agent.id}>{agent.name}</MenuItem>
                                        ))}
                                </TextField>
                                <Button
                                    variant="outlined"
                                    onClick={() => addParticipantMutation.mutate()}
                                    disabled={!newParticipantId || addParticipantMutation.isPending || brainstorm.status === "running" || brainstorm.status === "completed"}
                                >
                                    Add
                                </Button>
                            </Stack>
                            <Divider />
                            {participants.map((participant) => {
                                const agent = agents.find((item) => item.id === participant.agent_id);
                                const stance = participantStances[participant.id] ?? participant.stance ?? "";
                                return (
                                    <Stack key={participant.id} direction="row" spacing={1} alignItems="center">
                                        <Avatar sx={{ width: 28, height: 28 }}>{initials(agent?.name || "AI")}</Avatar>
                                        <Box sx={{ flex: 1, minWidth: 0 }}>
                                            <Typography variant="body2">{agent?.name || participant.agent_id}</Typography>
                                            <TextField
                                                size="small"
                                                variant="standard"
                                                placeholder="Optional stance or focus"
                                                value={stance}
                                                onChange={(event) => setParticipantStances((current) => ({ ...current, [participant.id]: event.target.value }))}
                                                onBlur={() => stanceMutation.mutate({ participantId: participant.id, stance })}
                                                disabled={brainstorm.status === "running" || brainstorm.status === "completed"}
                                                fullWidth
                                            />
                                        </Box>
                                        <Button
                                            size="small"
                                            color="error"
                                            aria-label={`Remove ${agent?.name || "participant"}`}
                                            onClick={() => removeParticipantMutation.mutate(participant.id)}
                                            disabled={participants.length <= 2 || removeParticipantMutation.isPending || brainstorm.status === "running" || brainstorm.status === "completed"}
                                        >
                                            <RemoveIcon fontSize="small" />
                                        </Button>
                                    </Stack>
                                );
                            })}
                        </Stack>
                    </SectionCard>

                    <SectionCard title="Promote output" description="Turn the final room output into operational records.">
                        <Stack spacing={1}>
                            <Button startIcon={<TaskIcon />} variant="contained" onClick={() => promoteTasksMutation.mutate()} disabled={promoteTasksMutation.isPending}>
                                Promote to task
                            </Button>
                            <Button startIcon={<AdrIcon />} variant="outlined" onClick={() => promoteAdrMutation.mutate()} disabled={promoteAdrMutation.isPending}>
                                Promote to ADR
                            </Button>
                            <Button startIcon={<DocumentIcon />} variant="outlined" onClick={() => promoteDocumentMutation.mutate()} disabled={promoteDocumentMutation.isPending}>
                                Promote to project document
                            </Button>
                            <Button
                                startIcon={<DocumentIcon />}
                                variant="outlined"
                                onClick={() => exportArtifactMutation.mutate()}
                                disabled={exportArtifactMutation.isPending || !brainstorm.final_recommendation}
                            >
                                Export as first-class artifact
                            </Button>
                            {brainstorm.project_id && (
                                <Button variant="text" onClick={() => navigate(`/agent-projects/${brainstorm.project_id}`)}>
                                    Open project
                                </Button>
                            )}
                        </Stack>
                    </SectionCard>
                </Stack>
            </Box>
        </PageShell>
    );
}
