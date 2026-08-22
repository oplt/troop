import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link as RouterLink } from "react-router-dom";
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
    importWorkspacePackage,
    installConnector,
    installMarketplaceAgentTemplate,
    installMarketplaceDepartment,
    installMarketplaceSkill,
    installMarketplaceWorkflow,
    installWorkspacePackage,
    listConnectorDefinitions,
    listConnectorInstallations,
    listWorkspacePackages,
    seedMarketplaceAgentTemplates,
    testConnectorInstallation,
    type WorkspacePackageSummary,
} from "../api/workforce";
import { listConnectorManifests } from "../api/integrations";
import { getDefaultCompany } from "../api/companies";
import { useSnackbar } from "../app/snackbarContext";
import { ConnectorSetupForm } from "../features/connectors/ConnectorSetupForm";
import { resolveSetupManifest } from "../features/connectors/manifestUtils";
import { PageHeader } from "../components/ui/PageHeader";
import { PageShell } from "../components/ui/PageShell";
import { CatalogCard } from "../components/ui/CatalogCard";
import { GovernanceStepLegend } from "../features/templates/emailApproval/GovernanceStepLegend";
import {
    EMAIL_APPROVAL_FLAGSHIP_SLUG,
    findFlagshipWorkflow,
    isEmailApprovalTemplatePack,
    type EmailApprovalTemplatePack,
} from "../features/templates/emailApproval/types";

type TabKey = "skills" | "workflows" | "departments" | "agents" | "connectors" | "workspace";

