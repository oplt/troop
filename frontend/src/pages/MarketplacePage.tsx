import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
    Alert,
    Box,
    Button,
    Chip,
    CircularProgress,
    MenuItem,
    Paper,
    Stack,
    Tab,
    Tabs,
    TextField,
    Typography,
} from "@mui/material";
import {
    getMarketplaceCatalog,
    installConnector,
    installMarketplaceAgentTemplate,
    installMarketplaceDepartment,
    installMarketplaceSkill,
    installMarketplaceWorkflow,
    listConnectorDefinitions,
    listConnectorInstallations,
    seedMarketplaceAgentTemplates,
    testConnectorInstallation,
} from "../api/workforce";
import { getDefaultCompany } from "../api/companies";
import { useSnackbar } from "../app/snackbarContext";
import { PageHeader } from "../components/ui/PageHeader";
import { PageShell } from "../components/ui/PageShell";

type TabKey = "skills" | "workflows" | "departments" | "agents" | "connectors";

function CatalogCard({
    title,
    description,
    meta,
    onInstall,
    installing,
}: {
    title: string;
    description: string;
    meta?: string;
    onInstall: () => void;
    installing: boolean;
}) {
    return (
        <Paper variant="outlined" sx={{ p: 2 }}>
            <Stack spacing={1}>
                <Typography variant="subtitle1">{title}</Typography>
                {meta ? <Chip size="small" label={meta} sx={{ alignSelf: "flex-start" }} /> : null}
                <Typography variant="body2" color="text.secondary">
                    {description}
                </Typography>
                <Button size="small" variant="contained" onClick={onInstall} disabled={installing}>
                    {installing ? "Installing…" : "Install"}
                </Button>
            </Stack>
        </Paper>
    );
}

