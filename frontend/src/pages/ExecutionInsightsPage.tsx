import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Chip, Divider, MenuItem, Paper, Stack, TextField, Typography } from "@mui/material";
import { getExecutionInsights } from "../api/orchestration";
import { PageHeader } from "../components/ui/PageHeader";
import { PageShell } from "../components/ui/PageShell";
import { SectionCard } from "../components/ui/SectionCard";
import { formatDateTime } from "../utils/formatters";

export default function ExecutionInsightsPage() {
    const [days, setDays] = useState(7);
    const { data, isLoading } = useQuery({
        queryKey: ["orchestration", "execution-insights", days],
        queryFn: () => getExecutionInsights(days),
    });

    const rows = useMemo(() => data?.by_event_type ?? [], [data]);
    const toolFailures = useMemo(() => data?.tool_failures_by_tool ?? [], [data]);

    return (
        <PageShell maxWidth="lg">
            <PageHeader
                eyebrow="Analytics"
                title="Run quality & events"
                description="Aggregated run event types across your orchestration projects (tool failures, fallbacks, LLM responses, etc.)."
            />

            <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ mb: 2 }} alignItems={{ sm: "center" }}>
                <TextField
                    select
                    label="Window"
                    size="small"
                    value={days}
                    onChange={(e) => setDays(Number(e.target.value))}
                    sx={{ minWidth: 200 }}
                >
                    <MenuItem value={7}>Last 7 days</MenuItem>
                    <MenuItem value={14}>Last 14 days</MenuItem>
                    <MenuItem value={30}>Last 30 days</MenuItem>
                </TextField>
                {data?.since && (
                    <Typography variant="body2" color="text.secondary">
                        Since {formatDateTime(data.since)}
                    </Typography>
                )}
            </Stack>

            <SectionCard title="Events by type" description="Higher counts can highlight noisy tools, failing models, or policy routing churn.">
                {isLoading ? (
                    <Typography variant="body2" color="text.secondary">
                        Loading…
                    </Typography>
                ) : rows.length === 0 ? (
                    <Typography variant="body2" color="text.secondary">
                        No run events in this window.
                    </Typography>
                ) : (
                    <Stack spacing={1}>
                        {rows.map((row) => (
                            <Paper key={row.event_type} variant="outlined" sx={{ p: 1.5, borderRadius: 2 }}>
                                <Stack direction="row" justifyContent="space-between" alignItems="center">
                                    <Typography variant="subtitle2" sx={{ fontFamily: "IBM Plex Mono, monospace" }}>
                                        {row.event_type}
                                    </Typography>
                                    <Typography variant="h6">{row.count}</Typography>
                                </Stack>
                            </Paper>
                        ))}
                    </Stack>
                )}
            </SectionCard>

            <SectionCard
                title="Quality heuristics"
                description="Aggregated signals for review churn, brainstorm convergence, and tool health (not a substitute for offline evals)."
            >
                {isLoading || !data ? (
                    <Typography variant="body2" color="text.secondary">Loading…</Typography>
                ) : (
                    <Stack spacing={1.5}>
                        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                            <Chip label={`Reopens: ${data.reopen_events}`} size="small" variant="outlined" />
                            <Chip label={`Blocked: ${data.blocked_events}`} size="small" variant="outlined" />
                            <Chip label={`Tool failures: ${data.tool_call_failed_events}`} size="small" variant="outlined" />
                            <Chip label={`Brainstorm summaries: ${data.brainstorm_round_summary_events}`} size="small" variant="outlined" />
                        </Stack>
                        <Divider />
                        <Typography variant="subtitle2">Tool failures by tool name</Typography>
                        {toolFailures.length === 0 ? (
                            <Typography variant="body2" color="text.secondary">No tool_call_failed events in this window.</Typography>
                        ) : (
                            <Stack spacing={1}>
                                {toolFailures.map((row) => (
                                    <Paper key={row.tool} variant="outlined" sx={{ p: 1.5, borderRadius: 2 }}>
                                        <Stack direction="row" justifyContent="space-between" alignItems="center">
                                            <Typography variant="subtitle2" sx={{ fontFamily: "IBM Plex Mono, monospace" }}>
                                                {row.tool}
                                            </Typography>
                                            <Typography variant="h6">{row.count}</Typography>
                                        </Stack>
                                    </Paper>
                                ))}
                            </Stack>
                        )}
                    </Stack>
                )}
            </SectionCard>
        </PageShell>
    );
}
