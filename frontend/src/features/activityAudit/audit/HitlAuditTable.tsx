import { Box, Paper, Skeleton, Stack, Typography } from "@mui/material";

import type { HITLAuditLog } from "../../../api/orchestration";
import { SectionCard } from "../../../components/ui/SectionCard";
import { formatDateTime, humanizeKey } from "../../../utils/formatters";

type HitlAuditTableProps = {
    logs: HITLAuditLog[];
    isLoading: boolean;
};

export function HitlAuditTable({ logs, isLoading }: HitlAuditTableProps) {
    return (
        <SectionCard
            title="Human-in-the-loop audit log"
            description="Approval requests, decisions, and project control changes. Sensitive payload values are intentionally excluded."
        >
            {isLoading && (
                <Stack spacing={1.25} role="status" aria-busy="true" aria-label="Loading audit log">
                    <Skeleton variant="rounded" height={64} sx={{ borderRadius: 1 }} />
                    <Skeleton variant="rounded" height={64} sx={{ borderRadius: 1 }} />
                </Stack>
            )}
            <Stack spacing={1.25}>
                {logs.map((log) => (
                    <Paper key={log.id} variant="outlined" sx={{ p: 1.5, borderRadius: 1 }}>
                        <Stack direction={{ xs: "column", sm: "row" }} spacing={1} justifyContent="space-between">
                            <Box>
                                <Typography variant="body2">{humanizeKey(log.action)}</Typography>
                                <Typography variant="caption" color="text.secondary">
                                    {log.resource_type ?? "resource"}
                                    {log.resource_id ? ` • ${log.resource_id.slice(0, 8)}` : ""}
                                </Typography>
                            </Box>
                            <Typography variant="caption" color="text.secondary">
                                {formatDateTime(log.created_at)}
                            </Typography>
                        </Stack>
                        {Object.keys(log.metadata).length > 0 && (
                            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.75 }}>
                                {Object.entries(log.metadata)
                                    .map(([key, value]) => `${humanizeKey(key)}: ${String(value)}`)
                                    .join(" • ")}
                            </Typography>
                        )}
                    </Paper>
                ))}
                {logs.length === 0 && !isLoading && (
                    <Typography variant="body2" color="text.secondary">
                        No HITL audit entries match the current filters.
                    </Typography>
                )}
            </Stack>
        </SectionCard>
    );
}
