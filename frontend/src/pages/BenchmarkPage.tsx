import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import {
    Alert,
    Box,
    Button,
    Chip,
    CircularProgress,
    MenuItem,
    Paper,
    Stack,
    TextField,
    Typography,
} from "@mui/material";
import {
    Science as BenchmarkIcon,
    PlayArrow as RunIcon,
    CheckCircle as WinIcon,
} from "@mui/icons-material";
import {
    createEvalRecord,
    getEvalLeaderboard,
    listAgents,
    listEvalRecords,
    listOrchestrationTasks,
    scoreEvalRecord,
    startBenchmark,
    startHistoricalBenchmarks,
    updateEvalRecord,
    type EvalRecord,
} from "../api/orchestration";
import { useSnackbar } from "../app/snackbarContext";
import { EmptyState } from "../components/ui/EmptyState";
import { PageHeader } from "../components/ui/PageHeader";
import { PageShell } from "../components/ui/PageShell";
import { SectionCard } from "../components/ui/SectionCard";
import { formatDateTime } from "../utils/formatters";

function winnerLabel(winner: string | null): string {
    if (winner === "a") return "Agent A wins";
    if (winner === "b") return "Agent B wins";
    if (winner === "tie") return "Tie";
    return "Undecided";
}

function winnerColor(winner: string | null): "success" | "info" | "default" {
    if (winner === "a" || winner === "b") return "success";
    if (winner === "tie") return "info";
    return "default";
}

