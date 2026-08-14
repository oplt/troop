import { useQuery } from "@tanstack/react-query";
import {
    Alert,
    Box,
    Button,
    Chip,
    CircularProgress,
    Link,
    Stack,
    Table,
    TableBody,
    TableCell,
    TableContainer,
    TableHead,
    TableRow,
    Typography,
} from "@mui/material";
import DownloadIcon from "@mui/icons-material/Download";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutline";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import ReportProblemIcon from "@mui/icons-material/ReportProblem";
import SecurityIcon from "@mui/icons-material/Security";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import { Link as RouterLink } from "react-router-dom";

import { exportSecurityPosture, getSecurityPosture, type SecurityPostureReport } from "../../api/admin";
import { AnalyticsKpiStrip } from "../../components/ui/AnalyticsKpiStrip";
import { EmptyState } from "../../components/ui/EmptyState";
import { SectionCard } from "../../components/ui/SectionCard";
import { StatCard } from "../../components/ui/StatCard";
import { formatDate } from "../../utils/formatters";

const SEVERITY_COLOR: Record<string, "error" | "warning" | "info" | "default" | "success"> = {
    critical: "error",
    high: "error",
    medium: "warning",
    low: "info",
    info: "default",
};

function severityRank(severity: string): number {
    const order = ["critical", "high", "medium", "low", "info"];
    const index = order.indexOf(severity);
    return index === -1 ? order.length : index;
}

function sortedFindings(report: SecurityPostureReport) {
    return [...report.findings].sort(
        (a, b) => severityRank(a.severity) - severityRank(b.severity) || a.title.localeCompare(b.title),
    );
}

export function SecurityPosturePanel() {
    const { data, isLoading, error, refetch, isFetching } = useQuery({
        queryKey: ["admin", "security-posture"],
        queryFn: () => getSecurityPosture(),
    });

    const handleExport = async () => {
        const blob = await exportSecurityPosture();
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = `security-posture-${new Date().toISOString().replace(/[:.]/g, "-")}.json`;
        anchor.click();
        URL.revokeObjectURL(url);
    };

    if (isLoading) {
        return (
            <Box sx={{ display: "flex", justifyContent: "center", py: 6 }}>
                <CircularProgress />
            </Box>
        );
    }

    if (error || !data) {
        return (
            <Alert severity="error" action={<Button onClick={() => void refetch()}>Retry</Button>}>
                Failed to load security posture audit.
            </Alert>
        );
    }

    const findings = sortedFindings(data);
    const hasCritical = data.summary.critical > 0 || data.summary.high > 0;

    return (
        <Stack spacing={2}>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={1} alignItems={{ sm: "center" }}>
                <Typography variant="body2" color="text.secondary" sx={{ flex: 1 }}>
                    Environment: <strong>{data.environment}</strong> · Generated{" "}
                    {formatDate(data.generated_at)}
                </Typography>
                <Stack direction="row" spacing={1}>
                    <Button size="small" onClick={() => void refetch()} disabled={isFetching}>
                        {isFetching ? "Refreshing…" : "Refresh"}
                    </Button>
                    <Button
                        size="small"
                        variant="outlined"
                        startIcon={<DownloadIcon />}
                        onClick={() => void handleExport()}
                    >
                        Export JSON
                    </Button>
                </Stack>
            </Stack>

            {hasCritical ? (
                <Alert severity="error">
                    {data.summary.critical + data.summary.high} critical/high finding
                    {data.summary.critical + data.summary.high === 1 ? "" : "s"} require attention before
                    production rollout.
                </Alert>
            ) : (
                <Alert severity="success">No critical or high severity findings detected.</Alert>
            )}

            <AnalyticsKpiStrip columns={{ xs: 2, sm: 3, md: 6, lg: 6 }}>
                <StatCard label="Total" value={data.summary.total} icon={<SecurityIcon />} />
                <StatCard
                    label="Critical"
                    value={data.summary.critical}
                    icon={<ErrorOutlineIcon />}
                    color="error"
                />
                <StatCard label="High" value={data.summary.high} icon={<ReportProblemIcon />} color="error" />
                <StatCard
                    label="Medium"
                    value={data.summary.medium}
                    icon={<WarningAmberIcon />}
                    color="warning"
                />
                <StatCard label="Low" value={data.summary.low} icon={<InfoOutlinedIcon />} color="info" />
                <StatCard label="Info" value={data.summary.info} icon={<InfoOutlinedIcon />} />
            </AnalyticsKpiStrip>

            <SectionCard
                title="Findings"
                description="Configuration, connector, and policy risks with remediation links."
            >
                {findings.length === 0 ? (
                    <EmptyState
                        icon={<SecurityIcon />}
                        title="All checks passed"
                        description="No security posture findings for the current deployment."
                    />
                ) : (
                    <TableContainer>
                        <Table size="small">
                            <TableHead>
                                <TableRow>
                                    <TableCell>Severity</TableCell>
                                    <TableCell>Finding</TableCell>
                                    <TableCell>Remediation</TableCell>
                                </TableRow>
                            </TableHead>
                            <TableBody>
                                {findings.map((finding) => (
                                    <TableRow key={`${finding.check_id}-${finding.resource_id ?? finding.title}`}>
                                        <TableCell>
                                            <Chip
                                                size="small"
                                                label={finding.severity}
                                                color={SEVERITY_COLOR[finding.severity] ?? "default"}
                                            />
                                        </TableCell>
                                        <TableCell>
                                            <Typography variant="subtitle2">{finding.title}</Typography>
                                            <Typography variant="body2" color="text.secondary">
                                                {finding.summary}
                                            </Typography>
                                            {finding.resource_type && finding.resource_id ? (
                                                <Typography variant="caption" color="text.secondary">
                                                    {finding.resource_type}: {finding.resource_id}
                                                </Typography>
                                            ) : null}
                                        </TableCell>
                                        <TableCell>
                                            <Typography variant="body2">{finding.remediation}</Typography>
                                            {finding.remediation_url ? (
                                                <Link
                                                    component={RouterLink}
                                                    to={finding.remediation_url}
                                                    variant="body2"
                                                >
                                                    Open remediation
                                                </Link>
                                            ) : null}
                                        </TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    </TableContainer>
                )}
            </SectionCard>
        </Stack>
    );
}
