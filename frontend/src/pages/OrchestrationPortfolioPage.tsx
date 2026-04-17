import { useQuery } from "@tanstack/react-query";
import { Box, Chip, Paper, Stack, Table, TableBody, TableCell, TableHead, TableRow, Typography } from "@mui/material";
import { useNavigate } from "react-router-dom";
import { getOrchestrationPortfolio } from "../api/orchestration";
import { PageHeader } from "../components/ui/PageHeader";
import { PageShell } from "../components/ui/PageShell";
import { SectionCard } from "../components/ui/SectionCard";

export default function OrchestrationPortfolioPage() {
    const navigate = useNavigate();
    const { data: rows = [], isLoading } = useQuery({
        queryKey: ["orchestration", "portfolio"],
        queryFn: getOrchestrationPortfolio,
    });

    return (
        <PageShell maxWidth="xl">
            <PageHeader
                eyebrow="Orchestration"
                title="Portfolio"
                description="One view across all agent projects: active runs, open tasks, and linked repositories."
            />

            <SectionCard title="Projects" description="Select a row to open the project workspace.">
                {isLoading ? (
                    <Typography variant="body2" color="text.secondary">
                        Loading portfolio…
                    </Typography>
                ) : rows.length === 0 ? (
                    <Typography variant="body2" color="text.secondary">
                        No orchestration projects yet. Create one from Projects.
                    </Typography>
                ) : (
                    <Table size="small">
                        <TableHead>
                            <TableRow>
                                <TableCell>Project</TableCell>
                                <TableCell align="right">Active runs</TableCell>
                                <TableCell align="right">Open tasks</TableCell>
                                <TableCell align="right">Repos</TableCell>
                            </TableRow>
                        </TableHead>
                        <TableBody>
                            {rows.map((row) => (
                                <TableRow
                                    key={row.project_id}
                                    hover
                                    sx={{ cursor: "pointer" }}
                                    onClick={() => navigate(`/agent-projects/${row.project_id}`)}
                                >
                                    <TableCell>
                                        <Stack spacing={0.5}>
                                            <Typography variant="subtitle2">{row.name}</Typography>
                                            <Chip size="small" variant="outlined" label={row.slug} />
                                        </Stack>
                                    </TableCell>
                                    <TableCell align="right">{row.active_runs}</TableCell>
                                    <TableCell align="right">{row.open_tasks}</TableCell>
                                    <TableCell align="right">{row.repository_links}</TableCell>
                                </TableRow>
                            ))}
                        </TableBody>
                    </Table>
                )}
            </SectionCard>

            <Box sx={{ mt: 2 }}>
                <Paper sx={{ p: 2, borderRadius: 3 }}>
                    <Typography variant="caption" color="text.secondary">
                        Open tasks exclude completed, archived, and GitHub-synced terminal states so the portfolio reflects
                        remaining work.
                    </Typography>
                </Paper>
            </Box>
        </PageShell>
    );
}
