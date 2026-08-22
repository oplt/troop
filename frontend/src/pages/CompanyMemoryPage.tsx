import { useState } from "react";
import { Link as RouterLink, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
    Box,
    Button,
    Chip,
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableRow,
    TextField,
    Typography,
} from "@mui/material";
import { Memory as MemoryIcon } from "@mui/icons-material";
import { listCompanySemanticMemory, type SemanticMemoryEntry } from "../api/orchestration";
import { EmptyState } from "../components/ui/EmptyState";
import { FilterToolbar } from "../components/ui/FilterToolbar";
import { PageHeader } from "../components/ui/PageHeader";
import { PageShell } from "../components/ui/PageShell";
import { SectionCard } from "../components/ui/SectionCard";
import { ResponsiveRowCard, ResponsiveTable } from "../components/ui/ResponsiveTable";
import { SemanticMemoryProvenanceDetails } from "../features/memory/SemanticMemoryProvenanceDetails";
import { formatDateTime } from "../utils/formatters";

export default function CompanyMemoryPage() {
    const { companyId } = useParams<{ companyId: string }>();
    const [q, setQ] = useState("");
    const [prefix, setPrefix] = useState("");

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
        <PageShell maxWidth="lg" variant="browse">
            <PageHeader
                title="Company memory"
                description="Org-scoped searchable facts and decisions. Provenance stays on each row."
                actions={
                    <Button component={RouterLink} to="/companies" variant="outlined" size="small">
                        Back to companies
                    </Button>
                }
            />

            <SectionCard title="Browse" density="plain">
                <FilterToolbar>
                    <TextField
                        label="Search title/body"
                        value={q}
                        onChange={(e) => setQ(e.target.value)}
                        size="small"
                        sx={{ flex: 1, minWidth: 200 }}
                    />
                    <TextField
                        label="Namespace prefix"
                        value={prefix}
                        onChange={(e) => setPrefix(e.target.value)}
                        size="small"
                        sx={{ minWidth: 180 }}
                        helperText="Filter by namespace path"
                    />
                </FilterToolbar>
                {isLoading ? (
                    <Typography color="text.secondary" sx={{ mt: 2 }}>
                        Loading…
                    </Typography>
                ) : (
                    <Box sx={{ mt: 2 }}>
                        <ResponsiveTable
                            isEmpty={entries.length === 0}
                            empty={
                                <EmptyState
                                    icon={<MemoryIcon />}
                                    title="No company memory yet"
                                    description="Company-scoped entries appear here after writes or installs."
                                    action={
                                        <Button component={RouterLink} to="/companies" variant="outlined" size="small">
                                            Edit company brief
                                        </Button>
                                    }
                                />
                            }
                            table={
                                <Table size="small">
                                    <TableHead>
                                        <TableRow>
                                            <TableCell>Type</TableCell>
                                            <TableCell>Title</TableCell>
                                            <TableCell>Namespace</TableCell>
                                            <TableCell>Confidence</TableCell>
                                            <TableCell>Lifecycle</TableCell>
                                            <TableCell>Updated</TableCell>
                                        </TableRow>
                                    </TableHead>
                                    <TableBody>
                                        {entries.map((row: SemanticMemoryEntry) => {
                                            const conf = typeof row.confidence === "number" ? row.confidence : 0.5;
                                            return (
                                                <TableRow key={row.id} hover>
                                                    <TableCell>
                                                        <Chip size="small" label={row.entry_type} variant="outlined" />
                                                    </TableCell>
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
                                                    <TableCell>{conf.toFixed(2)}</TableCell>
                                                    <TableCell>
                                                        <SemanticMemoryProvenanceDetails entry={row} compact />
                                                    </TableCell>
                                                    <TableCell>{formatDateTime(row.updated_at)}</TableCell>
                                                </TableRow>
                                            );
                                        })}
                                    </TableBody>
                                </Table>
                            }
                            cards={entries.map((row) => (
                                <ResponsiveRowCard
                                    key={row.id}
                                    title={row.title}
                                    meta={`${row.entry_type} · conf ${typeof row.confidence === "number" ? row.confidence.toFixed(2) : "—"} · ${formatDateTime(row.updated_at)}`}
                                >
                                    <Typography variant="caption" color="text.secondary">
                                        {(row.body || "").slice(0, 160)}
                                    </Typography>
                                    <Typography variant="caption" sx={{ display: "block", wordBreak: "break-all" }}>
                                        {row.namespace}
                                    </Typography>
                                    <SemanticMemoryProvenanceDetails entry={row} compact />
                                </ResponsiveRowCard>
                            ))}
                        />
                    </Box>
                )}
            </SectionCard>
        </PageShell>
    );
}
