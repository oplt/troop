import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link as RouterLink, useNavigate, useParams } from "react-router-dom";
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
    EmojiEvents as LeaderboardIcon,
    HourglassEmpty as PendingIcon,
    FolderOpen as ProjectsIcon,
} from "@mui/icons-material";
import {
    applyAgentPattern,
    benchmarkAgentPattern,
    createEvalRecord,
    enableAgentPattern,
    getEvalLeaderboard,
    listAgentPatterns,
    listAgents,
    listEvalRecords,
    listOrchestrationTasks,
    listProjectAgentPatterns,
    scoreAgentPatternEval,
    scoreEvalRecord,
    startBenchmark,
    startHistoricalBenchmarks,
    updateEvalRecord,
    type AgentPattern,
    type AgentPatternStatus,
    type EvalRecord,
} from "../api/orchestration";
import { useSnackbar } from "../app/snackbarContext";
import { AnalyticsKpiStrip } from "../components/ui/AnalyticsKpiStrip";
import { EmptyState } from "../components/ui/EmptyState";
import { PageHeader } from "../components/ui/PageHeader";
import { PageShell } from "../components/ui/PageShell";
import { SectionCard } from "../components/ui/SectionCard";
import { StatCard } from "../components/ui/StatCard";
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
                        <Typography variant="subtitle1" sx={{ fontWeight: 500 }}>{ev.name}</Typography>
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
                                    borderRadius: 1,
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

function patternStatusLabel(status: AgentPatternStatus["status"], evalReady: boolean): string {
    if (status === "released") return "Enabled";
    if (evalReady) return "Ready to enable";
    if (status === "eval_pending") return "Eval pending";
    return "Disabled";
}

function patternStatusColor(
    status: AgentPatternStatus["status"],
    evalReady: boolean,
): "success" | "warning" | "info" | "default" {
    if (status === "released") return "success";
    if (evalReady) return "info";
    if (status === "eval_pending") return "warning";
    return "default";
}

