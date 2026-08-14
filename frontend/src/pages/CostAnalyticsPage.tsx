import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link as RouterLink, useNavigate } from "react-router-dom";
import {
    Box,
    Button,
    Chip,
    Skeleton,
    Stack,
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableRow,
    Typography,
} from "@mui/material";
import { alpha } from "@mui/material/styles";
import {
    AttachMoney as CostIcon,
    Token as TokenIcon,
    EmojiEvents as LeaderboardIcon,
    PlayArrow as RunIcon,
} from "@mui/icons-material";
import { getCostAnalytics } from "../api/orchestration";
import { AnalyticsKpiStrip } from "../components/ui/AnalyticsKpiStrip";
import { DateRangeControl } from "../components/ui/DateRangeControl";
import { EmptyState } from "../components/ui/EmptyState";
import { PageHeader } from "../components/ui/PageHeader";
import { PageShell } from "../components/ui/PageShell";
import { SectionCard } from "../components/ui/SectionCard";
import { StatCard } from "../components/ui/StatCard";
import { ResponsiveRowCard, ResponsiveTable } from "../components/ui/ResponsiveTable";
import { formatDateTime, humanizeKey } from "../utils/formatters";

function prefersReducedMotion() {
    if (typeof window === "undefined" || !window.matchMedia) return false;
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function BarRow({ label, value, max, color = "primary" }: { label: string; value: number; max: number; color?: string }) {
    const pct = max > 0 ? Math.max(2, (value / max) * 100) : 0;
    const reduceMotion = prefersReducedMotion();
    return (
        <Stack direction="row" spacing={1.5} alignItems="center">
            <Typography variant="body2" sx={{ minWidth: 140, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {label}
            </Typography>
            <Box flex={1} sx={{ height: 10, borderRadius: 1, bgcolor: "action.hover" }}>
                <Box
                    sx={(theme) => ({
                        height: "100%",
                        width: `${pct}%`,
                        borderRadius: 1,
                        bgcolor: color === "secondary" ? theme.palette.secondary.main : theme.palette.primary.main,
                        transition: reduceMotion ? "none" : "width 0.4s ease",
                    })}
                />
            </Box>
            <Typography variant="caption" color="text.secondary" sx={{ minWidth: 72, textAlign: "right" }}>
                ${value.toFixed(4)}
            </Typography>
        </Stack>
    );
}

function AnalyticsEmpty({ title }: { title: string }) {
    return (
        <EmptyState
            icon={<RunIcon />}
            title={title}
            description="Cost and usage appear after agents complete runs."
            action={
                <Button component={RouterLink} to="/projects" variant="contained" size="small">
                    Open projects
                </Button>
            }
        />
    );
}

export default function CostAnalyticsPage() {
    const navigate = useNavigate();
    const [days, setDays] = useState(30);

    const { data, isLoading } = useQuery({
        queryKey: ["orchestration", "analytics", "cost", days],
        queryFn: () => getCostAnalytics(days),
    });

    const maxProjectCost = Math.max(...(data?.by_project.map((r) => r.cost_usd) ?? [0]));
    const maxAgentCost = Math.max(...(data?.by_agent.map((r) => r.cost_usd) ?? [0]));
    const maxTaskCost = Math.max(...(data?.by_task.map((r) => r.cost_usd) ?? [0]));
    const maxProviderCost = Math.max(...(data?.by_provider.map((r) => r.cost_usd) ?? [0]));
    const isEmpty =
        !isLoading &&
        data &&
        data.total_cost_usd === 0 &&
        data.by_project.length === 0 &&
        data.most_expensive_runs.length === 0;

    return (
        <PageShell maxWidth="xl" variant="browse">
            <PageHeader
                title="Cost & usage"
                description="Spend and tokens across projects, agents, models, and tasks."
                actions={<DateRangeControl value={days} onChange={setDays} />}
            />

            <AnalyticsKpiStrip columns={{ xs: 1, sm: 2, md: 3, lg: 3 }}>
                {isLoading ? (
                    Array.from({ length: 3 }).map((_, i) => (
                        <Skeleton key={i} variant="rounded" height={100} sx={{ borderRadius: 1 }} />
                    ))
                ) : (
                    <>
                        <StatCard
                            label="Total cost"
                            value={data ? `$${data.total_cost_usd.toFixed(4)}` : "—"}
                            description={`Last ${days} days`}
                            icon={<CostIcon />}
                            color="primary"
                        />
                        <StatCard
                            label="Total tokens"
                            value={data ? data.total_tokens.toLocaleString() : "—"}
                            description="Across all runs in period"
                            icon={<TokenIcon />}
                            color="secondary"
                        />
                        <StatCard
                            label="Expensive runs"
                            value={data?.most_expensive_runs.length ?? 0}
                            description="Top costly runs in window"
                            icon={<LeaderboardIcon />}
                        />
                    </>
                )}
            </AnalyticsKpiStrip>

            {isEmpty ? (
                <AnalyticsEmpty title="No cost data yet" />
            ) : (
                <>
                    <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", lg: "repeat(4, 1fr)" } }}>
                        <SectionCard title="By project" description="Cost breakdown per project.">
                            {isLoading ? (
                                <Stack spacing={1}>{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} height={20} />)}</Stack>
                            ) : data?.by_project.length === 0 ? (
                                <Typography variant="body2" color="text.secondary">No project costs in this window.</Typography>
                            ) : (
                                <Stack spacing={1.25}>
                                    {data?.by_project.map((row) => (
                                        <BarRow key={row.name} label={row.name} value={row.cost_usd} max={maxProjectCost} />
                                    ))}
                                </Stack>
                            )}
                        </SectionCard>

                        <SectionCard title="By agent" description="Which agents consumed the most.">
                            {isLoading ? (
                                <Stack spacing={1}>{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} height={20} />)}</Stack>
                            ) : data?.by_agent.length === 0 ? (
                                <Typography variant="body2" color="text.secondary">No agent runs yet.</Typography>
                            ) : (
                                <Stack spacing={1.25}>
                                    {data?.by_agent.map((row) => (
                                        <BarRow key={row.name} label={row.name} value={row.cost_usd} max={maxAgentCost} color="secondary" />
                                    ))}
                                </Stack>
                            )}
                        </SectionCard>

                        <SectionCard title="By model" description="Cost per model / provider.">
                            {isLoading ? (
                                <Stack spacing={1}>{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} height={20} />)}</Stack>
                            ) : data?.by_provider.length === 0 ? (
                                <Typography variant="body2" color="text.secondary">No model data yet.</Typography>
                            ) : (
                                <Stack spacing={1.25}>
                                    {data?.by_provider.map((row) => (
                                        <BarRow key={row.name} label={row.name} value={row.cost_usd} max={maxProviderCost} />
                                    ))}
                                </Stack>
                            )}
                        </SectionCard>

                        <SectionCard title="By task" description="Find expensive or noisy work.">
                            {isLoading ? (
                                <Stack spacing={1}>{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} height={20} />)}</Stack>
                            ) : data?.by_task.length === 0 ? (
                                <Typography variant="body2" color="text.secondary">No task costs recorded yet.</Typography>
                            ) : (
                                <Stack spacing={1.25}>
                                    {data?.by_task.slice(0, 12).map((row) => (
                                        <BarRow key={row.name} label={row.name} value={row.cost_usd} max={maxTaskCost} color="secondary" />
                                    ))}
                                </Stack>
                            )}
                        </SectionCard>
                    </Box>

                    <SectionCard title="Most expensive runs" description={`Top runs in the last ${days} days.`}>
                        {isLoading ? (
                            <Skeleton variant="rounded" height={200} />
                        ) : !data || data.most_expensive_runs.length === 0 ? (
                            <Typography variant="body2" color="text.secondary">No runs in this period.</Typography>
                        ) : (
                            <ResponsiveTable
                                table={
                                    <Table size="small">
                                        <TableHead>
                                            <TableRow>
                                                <TableCell>#</TableCell>
                                                <TableCell>Run ID</TableCell>
                                                <TableCell>Model</TableCell>
                                                <TableCell>Status</TableCell>
                                                <TableCell align="right">Tokens</TableCell>
                                                <TableCell align="right">Cost</TableCell>
                                                <TableCell>Created</TableCell>
                                                <TableCell />
                                            </TableRow>
                                        </TableHead>
                                        <TableBody>
                                            {data.most_expensive_runs.map((run, idx) => (
                                                <TableRow
                                                    key={run.id}
                                                    hover
                                                    sx={(theme) => ({
                                                        bgcolor: idx === 0 ? alpha(theme.palette.warning.main, 0.06) : undefined,
                                                    })}
                                                >
                                                    <TableCell>{idx + 1}</TableCell>
                                                    <TableCell sx={{ fontFamily: "monospace", fontSize: "0.78rem" }}>
                                                        {run.id.slice(0, 8)}…
                                                    </TableCell>
                                                    <TableCell>
                                                        <Typography variant="caption">{run.model_name ?? "—"}</Typography>
                                                    </TableCell>
                                                    <TableCell>
                                                        <Chip
                                                            label={humanizeKey(run.status)}
                                                            size="small"
                                                            color={run.status === "completed" ? "success" : run.status === "failed" ? "error" : "default"}
                                                        />
                                                    </TableCell>
                                                    <TableCell align="right">
                                                        <Typography variant="caption">{run.tokens.toLocaleString()}</Typography>
                                                    </TableCell>
                                                    <TableCell align="right">
                                                        <Typography variant="caption" sx={{ fontWeight: 500 }}>
                                                            ${run.cost_usd.toFixed(5)}
                                                        </Typography>
                                                    </TableCell>
                                                    <TableCell>
                                                        <Typography variant="caption" color="text.secondary">
                                                            {formatDateTime(run.created_at)}
                                                        </Typography>
                                                    </TableCell>
                                                    <TableCell>
                                                        <Button size="small" variant="text" onClick={() => navigate(`/runs/${run.id}`)}>
                                                            Inspect
                                                        </Button>
                                                    </TableCell>
                                                </TableRow>
                                            ))}
                                        </TableBody>
                                    </Table>
                                }
                                cards={
                                    <>
                                        {data.most_expensive_runs.map((run, idx) => (
                                            <ResponsiveRowCard
                                                key={run.id}
                                                title={`#${idx + 1} · ${run.id.slice(0, 8)}…`}
                                                meta={`${run.model_name ?? "—"} · ${formatDateTime(run.created_at)}`}
                                                actions={
                                                    <Button size="small" variant="outlined" onClick={() => navigate(`/runs/${run.id}`)}>
                                                        Inspect
                                                    </Button>
                                                }
                                            >
                                                <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                                                    <Chip
                                                        label={humanizeKey(run.status)}
                                                        size="small"
                                                        color={run.status === "completed" ? "success" : run.status === "failed" ? "error" : "default"}
                                                    />
                                                    <Typography variant="caption" color="text.secondary">
                                                        {run.tokens.toLocaleString()} tokens · ${run.cost_usd.toFixed(5)}
                                                    </Typography>
                                                </Stack>
                                            </ResponsiveRowCard>
                                        ))}
                                    </>
                                }
                            />
                        )}
                    </SectionCard>
                </>
            )}
        </PageShell>
    );
}
