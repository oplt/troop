import { Chip, Stack, Typography } from "@mui/material";
import { SectionCard } from "../../components/ui/SectionCard";
import { StatusChip } from "../../components/ui/StatusChip";
import { formatDurationMs, type RunTraceSummaryStats } from "./traceUtils";

type RunTraceSummaryCardProps = {
    stats: RunTraceSummaryStats;
};

export function RunTraceSummaryCard({ stats }: RunTraceSummaryCardProps) {
    return (
        <SectionCard
            title="Run summary"
            description="Active execution time, human wait, cost, and span counts from the safe trace read model."
        >
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mb: 2 }}>
                <StatusChip status={stats.status} kind="run" variant="filled" />
                <Chip label={`Active ${formatDurationMs(stats.activeTimeMs)}`} size="small" variant="outlined" />
                <Chip label={`Human wait ${formatDurationMs(stats.humanWaitMs)}`} size="small" variant="outlined" />
                <Chip
                    label={stats.costUsd != null ? `$${stats.costUsd.toFixed(5)}` : "Cost —"}
                    size="small"
                    variant="outlined"
                />
            </Stack>
            <Stack direction="row" spacing={3} flexWrap="wrap" useFlexGap>
                <Metric label="Model attempts" value={stats.modelCount} />
                <Metric label="Tool spans" value={stats.toolCount} />
                <Metric label="Approvals" value={stats.approvalCount} />
                <Metric label="Retries / checkpoints" value={stats.retryCount} />
                <Metric label="Errors" value={stats.errorCount} />
                <Metric label="External effects" value={stats.externalEffectCount} />
            </Stack>
        </SectionCard>
    );
}

function Metric({ label, value }: { label: string; value: number }) {
    return (
        <Stack spacing={0.25}>
            <Typography variant="caption" color="text.secondary">{label}</Typography>
            <Typography variant="h6" sx={{ lineHeight: 1.2 }}>{value}</Typography>
        </Stack>
    );
}