function AgentPatternsPanel({
    projectId,
    patterns,
    statuses,
    tasks,
    agents,
}: {
    projectId: string;
    patterns: AgentPattern[];
    statuses: AgentPatternStatus[];
    tasks: Array<{ id: string; title: string }>;
    agents: Array<{ id: string; name: string }>;
}) {
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();
    const [benchForm, setBenchForm] = useState<Record<string, { task_id: string; agent_id: string }>>({});

    const statusById = Object.fromEntries(statuses.map((s) => [s.pattern_id, s]));

    const invalidate = () => {
        queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "agent-patterns"] });
        queryClient.invalidateQueries({ queryKey: ["orchestration", "project", projectId, "evals"] });
    };

    const applyMutation = useMutation({
        mutationFn: (patternId: string) => applyAgentPattern(projectId, patternId),
        onSuccess: () => {
            invalidate();
            showToast({ message: "Pattern applied — run a benchmark before enabling.", severity: "success" });
        },
    });

    const benchmarkMutation = useMutation({
        mutationFn: ({ patternId, taskId, agentId }: { patternId: string; taskId: string; agentId: string }) =>
            benchmarkAgentPattern(projectId, patternId, { task_id: taskId, agent_id: agentId }),
        onSuccess: (result) => {
            invalidate();
            showToast({ message: `Pattern benchmark launched (${result.runs.length} runs).`, severity: "success" });
        },
    });

    const scoreMutation = useMutation({
        mutationFn: ({ evalId }: { evalId: string }) => scoreAgentPatternEval(projectId, evalId),
        onSuccess: (result) => {
            invalidate();
            const released = Boolean(result.advantage?.released);
            showToast({
                message: released
                    ? "Pattern passed eval gate — you can enable it."
                    : "Pattern did not beat baseline on quality/latency/cost.",
                severity: released ? "success" : "warning",
            });
        },
    });

    const enableMutation = useMutation({
        mutationFn: (patternId: string) => enableAgentPattern(projectId, patternId),
        onSuccess: () => {
            invalidate();
            showToast({ message: "Pattern enabled for this project.", severity: "success" });
        },
    });

    return (
        <SectionCard
            title="Multi-agent patterns"
            description="Curated patterns release only after evals show quality/latency/cost advantage vs single-agent baseline."
        >
            <Stack spacing={2}>
                {patterns.map((pattern) => {
                    const status = statusById[pattern.id];
                    const form = benchForm[pattern.id] ?? { task_id: "", agent_id: "" };
                    return (
                        <Paper key={pattern.id} sx={{ p: 2, borderRadius: 2, border: 1, borderColor: "divider" }}>
                            <Stack spacing={1.5}>
                                <Stack direction="row" justifyContent="space-between" alignItems="flex-start" gap={1}>
                                    <Box>
                                        <Typography variant="subtitle2">{pattern.name}</Typography>
                                        <Typography variant="body2" color="text.secondary">{pattern.description}</Typography>
                                        <Typography variant="caption" color="text.secondary">
                                            {pattern.baseline_run_mode} → {pattern.pattern_run_mode}
                                        </Typography>
                                    </Box>
                                    <Chip
                                        size="small"
                                        label={patternStatusLabel(status?.status ?? "disabled", Boolean(status?.eval_ready))}
                                        color={patternStatusColor(status?.status ?? "disabled", Boolean(status?.eval_ready))}
                                        variant="outlined"
                                    />
                                </Stack>
                                <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
                                    <TextField
                                        select
                                        size="small"
                                        label="Task"
                                        value={form.task_id}
                                        onChange={(e) =>
                                            setBenchForm((prev) => ({
                                                ...prev,
                                                [pattern.id]: { ...form, task_id: e.target.value },
                                            }))
                                        }
                                        sx={{ minWidth: 180, flex: 1 }}
                                    >
                                        <MenuItem value="">Select task</MenuItem>
                                        {tasks.map((t) => (
                                            <MenuItem key={t.id} value={t.id}>{t.title}</MenuItem>
                                        ))}
                                    </TextField>
                                    <TextField
                                        select
                                        size="small"
                                        label="Agent"
                                        value={form.agent_id}
                                        onChange={(e) =>
                                            setBenchForm((prev) => ({
                                                ...prev,
                                                [pattern.id]: { ...form, agent_id: e.target.value },
                                            }))
                                        }
                                        sx={{ minWidth: 160, flex: 1 }}
                                    >
                                        <MenuItem value="">Select agent</MenuItem>
                                        {agents.map((a) => (
                                            <MenuItem key={a.id} value={a.id}>{a.name}</MenuItem>
                                        ))}
                                    </TextField>
                                </Stack>
                                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                                    <Button
                                        size="small"
                                        variant="outlined"
                                        disabled={applyMutation.isPending}
                                        onClick={() => applyMutation.mutate(pattern.id)}
                                    >
                                        Apply
                                    </Button>
                                    <Button
                                        size="small"
                                        variant="contained"
                                        startIcon={<RunIcon />}
                                        disabled={
                                            !form.task_id ||
                                            !form.agent_id ||
                                            benchmarkMutation.isPending
                                        }
                                        onClick={() =>
                                            benchmarkMutation.mutate({
                                                patternId: pattern.id,
                                                taskId: form.task_id,
                                                agentId: form.agent_id,
                                            })
                                        }
                                    >
                                        Benchmark vs baseline
                                    </Button>
                                    {status?.last_eval_id && (
                                        <Button
                                            size="small"
                                            variant="outlined"
                                            disabled={scoreMutation.isPending}
                                            onClick={() => scoreMutation.mutate({ evalId: status.last_eval_id! })}
                                        >
                                            Score eval
                                        </Button>
                                    )}
                                    <Button
                                        size="small"
                                        variant="outlined"
                                        color="success"
                                        disabled={!status?.eval_ready || enableMutation.isPending}
                                        onClick={() => enableMutation.mutate(pattern.id)}
                                    >
                                        Enable
                                    </Button>
                                </Stack>
                            </Stack>
                        </Paper>
                    );
                })}
            </Stack>
        </SectionCard>
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
    const { data: agentPatterns = [] } = useQuery({
        queryKey: ["orchestration", "agent-patterns"],
        queryFn: () => listAgentPatterns(),
    });
    const { data: patternStatuses } = useQuery({
        queryKey: ["orchestration", "project", projectId, "agent-patterns"],
        queryFn: () => listProjectAgentPatterns(projectId!),
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

    const pendingCount = evals.filter((ev) => !ev.winner).length;
    const decidedCount = evals.filter((ev) => Boolean(ev.winner)).length;

    return (
        <PageShell maxWidth="xl" variant="browse">
            <PageHeader
                title="Benchmarks"
                description="Compare agents and models on shared tasks, then rank winners on the leaderboard."
            />

            <AnalyticsKpiStrip columns={{ xs: 1, sm: 2, md: 4, lg: 4 }}>
                <StatCard label="Benchmarks" value={evals.length} description="Eval records in this project" icon={<BenchmarkIcon />} loading={isLoading} />
                <StatCard label="Pending" value={pendingCount} description="Awaiting a winner decision" icon={<PendingIcon />} color="warning" loading={isLoading} />
                <StatCard label="Decided" value={decidedCount} description="A/B/tie outcomes saved" icon={<WinIcon />} color="success" loading={isLoading} />
                <StatCard label="Leaderboard" value={leaderboard.length} description="Agents ranked by win rate" icon={<LeaderboardIcon />} color="secondary" loading={isLoading} />
            </AnalyticsKpiStrip>

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
                                <Paper key={entry.agent_id} sx={{ p: 1.5, borderRadius: 1, border: 1, borderColor: "divider" }}>
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
                            description="Use New benchmark on the left, or open projects and run a task first."
                            action={
                                <Button component={RouterLink} to="/projects" variant="contained" size="small" startIcon={<ProjectsIcon />}>
                                    Open projects
                                </Button>
                            }
                        />
                    )}
                    {evals.map((ev) => (
                        <EvalCard key={ev.id} eval={ev} projectId={projectId!} />
                    ))}
                </Stack>
            </Box>

            {projectId && agentPatterns.length > 0 && (
                <AgentPatternsPanel
                    projectId={projectId}
                    patterns={agentPatterns}
                    statuses={patternStatuses?.patterns ?? []}
                    tasks={tasks}
                    agents={agents}
                />
            )}
        </PageShell>
    );
}