export default function MarketplacePage() {
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();
    const [tab, setTab] = useState<TabKey>("skills");
    const [connectorSlug, setConnectorSlug] = useState("mcp-http");
    const [connectorName, setConnectorName] = useState("My MCP server");
    const [connectorConfig, setConnectorConfig] = useState<Record<string, unknown>>({
        base_url: "http://127.0.0.1:8080/mcp",
    });

    const { data: company } = useQuery({
        queryKey: ["companies", "default"],
        queryFn: getDefaultCompany,
    });

    const { data: catalog, isLoading, error } = useQuery({
        queryKey: ["workforce", "marketplace"],
        queryFn: getMarketplaceCatalog,
    });

    const { data: workspacePackages = [], isLoading: workspaceLoading } = useQuery({
        queryKey: ["workforce", "marketplace", "workspace-packages"],
        queryFn: listWorkspacePackages,
        enabled: tab === "workspace",
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

    const { data: manifests = [] } = useQuery({
        queryKey: ["workforce", "connectors", "manifests"],
        queryFn: listConnectorManifests,
        enabled: tab === "connectors",
    });

    const selectedManifest = resolveSetupManifest(manifests, definitions, connectorSlug);

    const importPackageMutation = useMutation({
        mutationFn: ({ kind, slug }: { kind: TabKey; slug: string }) =>
            importWorkspacePackage({ kind: kind === "agents" ? "agent_template" : kind.replace(/s$/, ""), marketplace_slug: slug }),
        onSuccess: () => {
            showToast({ message: "Imported to private workspace catalog.", severity: "success" });
            queryClient.invalidateQueries({ queryKey: ["workforce", "marketplace", "workspace-packages"] });
            setTab("workspace");
        },
        onError: (err: Error) => showToast({ message: err.message, severity: "error" }),
    });

    const installPackageMutation = useMutation({
        mutationFn: ({ packageId, versionId, accept }: { packageId: string; versionId: string; accept: boolean }) =>
            installWorkspacePackage(packageId, { version_id: versionId, accept_permission_changes: accept }),
        onSuccess: (result) => {
            showToast({ message: `Package ${result.status}`, severity: "success" });
            queryClient.invalidateQueries({ queryKey: ["workforce", "marketplace", "workspace-packages"] });
        },
        onError: (err: Error) => showToast({ message: err.message, severity: "error" }),
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
                config_json: connectorConfig,
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
    const flagshipWorkflow = useMemo(
        () => findFlagshipWorkflow(catalog?.workflows ?? []),
        [catalog?.workflows],
    );
    const flagshipPack: EmailApprovalTemplatePack | undefined = isEmailApprovalTemplatePack(
        flagshipWorkflow?.template_pack,
    )
        ? flagshipWorkflow.template_pack
        : undefined;

    const items = useMemo(() => {
        if (!catalog) return [];
        if (tab === "skills") return catalog.skills;
        if (tab === "workflows") {
            return catalog.workflows.filter((item) => item.slug !== EMAIL_APPROVAL_FLAGSHIP_SLUG);
        }
        if (tab === "departments") return catalog.departments;
        if (tab === "agents") return catalog.agent_templates;
        return [];
    }, [catalog, tab]);

    return (
        <PageShell>
            <PageHeader
                title="Marketplace"
                description="One catalog for skills, workflows, departments, agent templates, and connectors. Prefer Skills or Agents when you already know the type."
                actions={
                    <Stack direction="row" spacing={1}>
                        <Button component={RouterLink} to="/skills" size="small" variant="outlined">Skills</Button>
                        <Button component={RouterLink} to="/agents" size="small" variant="outlined">Agents</Button>
                    </Stack>
                }
            />
            <Stack spacing={2}>
                {catalog?.policy && !catalog.policy.public_marketplace_enabled ? (
                    <Alert severity="info">
                        Public marketplace publishing is deferred. Import templates into your private workspace catalog
                        with signed versions and review permission changes before upgrading.
                    </Alert>
                ) : null}
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
                    <Tab value="workspace" label="Workspace packages" />
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

                {tab === "workspace" ? (
                    <Stack spacing={2}>
                        {workspaceLoading ? <CircularProgress size={28} /> : null}
                        {!workspaceLoading && workspacePackages.length === 0 ? (
                            <Typography color="text.secondary">
                                No private workspace packages yet. Use &quot;Save to workspace&quot; on a catalog item.
                            </Typography>
                        ) : null}
                        {workspacePackages.map((pkg: WorkspacePackageSummary) => (
                            <Paper key={pkg.id} variant="outlined" sx={{ p: 2 }}>
                                <Stack spacing={1}>
                                    <Stack direction="row" justifyContent="space-between" alignItems="flex-start" gap={1}>
                                        <Box>
                                            <Typography variant="subtitle2">{pkg.name}</Typography>
                                            <Typography variant="caption" color="text.secondary">
                                                {pkg.kind} · v{pkg.latest_version_label ?? "?"} · {pkg.source_marketplace_slug}
                                            </Typography>
                                        </Box>
                                        <Stack direction="row" spacing={0.5}>
                                            <Chip size="small" label="private" variant="outlined" />
                                            {pkg.trust_level ? (
                                                <Chip size="small" color="success" label={pkg.trust_level} variant="outlined" />
                                            ) : null}
                                        </Stack>
                                    </Stack>
                                    <Typography variant="body2" color="text.secondary">{pkg.description}</Typography>
                                    {pkg.latest_version_id ? (
                                        <Button
                                            size="small"
                                            variant="contained"
                                            disabled={installPackageMutation.isPending}
                                            onClick={() =>
                                                installPackageMutation.mutate({
                                                    packageId: pkg.id,
                                                    versionId: pkg.latest_version_id!,
                                                    accept: pkg.installed_version_id !== null,
                                                })
                                            }
                                        >
                                            {pkg.installed_version_id ? "Upgrade (accept permissions)" : "Install"}
                                        </Button>
                                    ) : null}
                                </Stack>
                            </Paper>
                        ))}
                    </Stack>
                ) : tab === "connectors" ? (
                    <Stack spacing={2}>
                        <Paper variant="outlined" sx={{ p: 2 }}>
                            <Stack spacing={1.5}>
                                <Typography variant="subtitle1">Install MCP / A2A connector</Typography>
                                <TextField
                                    select
                                    label="Connector type"
                                    value={connectorSlug}
                                    onChange={(e) => {
                                        setConnectorSlug(e.target.value);
                                        setConnectorConfig({});
                                    }}
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
                                <ConnectorSetupForm
                                    manifest={selectedManifest}
                                    values={connectorConfig}
                                    onChange={(key, value) => setConnectorConfig((current) => ({ ...current, [key]: value }))}
                                />
                                <Button
                                    variant="contained"
                                    onClick={() => connectorInstallMutation.mutate()}
                                    disabled={connectorInstallMutation.isPending || (selectedManifest?.auth.type !== "oauth2" && !String(connectorConfig.base_url ?? connectorConfig.bot_token ?? "").trim())}
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
                    <Stack spacing={2}>
                        {tab === "workflows" && flagshipPack ? (
                            <Paper variant="outlined" sx={{ p: 2, borderRadius: 2 }}>
                                <Stack spacing={2}>
                                    <Stack direction="row" justifyContent="space-between" alignItems="flex-start" gap={2}>
                                        <Box>
                                            <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                                                <Typography variant="h6">{flagshipPack.title}</Typography>
                                                <Chip size="small" color="primary" label="Flagship" />
                                            </Stack>
                                            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.75 }}>
                                                Recommended first automation — governed Gmail replies with exact-effect approval.
                                            </Typography>
                                        </Box>
                                        <Stack direction="row" spacing={1}>
                                            <Button component={RouterLink} to="/templates/email-approval" variant="contained">
                                                Guided install
                                            </Button>
                                            <Button
                                                variant="outlined"
                                                disabled={installMutation.isPending}
                                                onClick={() =>
                                                    installMutation.mutate({
                                                        kind: "workflows",
                                                        slug: EMAIL_APPROVAL_FLAGSHIP_SLUG,
                                                    })
                                                }
                                            >
                                                Quick install
                                            </Button>
                                        </Stack>
                                    </Stack>
                                    <GovernanceStepLegend pack={flagshipPack} compact />
                                </Stack>
                            </Paper>
                        ) : null}
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
                                    primaryCta={{
                                        label: "Install",
                                        loadingLabel: "Installing…",
                                        disabled: installMutation.isPending,
                                        onClick: () => installMutation.mutate({ kind: tab, slug }),
                                    }}
                                    secondaryAction={
                                        <Button
                                            size="small"
                                            variant="outlined"
                                            disabled={importPackageMutation.isPending}
                                            onClick={() => importPackageMutation.mutate({ kind: tab, slug })}
                                        >
                                            Save to workspace
                                        </Button>
                                    }
                                />
                            );
                        })}
                        </Box>
                    </Stack>
                )}
            </Stack>
        </PageShell>
    );
}