function EvalCard({ eval: ev, projectId }: { eval: EvalRecord; projectId: string }) {
    const queryClient = useQueryClient();
    const navigate = useNavigate();
    const { showToast } = useSnackbar();
    const [notes, setNotes] = useState(ev.notes ?? "");

    const startMutation = useMutation({
        mutationFn: () => startBenchmark(projectId, ev.id),
        onSuccess: (result) => {
            queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "evals"] });
            showToast({ message: `Launched ${result.runs.length} benchmark runs.`, severity: "success" });
        },
    });

    const scoreMutation = useMutation({
        mutationFn: () => scoreEvalRecord(projectId, ev.id),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "evals"] });
            showToast({ message: "Acceptance scores and run metrics saved.", severity: "success" });
        },
    });

    const decideMutation = useMutation({
        mutationFn: (winner: "a" | "b" | "tie") =>
            updateEvalRecord(projectId, ev.id, { winner, notes: notes || undefined }),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "evals"] });
            showToast({ message: "Eval decision saved.", severity: "success" });
        },
    });

    const isPending = !ev.winner;

    return (
        <Paper sx={{ p: 2.5, borderRadius: 4, border: 1, borderColor: "divider" }}>
            <Stack spacing={1.5}>
                <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
                    <Box>
                        <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>{ev.name}</Typography>
                        <Typography variant="caption" color="text.secondary">{formatDateTime(ev.created_at)}</Typography>
                    </Box>
                    <Chip
                        label={winnerLabel(ev.winner)}
                        color={winnerColor(ev.winner)}
                        size="small"
                        icon={ev.winner ? <WinIcon fontSize="small" /> : undefined}
                    />
                </Stack>

                {/* A vs B summary */}
                <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 1.5 }}>
                    {(["A", "B"] as const).map((side) => {
                        const agentId = side === "A" ? ev.agent_a_id : ev.agent_b_id;
                        const model = side === "A" ? ev.model_a : ev.model_b;
                        const runId = side === "A" ? ev.run_a_id : ev.run_b_id;
                        const score = side === "A" ? ev.score_a : ev.score_b;
                        const criteriaMet = side === "A" ? ev.criteria_met_a : ev.criteria_met_b;
                        const isWinner = ev.winner === side.toLowerCase();

                        return (
                            <Paper
                                key={side}
                                sx={(theme) => ({
                                    p: 1.5,
                                    borderRadius: 2,
                                    border: `1px solid ${isWinner ? theme.palette.success.main : theme.palette.divider}`,
                                    bgcolor: isWinner ? `${theme.palette.success.main}10` : undefined,
                                })}
                            >
                                <Typography variant="subtitle2">Agent {side}</Typography>
                                {model && <Typography variant="caption" color="text.secondary" display="block">{model}</Typography>}
                                {!model && agentId && <Typography variant="caption" color="text.secondary" display="block">{agentId.slice(0, 8)}…</Typography>}
                                {score !== null && score !== undefined && (
                                    <Chip label={`Score: ${score}`} size="small" sx={{ mt: 0.5 }} />
                                )}
                                {criteriaMet !== null && criteriaMet !== undefined && (
                                    <Chip
                                        label={criteriaMet ? "Criteria met" : "Criteria failed"}
                                        color={criteriaMet ? "success" : "error"}
                                        size="small"
                                        sx={{ mt: 0.5, ml: 0.5 }}
                                    />
                                )}
                                {runId && (
                                    <Button size="small" variant="text" onClick={() => navigate(`/runs/${runId}`)} sx={{ mt: 0.5, display: "block", p: 0 }}>
                                        View run →
                                    </Button>
                                )}
                            </Paper>
                        );
                    })}
                </Box>

                {/* Launch runs button */}
                {!ev.run_a_id && !ev.run_b_id && (
                    <Button
                        variant="contained"
                        size="small"
                        startIcon={startMutation.isPending ? <CircularProgress size={14} /> : <RunIcon />}
                        disabled={startMutation.isPending}
                        onClick={() => startMutation.mutate()}
                    >
                        Launch benchmark runs
                    </Button>
                )}

                {ev.run_a_id && ev.run_b_id && (
                    <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                        <Button
                            size="small"
                            variant="outlined"
                            startIcon={scoreMutation.isPending ? <CircularProgress size={14} /> : undefined}
                            disabled={scoreMutation.isPending}
                            onClick={() => scoreMutation.mutate()}
                        >
                            Score acceptance & metrics
                        </Button>
                    </Stack>
                )}

                {(() => {
                    const raw = ev.metadata_json?.benchmark_run_metrics;
                    if (!raw || typeof raw !== "object") return null;
                    const m = raw as Record<string, { latency_ms?: number | null; cost_usd?: number; tokens?: number; status?: string }>;
                    return (
                        <Typography variant="caption" color="text.secondary" component="div" sx={{ mt: 0.5 }}>
                            {(Object.entries(m) as Array<[string, { latency_ms?: number | null; cost_usd?: number; tokens?: number; status?: string }]>).map(([side, row]) => (
                                <span key={side} style={{ display: "block" }}>
                                    Side {side.toUpperCase()}:{" "}
                                    {row.tokens != null ? `${row.tokens} tok` : "—"}
                                    {row.cost_usd != null ? ` · $${Number(row.cost_usd).toFixed(5)}` : ""}
                                    {row.latency_ms != null ? ` · ${row.latency_ms} ms` : ""}
                                    {row.status ? ` · ${row.status}` : ""}
                                </span>
                            ))}
                        </Typography>
                    );
                })()}

                {/* Decide winner */}
                {isPending && (ev.run_a_id || ev.run_b_id) && (
                    <>
                        <TextField
                            size="small"
                            label="Notes"
                            multiline
                            minRows={2}
                            value={notes}
                            onChange={(e) => setNotes(e.target.value)}
                        />
                        <Stack direction="row" spacing={1}>
                            <Button size="small" variant="outlined" color="success" disabled={decideMutation.isPending} onClick={() => decideMutation.mutate("a")}>A wins</Button>
                            <Button size="small" variant="outlined" color="success" disabled={decideMutation.isPending} onClick={() => decideMutation.mutate("b")}>B wins</Button>
                            <Button size="small" variant="outlined" disabled={decideMutation.isPending} onClick={() => decideMutation.mutate("tie")}>Tie</Button>
                        </Stack>
                    </>
                )}

                {ev.notes && (
                    <Alert severity="info" sx={{ py: 0.5 }}>
                        <Typography variant="caption">{ev.notes}</Typography>
                    </Alert>
                )}
            </Stack>
        </Paper>
    );
}

