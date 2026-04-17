import { useCallback, useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
    Alert,
    Avatar,
    Box,
    Button,
    Chip,
    CircularProgress,
    Paper,
    Stack,
    Typography,
} from "@mui/material";
import {
    AutoAwesome as SummaryIcon,
    ArrowForward as NextRoundIcon,
    Assignment as TaskIcon,
    Description as DocumentIcon,
    Rule as AdrIcon,
} from "@mui/icons-material";
import { useNavigate, useParams } from "react-router-dom";
import {
    forceBrainstormSummary,
    getBrainstorm,
    getBrainstormDiscourseInsights,
    listAgents,
    listBrainstormMessages,
    listBrainstormParticipants,
    listRuns,
    promoteBrainstorm,
    promoteBrainstormAdr,
    promoteBrainstormDocument,
    startBrainstormNextRound,
} from "../api/orchestration";
import { useSnackbar } from "../app/snackbarContext";
import { PageHeader } from "../components/ui/PageHeader";
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
    const { data: runs = [] } = useQuery({
        queryKey: ["orchestration", "brainstorm", brainstorm?.project_id, "runs"],
        queryFn: () => listRuns(brainstorm?.project_id),
        enabled: Boolean(brainstorm?.project_id),
    });

    const roomRuns = useMemo(
        () => runs.filter((item) => item.brainstorm_id === brainstormId),
        [runs, brainstormId],
    );
    const totalCostUsd = roomRuns.reduce((sum, item) => sum + item.estimated_cost_micros / 1_000_000, 0);
    const currentRound = brainstorm?.current_round ?? 0;
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

    const exportMarkdown = useCallback(() => {
        if (!brainstorm) return;
        const lines: string[] = [
            `# Brainstorm: ${brainstorm.topic}`,
            "",
            `Status: ${brainstorm.status} · Mode: ${brainstorm.mode} · Output: ${brainstorm.output_type}`,
            "",
            "## Messages",
            "",
        ];
        groupedMessages.forEach(([round, roundMessages]) => {
            lines.push(`### Round ${round}`, "");
            roundMessages.forEach((m) => {
                lines.push(`- **${m.agent_id}** (${m.message_type}):`, "", m.content, "");
            });
        });
        const blob = new Blob([lines.join("\n")], { type: "text/markdown;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `brainstorm-${brainstormId}.md`;
        a.click();
        URL.revokeObjectURL(url);
    }, [brainstorm, brainstormId, groupedMessages]);

    const exportJson = useCallback(() => {
        if (!brainstorm) return;
        const blob = new Blob(
            [JSON.stringify({ brainstorm, messages, participants, discourse }, null, 2)],
            { type: "application/json;charset=utf-8" },
        );
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `brainstorm-${brainstormId}.json`;
        a.click();
        URL.revokeObjectURL(url);
    }, [brainstorm, brainstormId, discourse, messages, participants]);

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

    const nextRoundMutation = useMutation({
        mutationFn: () => startBrainstormNextRound(brainstormId),
        onSuccess: async () => {
            await refreshAll();
            showToast({ message: "Next brainstorm round queued.", severity: "success" });
        },
    });
    const forceSummaryMutation = useMutation({
        mutationFn: () => forceBrainstormSummary(brainstormId),
        onSuccess: async () => {
            await refreshAll();
            showToast({ message: "Final summary generated.", severity: "success" });
        },
    });
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

    if (isLoading || !brainstorm) {
        return (
            <PageShell maxWidth="xl">
                <Typography color="text.secondary">Loading brainstorm room...</Typography>
            </PageShell>
        );
    }

    return (
        <PageShell maxWidth="xl">
            <PageHeader
                eyebrow="Brainstorm Room"
                title={brainstorm.topic}
                description={brainstorm.latest_round_summary || brainstorm.summary || "Structured multi-agent discussion room."}
                actions={(
                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                        <Button
                            variant="contained"
                            startIcon={nextRoundMutation.isPending ? <CircularProgress size={14} /> : <NextRoundIcon />}
                            onClick={() => nextRoundMutation.mutate()}
                            disabled={brainstorm.status === "completed" || currentRound >= brainstorm.max_rounds || nextRoundMutation.isPending}
                        >
                            Start next round
                        </Button>
                        <Button
                            variant="outlined"
                            startIcon={<SummaryIcon />}
                            onClick={() => forceSummaryMutation.mutate()}
                            disabled={forceSummaryMutation.isPending}
                        >
                            Force summary
                        </Button>
                        <Button variant="text" onClick={exportMarkdown}>
                            Export Markdown
                        </Button>
                        <Button variant="text" onClick={exportJson}>
                            Export JSON
                        </Button>
                    </Stack>
                )}
                meta={(
                    <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                        <Chip label={humanizeKey(brainstorm.mode)} size="small" color="secondary" variant="outlined" />
                        <Chip label={humanizeKey(brainstorm.output_type)} size="small" variant="outlined" />
                        <Chip label={`Round ${currentRound}/${brainstorm.max_rounds}`} size="small" variant="outlined" />
                        <Chip label={`$${totalCostUsd.toFixed(4)}`} size="small" variant="outlined" />
                        <Chip label={humanizeKey(brainstorm.consensus_status)} size="small" color={consensusColor} />
                        {discourse?.conflict_signal ? (
                            <Chip label="Conflict signal" size="small" color="warning" variant="outlined" />
                        ) : null}
                    </Stack>
                )}
            />

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
                                                <Paper key={message.id} sx={{ p: 1.5, borderRadius: 3 }}>
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
                                <Paper key={`round-summary-${index}`} variant="outlined" sx={{ p: 1.25, borderRadius: 2 }}>
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
                                <Paper key={`final-output-${index}`} variant="outlined" sx={{ p: 1.25, borderRadius: 2 }}>
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
                            {participants.map((participant) => {
                                const agent = agents.find((item) => item.id === participant.agent_id);
                                return (
                                    <Stack key={participant.id} direction="row" spacing={1} alignItems="center">
                                        <Avatar sx={{ width: 28, height: 28 }}>{initials(agent?.name || "AI")}</Avatar>
                                        <Box>
                                            <Typography variant="body2">{agent?.name || participant.agent_id}</Typography>
                                            <Typography variant="caption" color="text.secondary">
                                                {agent?.role || "participant"}
                                            </Typography>
                                        </Box>
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
