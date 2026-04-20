import { useState } from "react";
import { Link as RouterLink, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Box, Link, Stack, Table, TableBody, TableCell, TableHead, TableRow, TextField, Typography } from "@mui/material";
import { listCompanies, type Company } from "../api/companies";
import { listCompanySemanticMemory, type SemanticMemoryEntry } from "../api/orchestration";
import { PageHeader } from "../components/ui/PageHeader";
import { PageShell } from "../components/ui/PageShell";
import { SectionCard } from "../components/ui/SectionCard";
import { formatDateTime } from "../utils/formatters";

export default function CompanyMemoryPage() {
    const { companyId } = useParams<{ companyId: string }>();
    const [q, setQ] = useState("");
    const [prefix, setPrefix] = useState("");

    const { data: companies = [] } = useQuery({
        queryKey: ["companies"],
        queryFn: listCompanies,
    });
    const company: Company | undefined = companies.find((c) => c.id === companyId);

    const { data: entries = [], isLoading } = useQuery({
        queryKey: ["orchestration", "company-semantic", companyId, q, prefix],
        queryFn: () =>
            listCompanySemanticMemory(companyId!, {
                q: q.trim() || undefined,
                namespace_prefix: prefix.trim() || undefined,
                limit: 120,
            }),
        enabled: Boolean(companyId),
    });

    if (!companyId) return null;

    return (
        <PageShell maxWidth="lg">
            <PageHeader
                eyebrow="Company memory"
                title={company ? `${company.name} · semantic` : "Semantic (company scope)"}
                description={
                    <>
                        Entries with <code>project_id = null</code> for this company.{" "}
                        <Link component={RouterLink} to="/companies">
                            Companies
                        </Link>
                    </>
                }
            />

            <SectionCard title="Browse" sx={{ mb: 3 }}>
                <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ mb: 2 }}>
                    <TextField
                        label="Search title/body"
                        value={q}
                        onChange={(e) => setQ(e.target.value)}
                        size="small"
                        fullWidth
                    />
                    <TextField
                        label="Namespace prefix"
                        value={prefix}
                        onChange={(e) => setPrefix(e.target.value)}
                        size="small"
                        fullWidth
                    />
                </Stack>
                {isLoading ? (
                    <Typography color="text.secondary">Loading…</Typography>
                ) : entries.length === 0 ? (
                    <Typography color="text.secondary">No company-scoped entries.</Typography>
                ) : (
                    <Table size="small">
                        <TableHead>
                            <TableRow>
                                <TableCell>Type</TableCell>
                                <TableCell>Title</TableCell>
                                <TableCell>Namespace</TableCell>
                                <TableCell>Confidence</TableCell>
                                <TableCell>Updated</TableCell>
                            </TableRow>
                        </TableHead>
                        <TableBody>
                            {entries.map((row: SemanticMemoryEntry) => {
                                const conf = typeof row.confidence === "number" ? row.confidence : 0.5;
                                return (
                                    <TableRow key={row.id}>
                                        <TableCell>{row.entry_type}</TableCell>
                                        <TableCell>
                                            <Typography variant="body2" fontWeight={600}>
                                                {row.title}
                                            </Typography>
                                            <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
                                                {(row.body || "").slice(0, 120)}
                                                {(row.body || "").length > 120 ? "…" : ""}
                                            </Typography>
                                        </TableCell>
                                        <TableCell>
                                            <Typography variant="caption" sx={{ wordBreak: "break-all" }}>
                                                {row.namespace}
                                            </Typography>
                                        </TableCell>
                                        <TableCell>{(conf * 100).toFixed(0)}%</TableCell>
                                        <TableCell>{formatDateTime(row.updated_at)}</TableCell>
                                    </TableRow>
                                );
                            })}
                        </TableBody>
                    </Table>
                )}
            </SectionCard>

            <Box sx={{ mt: 2 }}>
                <Typography variant="caption" color="text.secondary">
                    Project-scoped memory stays on each project&apos;s Memory page.
                </Typography>
            </Box>
        </PageShell>
    );
}