export default function BenchmarkPage() {
    const { projectId } = useParams<{ projectId: string }>();
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();

    const { data: evals = [], isLoading } = useQuery({
        queryKey: ["orchestration", "project", projectId, "evals"],
        queryFn: () => listEvalRecords(projectId!),
        enabled: Boolean(projectId),
    });
    const { data: tasks = [] } = useQuery({
        queryKey: ["orchestration", "project", projectId, "tasks"],
        queryFn: () => listOrchestrationTasks(projectId!),
        enabled: Boolean(projectId),
    });
    const { data: agents = [] } = useQuery({
        queryKey: ["orchestration", "agents"],
        queryFn: () => listAgents(),
    });
    const { data: leaderboard = [] } = useQuery({
        queryKey: ["orchestration", "project", projectId, "evals", "leaderboard"],
        queryFn: () => getEvalLeaderboard(projectId!),
        enabled: Boolean(projectId),
    });

    const [form, setForm] = useState({ name: "", task_id: "", agent_a_id: "", agent_b_id: "", model_a: "", model_b: "" });
    const [historicalForm, setHistoricalForm] = useState({ agent_a_id: "", agent_b_id: "", model_a: "", model_b: "", days: "60", limit: "8" });

    const createMutation = useMutation({
        mutationFn: () =>
            createEvalRecord(projectId!, {
                name: form.name,
                task_id: form.task_id || undefined,
                agent_a_id: form.agent_a_id || undefined,
                agent_b_id: form.agent_b_id || undefined,
                model_a: form.model_a || undefined,
                model_b: form.model_b || undefined,
            }),
        onSuccess: async () => {
            setForm({ name: "", task_id: "", agent_a_id: "", agent_b_id: "", model_a: "", model_b: "" });
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "evals"] });
            showToast({ message: "Benchmark created.", severity: "success" });
        },
    });
    const historicalMutation = useMutation({
        mutationFn: () => startHistoricalBenchmarks(projectId!, {
            agent_a_id: historicalForm.agent_a_id,
            agent_b_id: historicalForm.agent_b_id,
            model_a: historicalForm.model_a || undefined,
            model_b: historicalForm.model_b || undefined,
            days: Number(historicalForm.days || 60),
            limit: Number(historicalForm.limit || 8),
        }),
        onSuccess: async (result) => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "evals"] });
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "evals", "leaderboard"] });
            showToast({ message: `Started ${result.count} historical benchmarks.`, severity: "success" });
        },
    });

    return (
        <PageShell maxWidth="xl">
            <PageHeader
                eyebrow="Evaluation"
                title="Benchmark"
                description="Run the same task through two agents or models side-by-side. Score by acceptance criteria, cost, and latency."
                meta={<Chip label={`${evals.length} evals`} variant="outlined" />}
            />

            <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", lg: "340px minmax(0, 1fr)" } }}>
                {/* New eval form */}
                <SectionCard title="New benchmark" description="Configure agent A vs B and pick a task to evaluate.">
                    <Stack spacing={2}>
                        <TextField
                            label="Benchmark name"
                            value={form.name}
                            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                            size="small"
                        />
                        <TextField
                            select
                            label="Task to evaluate"
                            value={form.task_id}
                            onChange={(e) => setForm((f) => ({ ...f, task_id: e.target.value }))}
                            size="small"
                        >
                            <MenuItem value="">None</MenuItem>
                            {tasks.map((t) => <MenuItem key={t.id} value={t.id}>{t.title}</MenuItem>)}
                        </TextField>

                        <Typography variant="subtitle2" color="text.secondary">Agent A</Typography>
                        <TextField
                            select
                            label="Agent A"
                            value={form.agent_a_id}
                            onChange={(e) => setForm((f) => ({ ...f, agent_a_id: e.target.value }))}
                            size="small"
                        >
                            <MenuItem value="">Select agent</MenuItem>
                            {agents.map((a) => <MenuItem key={a.id} value={a.id}>{a.name}</MenuItem>)}
                        </TextField>
                        <TextField
                            label="Model A override"
                            value={form.model_a}
                            onChange={(e) => setForm((f) => ({ ...f, model_a: e.target.value }))}
                            size="small"
                            placeholder="e.g. gpt-4o"
                        />

                        <Typography variant="subtitle2" color="text.secondary">Agent B</Typography>
                        <TextField
                            select
                            label="Agent B"
                            value={form.agent_b_id}
                            onChange={(e) => setForm((f) => ({ ...f, agent_b_id: e.target.value }))}
                            size="small"
                        >
                            <MenuItem value="">Select agent</MenuItem>
                            {agents.map((a) => <MenuItem key={a.id} value={a.id}>{a.name}</MenuItem>)}
                        </TextField>
                        <TextField
                            label="Model B override"
                            value={form.model_b}
                            onChange={(e) => setForm((f) => ({ ...f, model_b: e.target.value }))}
                            size="small"
                            placeholder="e.g. gpt-4-turbo"
                        />

                        <Button
                            variant="contained"
                            startIcon={createMutation.isPending ? <CircularProgress size={16} /> : <BenchmarkIcon />}
                            disabled={!form.name || createMutation.isPending}
                            onClick={() => createMutation.mutate()}
                        >
                            Create benchmark
                        </Button>
                    </Stack>
                </SectionCard>
                <SectionCard title="Historical benchmark" description="Run A/B benchmarks across previously completed GitHub-linked issues.">
                    <Stack spacing={2}>
                        <TextField select label="Agent A" value={historicalForm.agent_a_id} onChange={(e) => setHistoricalForm((f) => ({ ...f, agent_a_id: e.target.value }))} size="small">
                            <MenuItem value="">Select agent</MenuItem>
                            {agents.map((a) => <MenuItem key={a.id} value={a.id}>{a.name}</MenuItem>)}
                        </TextField>
                        <TextField select label="Agent B" value={historicalForm.agent_b_id} onChange={(e) => setHistoricalForm((f) => ({ ...f, agent_b_id: e.target.value }))} size="small">
                            <MenuItem value="">Select agent</MenuItem>
                            {agents.map((a) => <MenuItem key={a.id} value={a.id}>{a.name}</MenuItem>)}
                        </TextField>
                        <TextField label="Days lookback" type="number" value={historicalForm.days} onChange={(e) => setHistoricalForm((f) => ({ ...f, days: e.target.value }))} size="small" />
                        <TextField label="Issue limit" type="number" value={historicalForm.limit} onChange={(e) => setHistoricalForm((f) => ({ ...f, limit: e.target.value }))} size="small" />
                        <Button
                            variant="outlined"
                            disabled={!historicalForm.agent_a_id || !historicalForm.agent_b_id || historicalMutation.isPending}
                            onClick={() => historicalMutation.mutate()}
                        >
                            Benchmark historical issues
                        </Button>
                    </Stack>
                </SectionCard>

                {/* Eval list */}
                <Stack spacing={2}>
                    <SectionCard title="Leaderboard" description="Aggregate benchmark performance ranking by win rate, score, cost, and latency.">
                        <Stack spacing={1}>
                            {leaderboard.map((entry, index) => (
                                <Paper key={entry.agent_id} sx={{ p: 1.5, borderRadius: 2, border: 1, borderColor: "divider" }}>
                                    <Stack direction="row" justifyContent="space-between" alignItems="center">
                                        <Typography variant="subtitle2">#{index + 1} {entry.agent_name}</Typography>
                                        <Chip label={`${(entry.win_rate * 100).toFixed(1)}% win`} size="small" color="success" variant="outlined" />
                                    </Stack>
                                    <Typography variant="caption" color="text.secondary">
                                        W/L/T {entry.wins}/{entry.losses}/{entry.ties} • score {entry.avg_score.toFixed(1)} • ${entry.avg_cost_usd.toFixed(5)} • {entry.avg_latency_ms.toFixed(0)} ms
                                    </Typography>
                                </Paper>
                            ))}
                            {leaderboard.length === 0 && (
                                <Typography variant="body2" color="text.secondary">No leaderboard data yet.</Typography>
                            )}
                        </Stack>
                    </SectionCard>
                    {isLoading && [1, 2].map((i) => (
                        <Paper key={i} sx={{ height: 180, borderRadius: 4 }} />
                    ))}
                    {!isLoading && evals.length === 0 && (
                        <EmptyState
                            icon={<BenchmarkIcon />}
                            title="No benchmarks yet"
                            description="Create your first benchmark to compare agents or models on a task."
                        />
                    )}
                    {evals.map((ev) => (
                        <EvalCard key={ev.id} eval={ev} projectId={projectId!} />
                    ))}
                </Stack>
            </Box>
        </PageShell>
    );
}