export default function MarketplacePage() {
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();
    const [tab, setTab] = useState<TabKey>("skills");
    const [connectorSlug, setConnectorSlug] = useState("mcp-http");
    const [connectorName, setConnectorName] = useState("My MCP server");
    const [baseUrl, setBaseUrl] = useState("http://127.0.0.1:8080/mcp");
    const [authToken, setAuthToken] = useState("");

    const { data: company } = useQuery({
        queryKey: ["companies", "default"],
        queryFn: getDefaultCompany,
    });

    const { data: catalog, isLoading, error } = useQuery({
        queryKey: ["workforce", "marketplace"],
        queryFn: getMarketplaceCatalog,
    });

    const { data: definitions = [] } = useQuery({
        queryKey: ["workforce", "connectors", "definitions"],
        queryFn: listConnectorDefinitions,
        enabled: tab === "connectors",
    });

    const { data: installations = [] } = useQuery({
        queryKey: ["workforce", "connectors", "installations"],
        queryFn: listConnectorInstallations,
        enabled: tab === "connectors",
    });

    const installMutation = useMutation({
        mutationFn: async ({ kind, slug }: { kind: TabKey; slug: string }) => {
            if (kind === "skills") {
                return installMarketplaceSkill({ slug, company_id: company?.id, publish: true });
            }
            if (kind === "workflows") {
                return installMarketplaceWorkflow({ slug, company_id: company?.id, publish: true });
            }
            if (kind === "departments") {
                if (!company?.id) throw new Error("Default company required");
                return installMarketplaceDepartment({ slug, company_id: company.id });
            }
            return installMarketplaceAgentTemplate({ slug });
        },
        onSuccess: (result) => {
            showToast({
                message: `${result.slug}: ${result.status}`,
                severity: result.status === "already_installed" ? "info" : "success",
            });
            queryClient.invalidateQueries({ queryKey: ["workforce"] });
        },
        onError: (err: Error) => showToast({ message: err.message, severity: "error" }),
    });

    const seedAgentsMutation = useMutation({
        mutationFn: seedMarketplaceAgentTemplates,
        onSuccess: (result) => {
            showToast({
                message: `Seeded agents: ${result.installed} installed, ${result.skipped} skipped`,
                severity: "success",
            });
        },
        onError: (err: Error) => showToast({ message: err.message, severity: "error" }),
    });

    const connectorInstallMutation = useMutation({
        mutationFn: () =>
            installConnector({
                name: connectorName,
                connector_slug: connectorSlug,
                company_id: company?.id,
                config_json: {
                    base_url: baseUrl,
                    ...(authToken ? { auth_token: authToken } : {}),
                },
            }),
        onSuccess: () => {
            showToast({ message: "Connector installed", severity: "success" });
            queryClient.invalidateQueries({ queryKey: ["workforce", "connectors"] });
        },
        onError: (err: Error) => showToast({ message: err.message, severity: "error" }),
    });

    const testMutation = useMutation({
        mutationFn: (id: string) => testConnectorInstallation(id),
        onSuccess: (result) => {
            showToast({
                message: result.ok
                    ? `Connector OK${result.tool_count != null ? ` (${result.tool_count} tools)` : ""}`
                    : `Connector test failed: ${result.error || "unknown"}`,
                severity: result.ok ? "success" : "error",
            });
        },
        onError: (err: Error) => showToast({ message: err.message, severity: "error" }),
    });

    const summary = useMemo(() => catalog?.summary, [catalog]);

    const items = useMemo(() => {
        if (!catalog) return [];
        if (tab === "skills") return catalog.skills;
        if (tab === "workflows") return catalog.workflows;
        if (tab === "departments") return catalog.departments;
        if (tab === "agents") return catalog.agent_templates;
        return [];
    }, [catalog, tab]);

    return (
        <PageShell>
            <PageHeader
                title="Marketplace"
                description="Install skills, workflows, departments, agent templates, and MCP/A2A connectors."
            />
            <Stack spacing={2}>
                {error ? <Alert severity="error">{(error as Error).message}</Alert> : null}
                {summary ? (
                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                        <Chip label={`${summary.skills} skills`} />
                        <Chip label={`${summary.workflows} workflows`} />
                        <Chip label={`${summary.departments} departments`} />
                        <Chip label={`${summary.agent_templates} agent templates`} />
                    </Stack>
                ) : null}

                <Tabs
                    value={tab}
                    onChange={(_, value: TabKey) => setTab(value)}
                    variant="scrollable"
                    allowScrollButtonsMobile
                >
                    <Tab value="skills" label="Skills" />
                    <Tab value="workflows" label="Workflows" />
                    <Tab value="departments" label="Departments" />
                    <Tab value="agents" label="Agent templates" />
                    <Tab value="connectors" label="Connectors" />
                </Tabs>

                {tab === "agents" ? (
                    <Box>
                        <Button
                            variant="outlined"
                            onClick={() => seedAgentsMutation.mutate()}
                            disabled={seedAgentsMutation.isPending}
                        >
                            Seed all agent templates
                        </Button>
                    </Box>
                ) : null}

                {tab === "connectors" ? (
                    <Stack spacing={2}>
                        <Paper variant="outlined" sx={{ p: 2 }}>
                            <Stack spacing={1.5}>
                                <Typography variant="subtitle1">Install MCP / A2A connector</Typography>
                                <TextField
                                    select
                                    label="Connector type"
                                    value={connectorSlug}
                                    onChange={(e) => setConnectorSlug(e.target.value)}
                                    size="small"
                                >
                                    {(definitions.length
                                        ? definitions
                                        : [
                                              { slug: "mcp-http", name: "MCP HTTP Server" },
                                              { slug: "a2a-http", name: "A2A External Agent" },
                                          ]
                                    ).map((d) => (
                                        <MenuItem key={d.slug} value={d.slug}>
                                            {d.name}
                                        </MenuItem>
                                    ))}
                                </TextField>
                                <TextField
                                    label="Name"
                                    size="small"
                                    value={connectorName}
                                    onChange={(e) => setConnectorName(e.target.value)}
                                />
                                <TextField
                                    label="Base URL"
                                    size="small"
                                    value={baseUrl}
                                    onChange={(e) => setBaseUrl(e.target.value)}
                                />
                                <TextField
                                    label="Auth token (optional)"
                                    size="small"
                                    type="password"
                                    value={authToken}
                                    onChange={(e) => setAuthToken(e.target.value)}
                                />
                                <Button
                                    variant="contained"
                                    onClick={() => connectorInstallMutation.mutate()}
                                    disabled={connectorInstallMutation.isPending || !baseUrl}
                                >
                                    Install connector
                                </Button>
                            </Stack>
                        </Paper>
                        <Stack spacing={1}>
                            {installations.map((inst) => (
                                <Paper key={inst.id} variant="outlined" sx={{ p: 2 }}>
                                    <Stack direction="row" justifyContent="space-between" alignItems="center">
                                        <Box>
                                            <Typography variant="subtitle2">{inst.name}</Typography>
                                            <Typography variant="caption" color="text.secondary">
                                                {String(inst.config_json.base_url || "")} · {inst.status}
                                            </Typography>
                                        </Box>
                                        <Button
                                            size="small"
                                            onClick={() => testMutation.mutate(inst.id)}
                                            disabled={testMutation.isPending}
                                        >
                                            Test
                                        </Button>
                                    </Stack>
                                </Paper>
                            ))}
                            {!installations.length ? (
                                <Typography color="text.secondary">No connectors installed yet.</Typography>
                            ) : null}
                        </Stack>
                    </Stack>
                ) : isLoading ? (
                    <CircularProgress size={28} />
                ) : (
                    <Box
                        sx={{
                            display: "grid",
                            gap: 2,
                            gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
                        }}
                    >
                        {items.map((item) => {
                            const slug = String(item.slug || "");
                            const name = String(item.name || slug);
                            const description = String(item.description || "");
                            const meta = String(item.category || item.department || item.role || "");
                            return (
                                <CatalogCard
                                    key={slug}
                                    title={name}
                                    description={description}
                                    meta={meta || undefined}
                                    installing={installMutation.isPending}
                                    onInstall={() => installMutation.mutate({ kind: tab, slug })}
                                />
                            );
                        })}
                    </Box>
                )}
            </Stack>
        </PageShell>
    );
}
