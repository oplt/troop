import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
    Box,
    Button,
    Chip,
    Paper,
    Skeleton,
    Stack,
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableRow,
    Typography,
} from "@mui/material";
import {
    AccessTime as LatencyIcon,
    CheckCircleOutline as AcceptanceIcon,
    ErrorOutline as FailureIcon,
    Hub as ProviderIcon,
    PlayArrow as RunFirstIcon,
    Replay as RetryIcon,
    Speed as RunIcon,
    Token as TokenIcon,
} from "@mui/icons-material";
import { Link as RouterLink, useNavigate } from "react-router-dom";
import { getExecutionInsights, getProviderHealthSummary, type ExecutionRollup } from "../api/orchestration";
import { AnalyticsKpiStrip } from "../components/ui/AnalyticsKpiStrip";
import { DateRangeControl } from "../components/ui/DateRangeControl";
import { EmptyState } from "../components/ui/EmptyState";
import { PageHeader } from "../components/ui/PageHeader";
import { PageShell } from "../components/ui/PageShell";
import { SectionCard } from "../components/ui/SectionCard";
import { SectionError } from "../components/ui/SectionError";
import { StatCard } from "../components/ui/StatCard";
import { humanizeKey } from "../utils/formatters";

function RollupTable({ title, rows, emptyLabel }: { title: string; rows: ExecutionRollup[]; emptyLabel: string }) {
    return (
        <SectionCard title={title}>
            {rows.length === 0 ? (
                <Typography variant="body2" color="text.secondary">{emptyLabel}</Typography>
            ) : (
                <Table size="small" aria-label={title}>
                    <TableHead>
                        <TableRow>
                            <TableCell>Name</TableCell>
                            <TableCell align="right">Runs</TableCell>
                            <TableCell align="right">Tokens</TableCell>
                            <TableCell align="right">Cost</TableCell>
                            <TableCell align="right">Latency</TableCell>
                            <TableCell align="right">Retries</TableCell>
                            <TableCell align="right">Failures</TableCell>
                        </TableRow>
                    </TableHead>
                    <TableBody>
                        {rows.slice(0, 12).map((row) => (
                            <TableRow key={`${row.id ?? row.name}-${title}`} hover>
                                <TableCell sx={{ maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                    {row.name}
                                </TableCell>
                                <TableCell align="right">{row.runs}</TableCell>
                                <TableCell align="right">{row.tokens.toLocaleString()}</TableCell>
                                <TableCell align="right">${row.cost_usd.toFixed(4)}</TableCell>
                                <TableCell align="right">{row.avg_latency_ms ? `${Math.round(row.avg_latency_ms)} ms` : "—"}</TableCell>
                                <TableCell align="right">{row.retries}</TableCell>
                                <TableCell align="right">{row.tool_failures + row.validation_failures}</TableCell>
                            </TableRow>
                        ))}
                    </TableBody>
                </Table>
            )}
        </SectionCard>
    );
}

export default function ExecutionInsightsPage() {
    const navigate = useNavigate();
    const [days, setDays] = useState(7);
    const insights = useQuery({
        queryKey: ["orchestration", "execution-insights", days],
        queryFn: () => getExecutionInsights(days),
        refetchInterval: 30_000,
    });
    const providerHealth = useQuery({
        queryKey: ["orchestration", "provider-health-summary"],
        queryFn: getProviderHealthSummary,
        refetchInterval: 60_000,
    });
    const data = insights.data;
    const rows = useMemo(() => data?.by_event_type ?? [], [data]);
    const toolFailures = useMemo(() => data?.tool_failures_by_tool ?? [], [data]);
    const providerRows = providerHealth.data ?? [];
    const failedProviders = providerRows.filter((provider) => provider.enabled && provider.healthy === false).length;

    return (
        <PageShell maxWidth="xl" variant="browse">
            <PageHeader
                title="Execution insights"
                description="Reliability and quality signals across runs — investigate, then open a run for the full timeline."
                actions={
                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap alignItems="center">
                        <DateRangeControl value={days} onChange={setDays} />
                        <Button variant="outlined" onClick={() => navigate("/analytics/cost")}>Cost</Button>
                        <Button variant="outlined" onClick={() => navigate("/approvals")}>Approvals / ledger</Button>
                    </Stack>
                }
            />

            {(insights.isError || providerHealth.isError) && (
                <SectionError
                    error={insights.error ?? providerHealth.error}
                    fallback="Observability data could not be loaded."
                    onRetry={() => {
                        void insights.refetch();
                        void providerHealth.refetch();
                    }}
                />
            )}

            <AnalyticsKpiStrip>
                <StatCard label="Runs" value={data?.total_runs ?? "—"} description={`${data?.completed_runs ?? 0} completed · ${data?.failed_runs ?? 0} failed`} icon={<RunIcon />} loading={insights.isLoading} />
                <StatCard label="Tokens" value={data ? (data.total_tokens ?? 0).toLocaleString() : "—"} description={`$${(data?.total_cost_usd ?? 0).toFixed(4)} estimated cost`} icon={<TokenIcon />} color="secondary" loading={insights.isLoading} />
                <StatCard label="Latency" value={data ? `${Math.round(data.avg_latency_ms ?? 0)} ms` : "—"} description={`p95 ${Math.round(data?.p95_latency_ms ?? 0)} ms`} icon={<LatencyIcon />} color="info" loading={insights.isLoading} />
                <StatCard label="Acceptance after review" value={data?.acceptance_rate_after_review == null ? "—" : `${Math.round(data.acceptance_rate_after_review * 100)}%`} description={`${data?.accepted_after_review ?? 0} of ${data?.acceptance_checks ?? 0} review runs`} icon={<AcceptanceIcon />} color="success" loading={insights.isLoading} />
            </AnalyticsKpiStrip>

            {!insights.isLoading && (data?.total_runs ?? 0) === 0 ? (
                <EmptyState
                    icon={<RunFirstIcon />}
                    title="No runs in this window"
                    description="Start a project run to populate execution insights."
                    action={
                        <Button component={RouterLink} to="/projects" variant="contained" size="small">
                            Open projects
                        </Button>
                    }
                />
            ) : null}

            <SectionCard title="Quality and reliability signals" description="Operational signals are evidence for investigation, not a replacement for human review or offline evaluation.">
                {insights.isLoading ? <Skeleton variant="rounded" height={80} /> : (
                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                        <Chip label={`Retries: ${data?.retry_count ?? 0} (${Math.round((data?.retry_rate ?? 0) * 100)}%)`} icon={<RetryIcon />} variant="outlined" />
                        <Chip label={`Tool failures: ${data?.tool_call_failed_events ?? 0}`} icon={<FailureIcon />} color={(data?.tool_call_failed_events ?? 0) > 0 ? "warning" : "default"} variant="outlined" />
                        <Chip label={`Validation failures: ${data?.validation_failures ?? 0}`} color={(data?.validation_failures ?? 0) > 0 ? "warning" : "default"} variant="outlined" />
                        <Chip label={`Hallucination signals: ${data?.hallucination_failures ?? 0}`} color={(data?.hallucination_failures ?? 0) > 0 ? "error" : "default"} variant="outlined" />
                        <Chip label={`GitHub sync failures: ${data?.github_sync_failures ?? 0}`} color={(data?.github_sync_failures ?? 0) > 0 ? "error" : "default"} variant="outlined" />
                        <Chip label={`Discussion loop score: ${data?.discussion_loop_score == null ? "—" : data.discussion_loop_score.toFixed(2)}`} variant="outlined" />
                        <Chip label={`Eval records: ${data?.evaluation_records ?? 0}`} variant="outlined" />
                    </Stack>
                )}
            </SectionCard>

            <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", lg: "repeat(2, 1fr)" } }}>
                <RollupTable title="Cost and reliability by project" rows={data?.by_project ?? []} emptyLabel="No project runs in this window." />
                <RollupTable title="Cost and reliability by agent" rows={data?.by_agent ?? []} emptyLabel="No agent runs in this window." />
                <RollupTable title="Cost and reliability by task" rows={data?.by_task ?? []} emptyLabel="No task runs in this window." />
                <RollupTable title="Cost and reliability by provider" rows={data?.by_provider ?? []} emptyLabel="No provider-attributed runs in this window." />
            </Box>

            <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", lg: "repeat(2, 1fr)" } }}>
                <SectionCard title="Run event timeline" description="Open a run for the live trace, conversation viewer, and workflow graph.">
                    {rows.length === 0 ? <Typography variant="body2" color="text.secondary">No run events in this window.</Typography> : (
                        <Stack spacing={1}>
                            {rows.slice(0, 12).map((row) => (
                                <Paper key={row.event_type} variant="outlined" sx={{ p: 1.25 }}>
                                    <Stack direction="row" justifyContent="space-between" alignItems="center">
                                        <Typography variant="body2" sx={{ fontFamily: "IBM Plex Mono, monospace" }}>{humanizeKey(row.event_type)}</Typography>
                                        <Typography variant="h6">{row.count}</Typography>
                                    </Stack>
                                </Paper>
                            ))}
                        </Stack>
                    )}
                    {toolFailures.length > 0 && <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>Top failed tool: {toolFailures[0].tool} ({toolFailures[0].count})</Typography>}
                </SectionCard>

                <SectionCard title="Model/provider health" description="Latest persisted health checks. Run a check from model settings when a provider needs verification.">
                    {providerHealth.isLoading ? <Skeleton variant="rounded" height={120} /> : providerRows.length === 0 ? (
                        <Typography variant="body2" color="text.secondary">No providers configured.</Typography>
                    ) : (
                        <Stack spacing={1}>
                            <Typography variant="caption" color={failedProviders ? "error.main" : "text.secondary"}>{failedProviders ? `${failedProviders} enabled provider(s) need attention.` : "Enabled providers are healthy or have not been checked yet."}</Typography>
                            {providerRows.map((provider) => (
                                <Paper key={provider.provider_id} variant="outlined" sx={{ p: 1.25 }}>
                                    <Stack direction="row" spacing={1} alignItems="center">
                                        <ProviderIcon fontSize="small" color="action" />
                                        <Box sx={{ flex: 1, minWidth: 0 }}>
                                            <Typography variant="body2" noWrap>{provider.name}</Typography>
                                            <Typography variant="caption" color="text.secondary" noWrap>{provider.provider_type} · {provider.default_model}</Typography>
                                        </Box>
                                        <Chip size="small" label={humanizeKey(provider.status)} color={provider.healthy === true ? "success" : provider.healthy === false ? "error" : "default"} />
                                        <Typography variant="caption" color="text.secondary">{provider.latency_ms == null ? "—" : `${provider.latency_ms} ms`}</Typography>
                                    </Stack>
                                </Paper>
                            ))}
                        </Stack>
                    )}
                </SectionCard>
            </Box>
        </PageShell>
    );
}
