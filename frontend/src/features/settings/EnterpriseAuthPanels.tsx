import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
    Alert,
    Box,
    Button,
    Chip,
    CircularProgress,
    Stack,
    Switch,
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableRow,
    TextField,
    Typography,
} from "@mui/material";
import DownloadIcon from "@mui/icons-material/Download";
import { useState } from "react";

import {
    createIdentityProvider,
    exportAuditLogs,
    listAuditLogs,
    listIdentityProviders,
    testIdentityProvider,
    updateIdentityProvider,
    type IdentityProvider,
} from "../../api/admin";
import { SectionCard } from "../../components/ui/SectionCard";
import { formatDateTime } from "../../utils/formatters";

export function AuditExportPanel() {
    const [actionFilter, setActionFilter] = useState("");
    const { data, isLoading, error, refetch } = useQuery({
        queryKey: ["admin", "audit-logs"],
        queryFn: () => listAuditLogs({ page: 1, page_size: 25 }),
    });

    const handleExport = async (format: "ndjson" | "csv") => {
        const blob = await exportAuditLogs(format, actionFilter ? { action: actionFilter } : undefined);
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = `audit-export-${new Date().toISOString().replace(/[:.]/g, "-")}.${format === "csv" ? "csv" : "ndjson"}`;
        anchor.click();
        URL.revokeObjectURL(url);
    };

    const filtered = actionFilter
        ? data?.items.filter((item) => item.action.includes(actionFilter)) ?? []
        : data?.items ?? [];

    return (
        <Stack spacing={2}>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={1} alignItems={{ sm: "center" }}>
                <TextField
                    size="small"
                    label="Filter action contains"
                    value={actionFilter}
                    onChange={(event) => setActionFilter(event.target.value)}
                    sx={{ minWidth: 240 }}
                />
                <Button startIcon={<DownloadIcon />} variant="outlined" onClick={() => void handleExport("ndjson")}>
                    Export NDJSON
                </Button>
                <Button startIcon={<DownloadIcon />} variant="outlined" onClick={() => void handleExport("csv")}>
                    Export CSV
                </Button>
            </Stack>
            {isLoading ? (
                <CircularProgress size={24} />
            ) : error ? (
                <Alert severity="error" action={<Button onClick={() => void refetch()}>Retry</Button>}>
                    Failed to load audit logs.
                </Alert>
            ) : (
                <SectionCard title={`Recent audit events (${data?.total ?? 0})`}>
                    <Table size="small">
                        <TableHead>
                            <TableRow>
                                <TableCell>When</TableCell>
                                <TableCell>Action</TableCell>
                                <TableCell>User</TableCell>
                                <TableCell>Resource</TableCell>
                            </TableRow>
                        </TableHead>
                        <TableBody>
                            {filtered.map((row) => (
                                <TableRow key={row.id}>
                                    <TableCell>{formatDateTime(row.created_at)}</TableCell>
                                    <TableCell>{row.action}</TableCell>
                                    <TableCell>{row.user_id?.slice(0, 8) ?? "—"}</TableCell>
                                    <TableCell>
                                        {row.resource_type ? `${row.resource_type}:${row.resource_id ?? ""}` : "—"}
                                    </TableCell>
                                </TableRow>
                            ))}
                        </TableBody>
                    </Table>
                </SectionCard>
            )}
        </Stack>
    );
}

const emptyForm = {
    slug: "",
    name: "",
    issuer: "",
    client_id: "",
    client_secret: "",
    domain_allowlist: "",
};

export function IdentityProvidersPanel() {
    const queryClient = useQueryClient();
    const { data, isLoading, error, refetch } = useQuery({
        queryKey: ["admin", "identity-providers"],
        queryFn: () => listIdentityProviders(),
    });
    const [form, setForm] = useState(emptyForm);
    const [message, setMessage] = useState("");

    const createMutation = useMutation({
        mutationFn: () => createIdentityProvider({
            slug: form.slug,
            name: form.name,
            issuer: form.issuer,
            client_id: form.client_id,
            client_secret: form.client_secret,
            domain_allowlist: form.domain_allowlist.split(",").map((item) => item.trim()).filter(Boolean),
            enabled: false,
        }),
        onSuccess: async () => {
            setForm(emptyForm);
            setMessage("Identity provider created. Enable it after verifying OIDC discovery.");
            await queryClient.invalidateQueries({ queryKey: ["admin", "identity-providers"] });
        },
    });

    const toggleEnabled = useMutation({
        mutationFn: (provider: IdentityProvider) => updateIdentityProvider(provider.id, { enabled: !provider.enabled }),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["admin", "identity-providers"] });
        },
    });

    const testMutation = useMutation({
        mutationFn: (providerId: string) => testIdentityProvider(providerId),
        onSuccess: (result) => setMessage(`OIDC discovery OK: ${String(result.authorization_endpoint ?? "ready")}`),
    });

    return (
        <Stack spacing={2}>
            <Typography variant="body2" color="text.secondary">
                Configure OIDC identity providers for enterprise SSO. SAML and SCIM are deferred until workspace RBAC stabilizes.
            </Typography>
            {message && <Alert severity="info" onClose={() => setMessage("")}>{message}</Alert>}
            <SectionCard title="Create OIDC provider">
                <Stack spacing={1.5}>
                    <TextField label="Slug" size="small" value={form.slug} onChange={(e) => setForm({ ...form, slug: e.target.value })} />
                    <TextField label="Display name" size="small" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
                    <TextField label="Issuer URL" size="small" value={form.issuer} onChange={(e) => setForm({ ...form, issuer: e.target.value })} />
                    <TextField label="Client ID" size="small" value={form.client_id} onChange={(e) => setForm({ ...form, client_id: e.target.value })} />
                    <TextField label="Client secret" size="small" type="password" value={form.client_secret} onChange={(e) => setForm({ ...form, client_secret: e.target.value })} />
                    <TextField label="Allowed email domains (comma-separated)" size="small" value={form.domain_allowlist} onChange={(e) => setForm({ ...form, domain_allowlist: e.target.value })} />
                    <Button variant="contained" disabled={createMutation.isPending} onClick={() => createMutation.mutate()}>
                        Create provider
                    </Button>
                </Stack>
            </SectionCard>
            {isLoading ? <CircularProgress size={24} /> : error ? (
                <Alert severity="error" action={<Button onClick={() => void refetch()}>Retry</Button>}>Failed to load providers.</Alert>
            ) : (
                <SectionCard title="Configured providers">
                    <Stack spacing={1}>
                        {(data ?? []).map((provider) => (
                            <Stack key={provider.id} direction={{ xs: "column", sm: "row" }} spacing={1} alignItems={{ sm: "center" }} sx={{ p: 1.25, border: 1, borderColor: "divider", borderRadius: 1 }}>
                                <Box sx={{ flex: 1 }}>
                                    <Typography variant="subtitle2">{provider.name}</Typography>
                                    <Typography variant="caption" color="text.secondary">{provider.slug} · {provider.issuer}</Typography>
                                </Box>
                                <Chip size="small" label={provider.enabled ? "Enabled" : "Disabled"} color={provider.enabled ? "success" : "default"} />
                                <Switch checked={provider.enabled} onChange={() => toggleEnabled.mutate(provider)} />
                                <Button size="small" onClick={() => testMutation.mutate(provider.id)}>Test</Button>
                            </Stack>
                        ))}
                    </Stack>
                </SectionCard>
            )}
        </Stack>
    );
}
