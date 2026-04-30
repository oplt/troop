import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
    Alert,
    Box,
    Button,
    Chip,
    IconButton,
    MenuItem,
    Skeleton,
    Stack,
    Tab,
    Tabs,
    TextField,
    Typography,
} from "@mui/material";
import {
    DeleteOutline as DeleteIcon,
    Storage as StorageIcon,
} from "@mui/icons-material";
import { alpha } from "@mui/material/styles";
import { useSearchParams } from "react-router-dom";
import {
    createDatabaseSetting,
    deleteDatabaseSetting,
    getConfigSettings,
    listDatabaseSettings,
    listParameterCatalog,
    updateConfigSettings,
    updateDatabaseSetting,
    type ConfigEntry,
    type ConfigSettingsResponse,
    type DatabaseSetting,
    type ParameterCatalogEntry,
} from "../api/settings";
import { listGithubConnections, listProviders } from "../api/orchestration";
import { EmptyState } from "../components/ui/EmptyState";
import { GithubSyncPanel } from "./GithubSyncPage";
import { ProviderSettingsPanel } from "./OrchestrationSettingsPage";
import { PlatformPanel } from "./PlatformPage";
import { PageShell } from "../components/ui/PageShell";
import { SectionCard } from "../components/ui/SectionCard";
import { formatDateTime } from "../utils/formatters";

type DatabaseSettingDrafts = Record<
    string,
    {
        value: string;
        description: string;
    }
>;

type ParameterCatalogMap = Record<string, ParameterCatalogEntry>;

type ConfigGroupId =
    | "application"
    | "infrastructure"
    | "security"
    | "ai_config"
    | "github_app"
    | "email"
    | "observability"
    | "storage"
    | "custom";

type SettingsTabValue = ConfigGroupId | "database" | "providers" | "github_sync" | "platform";

type ConfigGroupDefinition = {
    id: ConfigGroupId;
    label: string;
    description: string;
};

const CONFIG_GROUP_DEFINITIONS: ConfigGroupDefinition[] = [
    {
        id: "application",
        label: "Application",
        description: "Branding, naming, environment identity, and app-facing defaults.",
    },
    {
        id: "infrastructure",
        label: "Infrastructure",
        description: "Hosts, ports, databases, cache, and background job plumbing.",
    },
    {
        id: "security",
        label: "Auth & Security",
        description: "Token behavior, cookies, verification windows, and admin access controls.",
    },
    {
        id: "ai_config",
        label: "AI Config",
        description: "Built-in model defaults, orchestration AI flags, and provider API credentials.",
    },
    {
        id: "github_app",
        label: "GitHub App",
        description: "GitHub App credentials and webhook configuration used by sync flows.",
    },
    {
        id: "email",
        label: "Email",
        description: "SMTP delivery settings for verification, reset, and notification mail.",
    },
    {
        id: "observability",
        label: "Observability",
        description: "Tracing, error capture, and telemetry export configuration.",
    },
    {
        id: "storage",
        label: "Storage",
        description: "Object storage connectivity, URL generation, and avatar upload limits.",
    },
    {
        id: "custom",
        label: "Custom",
        description: "Unmapped or custom environment variables kept in `backend/.env`.",
    },
];

function getConfigGroupId(item: ConfigEntry): ConfigGroupId {
    const { key, is_custom } = item;

    if (is_custom) {
        return "custom";
    }

    if (
        key === "PROVIDER_HEALTHCHECK_INTERVAL_MINUTES" ||
        key === "GITHUB_ISSUE_POLL_INTERVAL_MINUTES" ||
        key === "ORCHESTRATION_SLA_SCAN_INTERVAL_MINUTES"

    ) {
        return "infrastructure";
    }
    if (
        key === "ACCESS_TOKEN_EXPIRE_MINUTES" ||
        key === "REFRESH_TOKEN_EXPIRE_DAYS" ||
        key === "VERIFICATION_TOKEN_TTL" ||
        key === "PASSWORD_RESET_TOKEN_TTL" ||
        key === "PUBLIC_RATE_LIMIT_REQUESTS" ||
        key === "PUBLIC_RATE_LIMIT_WINDOW_SECONDS" ||
        key === "AUTH_FAILURE_LIMIT" ||
        key === "AUTH_FAILURE_WINDOW_SECONDS" ||
        key === "REQUIRE_EMAIL_VERIFICATION"
    ) {
        return "security";
    }
    if (
        key.startsWith("AI_") ||
        key === "ORCHESTRATION_RUN_RATE_LIMIT_PER_MINUTE" ||
        key === "AGENT_TOKEN_BUDGET_WINDOW_DAYS"
    ) {
        return "ai_config";
    }
    return "application";
}

function buildConfigGroups(items: ConfigEntry[]) {
    const grouped = Object.fromEntries(
        CONFIG_GROUP_DEFINITIONS.map((group) => [group.id, [] as ConfigEntry[]])
    ) as Record<ConfigGroupId, ConfigEntry[]>;

    items.forEach((item) => {
        grouped[getConfigGroupId(item)].push(item);
    });

    return CONFIG_GROUP_DEFINITIONS
        .map((group) => ({
            ...group,
            items: grouped[group.id],
        }))
        .filter((group) => group.items.length > 0);
}

function ConfigEntryEditor({
    item,
    value,
    onChange,
}: {
    item: ConfigEntry;
    value: string;
    onChange: (nextValue: string) => void;
}) {
    return (
        <Box
            sx={(theme) => ({
                p: 2,
                borderRadius: 4,
                border: `1px solid ${theme.palette.divider}`,
                backgroundColor: alpha(theme.palette.background.paper, 0.78),
            })}
        >
            <Stack spacing={1.25}>
                <Stack
                    direction={{ xs: "column", sm: "row" }}
                    justifyContent="space-between"
                    spacing={1}
                >
                    <Box>
                        <Typography variant="subtitle2">{item.key}</Typography>
                        {item.description && (
                            <Typography variant="body2" color="text.secondary">
                                {item.description}
                            </Typography>
                        )}
                    </Box>
                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                        <Chip label={item.value_type} size="small" variant="outlined" />
                        {item.is_custom && <Chip label="custom" size="small" variant="outlined" />}
                        {item.requires_restart && (
                            <Chip
                                label="restart recommended"
                                size="small"
                                color="warning"
                                variant="outlined"
                            />
                        )}
                    </Stack>
                </Stack>
                <TextField
                    type={item.is_secret ? "password" : "text"}
                    value={value}
                    onChange={(event) => onChange(event.target.value)}
                    helperText={item.is_secret ? "Stored value is masked. Enter a new value to replace it." : undefined}
                    fullWidth
                />
            </Stack>
        </Box>
    );
}

function DatabaseSettingEditor({
    item,
    draft,
    spec,
    onDraftChange,
    onSave,
    onDelete,
    isSaving,
    isDeleting,
}: {
    item: DatabaseSetting;
    draft: {
        value: string;
        description: string;
    };
    spec: ParameterCatalogEntry | null;
    onDraftChange: (nextDraft: { value: string; description: string }) => void;
    onSave: () => void;
    onDelete: () => void;
    isSaving: boolean;
    isDeleting: boolean;
}) {
    const valueType = spec?.value_type ?? "string";
    const isKnown = Boolean(spec);
    return (
        <Box
            sx={(theme) => ({
                p: 2.25,
                borderRadius: 4,
                border: `1px solid ${theme.palette.divider}`,
            })}
        >
            <Stack spacing={1.5}>
                <Stack direction="row" justifyContent="space-between" spacing={1.5}>
                    <Box>
                        <Typography variant="subtitle2">{item.key}</Typography>
                        <Typography variant="caption" color="text.secondary">
                            Updated {formatDateTime(item.updated_at)}
                        </Typography>
                    </Box>
                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                        <Chip label={valueType} size="small" variant="outlined" />
                        {!isKnown && <Chip label="unknown" size="small" color="warning" variant="outlined" />}
                    </Stack>
                    <IconButton color="error" onClick={onDelete} disabled={isDeleting}>
                        <DeleteIcon />
                    </IconButton>
                </Stack>
                <TextField
                    label="Value"
                    value={draft.value}
                    onChange={(event) => onDraftChange({ value: event.target.value, description: draft.description })}
                    select={valueType === "bool"}
                    fullWidth
                    multiline={valueType === "json"}
                    minRows={valueType === "json" ? 3 : undefined}
                >
                    {valueType === "bool" ? [
                        <MenuItem key="true" value="true">true</MenuItem>,
                        <MenuItem key="false" value="false">false</MenuItem>,
                    ] : null}
                </TextField>
                {spec?.description ? (
                    <Typography variant="caption" color="text.secondary">
                        {spec.description}
                    </Typography>
                ) : null}
                {!isKnown ? (
                    <Alert severity="warning">
                        Unknown parameter key. This row is legacy/custom and not in catalog.
                    </Alert>
                ) : null}
                {valueType === "int" ? (
                    <Typography variant="caption" color="text.secondary">
                        Enter integer value.
                    </Typography>
                ) : null}
                {valueType === "json" ? (
                    <Typography variant="caption" color="text.secondary">
                        Enter valid JSON object/array text.
                    </Typography>
                ) : null}
                <TextField
                    label="Description"
                    value={draft.description}
                    onChange={(event) =>
                        onDraftChange({
                            value: draft.value,
                            description: event.target.value,
                        })
                    }
                    fullWidth
                    multiline
                    minRows={3}
                />
                <Button variant="contained" disabled={isSaving} onClick={onSave}>
                    {isSaving ? "Saving..." : "Save parameter"}
                </Button>
            </Stack>
        </Box>
    );
}

function AdminSettingsContent({
    configData,
    databaseSettings,
    configErrorMessage,
    databaseErrorMessage,
    hasConfigError,
    hasDatabaseError,
    activeTab,
    onTabChange,
}: {
    configData: ConfigSettingsResponse;
    databaseSettings: DatabaseSetting[];
    configErrorMessage: string;
    databaseErrorMessage: string;
    hasConfigError: boolean;
    hasDatabaseError: boolean;
    activeTab: SettingsTabValue;
    onTabChange: (nextTab: SettingsTabValue) => void;
}) {
    const queryClient = useQueryClient();
    const configGroups: Array<{
        id: ConfigGroupId;
        label: string;
        description: string;
        items: ConfigEntry[];
    }> = [];
    const { data: providers = [] } = useQuery({
        queryKey: ["orchestration", "providers"],
        queryFn: () => listProviders(),
    });
    const { data: githubConnections = [] } = useQuery({
        queryKey: ["orchestration", "github", "connections"],
        queryFn: () => listGithubConnections(),
    });
    const { data: parameterCatalog = [] } = useQuery({
        queryKey: ["settings", "database", "catalog"],
        queryFn: listParameterCatalog,
    });
    const [configDrafts, setConfigDrafts] = useState<Record<string, string>>(() =>
        Object.fromEntries(configData.items.map((item) => [item.key, item.value]))
    );
    const [databaseDrafts, setDatabaseDrafts] = useState<DatabaseSettingDrafts>(() =>
        Object.fromEntries(
            databaseSettings.map((item) => [
                item.id,
                {
                    value: item.value,
                    description: item.description ?? "",
                },
            ])
        )
    );
    const [newSetting, setNewSetting] = useState({
        key: "",
        value: "",
        description: "",
    });
    const parameterCatalogMap: ParameterCatalogMap = Object.fromEntries(
        parameterCatalog.map((item) => [item.key, item])
    );
    const selectedParameterSpec = parameterCatalogMap[newSetting.key] ?? null;

    const activeConfigGroup =
        activeTab === "database" || activeTab === "providers" || activeTab === "github_sync" || activeTab === "platform"
            ? null
            : configGroups.find((group) => group.id === activeTab) ?? configGroups[0] ?? null;
    const changedConfigCount = configData.items.filter(
        (item) => (configDrafts[item.key] ?? item.value) !== item.value
    ).length;

    const configMutation = useMutation({
        mutationFn: updateConfigSettings,
        onSuccess: (data) => {
            queryClient.setQueryData(["settings", "config"], data);
            setConfigDrafts(Object.fromEntries(data.items.map((item) => [item.key, item.value])));
        },
    });
    const createDatabaseMutation = useMutation({
        mutationFn: createDatabaseSetting,
        onSuccess: async () => {
            setNewSetting({ key: "", value: "", description: "" });
            await queryClient.invalidateQueries({ queryKey: ["settings", "database"] });
        },
    });
    const updateDatabaseMutation = useMutation({
        mutationFn: ({ id, value, description }: { id: string; value: string; description: string }) =>
            updateDatabaseSetting(id, { value, description }),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["settings", "database"] });
        },
    });
    const deleteDatabaseMutation = useMutation({
        mutationFn: deleteDatabaseSetting,
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["settings", "database"] });
        },
    });

    return (
        <PageShell maxWidth="xl">

            {hasConfigError && <Alert severity="error">{configErrorMessage}</Alert>}
            {hasDatabaseError && <Alert severity="error">{databaseErrorMessage}</Alert>}

            <Box
                sx={(theme) => ({
                    display: "flex",
                    gap: 2,
                    alignItems: "start",
                    border: `1px solid ${theme.palette.divider}`,
                    borderRadius: 4,
                    backgroundColor: alpha(theme.palette.background.paper, 0.82),
                    overflow: "hidden",
                })}
            >
                <Tabs
                    value={activeTab}
                    onChange={(_, value: SettingsTabValue) => onTabChange(value)}
                    orientation="vertical"
                    variant="scrollable"
                    scrollButtons="auto"
                    sx={(theme) => ({
                        minWidth: 200,
                        borderRight: `1px solid ${theme.palette.divider}`,
                        flexShrink: 0,
                        "& .MuiTab-root": {
                            alignItems: "flex-start",
                            textAlign: "left",
                            px: 2.5,
                            py: 1.5,
                        },
                    })}
                >
                    {configGroups.map((group) => (
                        <Tab
                            key={group.id}
                            value={group.id}
                            label={`${group.label} (${group.items.length})`}
                        />
                    ))}

                    <Tab
                        value="providers"
                        label={`AI providers (${providers.length})`}
                    />
                    <Tab
                        value="github_sync"
                        label={`GitHub sync (${githubConnections.length})`}
                    />
                    <Tab
                        value="database"
                        label={`Parameters (${databaseSettings.length})`}
                    />
                    <Tab
                        value="platform"
                        label="Platform"
                    />
                    
                </Tabs>

                <Box sx={{ flex: 1, py: 1.5, pr: 1.5, minWidth: 0 }}>
            {activeTab === "providers" ? (
                <ProviderSettingsPanel />
            ) : activeTab === "github_sync" ? (
                <GithubSyncPanel />
            ) : activeTab === "platform" ? (
                <PlatformPanel />
            ) : activeConfigGroup ? (
                <SectionCard
                    title={activeConfigGroup.label}
                    description={activeConfigGroup.description}
                    action={
                        <Button
                            variant="contained"
                            disabled={configMutation.isPending || changedConfigCount === 0}
                            onClick={() =>
                                configMutation.mutate({
                                    items: configData.items.map((item) => ({
                                        key: item.key,
                                        value: configDrafts[item.key] ?? "",
                                    })),
                                })
                            }
                        >
                            {configMutation.isPending ? "Saving..." : "Save all config"}
                        </Button>
                    }
                >
                    <Stack spacing={2}>
                        <Alert severity="info">{configData.notice}</Alert>
                        {configMutation.isSuccess && (
                            <Alert severity="success">
                                Config saved. Restart the backend if a startup-bound value changed.
                            </Alert>
                        )}
                        {configMutation.isError && (
                            <Alert severity="error">
                                {configMutation.error instanceof Error
                                    ? configMutation.error.message
                                    : "Couldn't save config. Try again."}
                            </Alert>
                        )}

                        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                            <Chip
                                label={`${activeConfigGroup.items.length} variables in this group`}
                                variant="outlined"
                            />
                            <Chip
                                label={
                                    changedConfigCount > 0
                                        ? `${changedConfigCount} unsaved changes across all tabs`
                                        : "No unsaved config changes"
                                }
                                color={changedConfigCount > 0 ? "warning" : "default"}
                                variant="outlined"
                            />
                        </Stack>

                        <Box
                            sx={{
                                display: "grid",
                                gap: 1.5,
                                gridTemplateColumns: { xs: "1fr", md: "repeat(2, minmax(0, 1fr))" },
                                alignItems: "start",
                            }}
                        >
                            {activeConfigGroup.items.map((item) => (
                                <ConfigEntryEditor
                                    key={item.key}
                                    item={item}
                                    value={configDrafts[item.key] ?? item.value}
                                    onChange={(nextValue) =>
                                        setConfigDrafts((current) => ({
                                            ...current,
                                            [item.key]: nextValue,
                                        }))
                                    }
                                />
                            ))}
                        </Box>
                    </Stack>
                </SectionCard>
            ) : (
                <Box
                    sx={{
                        display: "grid",
                        gap: 2,
                        gridTemplateColumns: { xs: "1fr", lg: "minmax(320px, 0.9fr) minmax(0, 1.1fr)" },
                        alignItems: "start",
                    }}
                >
                    <SectionCard
                        title="Add parameter"
                        description="Create typed runtime parameters from the supported catalog."
                    >
                        <Stack spacing={2}>
                                {createDatabaseMutation.isSuccess && (
                                <Alert severity="success">Parameter created.</Alert>
                            )}
                            {createDatabaseMutation.isError && (
                                <Alert severity="error">
                                    {createDatabaseMutation.error instanceof Error
                                        ? createDatabaseMutation.error.message
                                        : "Couldn't save parameter. Try again."}
                                </Alert>
                            )}
                            <TextField
                                label="Key"
                                value={newSetting.key}
                                onChange={(event) => {
                                    const spec = parameterCatalogMap[event.target.value] ?? null;
                                    setNewSetting((current) => ({
                                        ...current,
                                        key: event.target.value,
                                        value: spec ? spec.default_value : "",
                                        description: spec?.description ?? current.description,
                                    }));
                                }}
                                select
                                fullWidth
                            >
                                {parameterCatalog.map((entry) => (
                                    <MenuItem key={entry.key} value={entry.key}>
                                        {entry.key}
                                    </MenuItem>
                                ))}
                            </TextField>
                            <TextField
                                label="Value"
                                value={newSetting.value}
                                onChange={(event) =>
                                    setNewSetting((current) => ({
                                        ...current,
                                        value: event.target.value,
                                    }))
                                }
                                fullWidth
                                select={selectedParameterSpec?.value_type === "bool"}
                                multiline={selectedParameterSpec?.value_type === "json"}
                                minRows={selectedParameterSpec?.value_type === "json" ? 3 : undefined}
                            >
                                {selectedParameterSpec?.value_type === "bool" ? [
                                    <MenuItem key="new-true" value="true">true</MenuItem>,
                                    <MenuItem key="new-false" value="false">false</MenuItem>,
                                ] : null}
                            </TextField>
                            {selectedParameterSpec ? (
                                <Typography variant="caption" color="text.secondary">
                                    Type: {selectedParameterSpec.value_type}. {selectedParameterSpec.description}
                                </Typography>
                            ) : null}
                            <TextField
                                label="Description"
                                value={newSetting.description}
                                onChange={(event) =>
                                    setNewSetting((current) => ({
                                        ...current,
                                        description: event.target.value,
                                    }))
                                }
                                fullWidth
                                multiline
                                minRows={3}
                            />
                            <Button
                                variant="contained"
                                disabled={createDatabaseMutation.isPending || !newSetting.key.trim()}
                                onClick={() =>
                                    createDatabaseMutation.mutate({
                                        key: newSetting.key.trim(),
                                        value: newSetting.value,
                                        description: newSetting.description || undefined,
                                    })
                                }
                            >
                                {createDatabaseMutation.isPending ? "Adding..." : "Add parameter"}
                            </Button>
                        </Stack>
                    </SectionCard>

                    <SectionCard
                        title="Parameters"
                        description="Review, edit, and delete runtime parameters stored in the database."
                    >
                        {databaseSettings.length > 0 ? (
                            <Box
                                sx={{
                                    display: "grid",
                                    gap: 1.5,
                                    gridTemplateColumns: { xs: "1fr", xl: "repeat(2, minmax(0, 1fr))" },
                                    alignItems: "start",
                                }}
                            >
                                {databaseSettings.map((item) => {
                                    const isSavingThisItem =
                                        updateDatabaseMutation.isPending &&
                                        updateDatabaseMutation.variables?.id === item.id;
                                    const isDeletingThisItem =
                                        deleteDatabaseMutation.isPending &&
                                        deleteDatabaseMutation.variables === item.id;

                                    return (
                                        <DatabaseSettingEditor
                                            key={item.id}
                                            item={item}
                                            spec={parameterCatalogMap[item.key] ?? null}
                                            draft={databaseDrafts[item.id] ?? {
                                                value: item.value,
                                                description: item.description ?? "",
                                            }}
                                            onDraftChange={(nextDraft) =>
                                                setDatabaseDrafts((current) => ({
                                                    ...current,
                                                    [item.id]: nextDraft,
                                                }))
                                            }
                                            onSave={() =>
                                                updateDatabaseMutation.mutate({
                                                    id: item.id,
                                                    value: databaseDrafts[item.id]?.value ?? item.value,
                                                    description:
                                                        databaseDrafts[item.id]?.description ??
                                                        item.description ??
                                                        "",
                                                })
                                            }
                                            onDelete={() => deleteDatabaseMutation.mutate(item.id)}
                                            isSaving={isSavingThisItem}
                                            isDeleting={isDeletingThisItem}
                                        />
                                    );
                                })}
                            </Box>
                        ) : (
                            <EmptyState
                                icon={<StorageIcon />}
                                title="No parameters yet"
                                description="Create a parameter when you need runtime-configurable values stored in the database."
                            />
                        )}
                    </SectionCard>
                </Box>
            )}
                </Box>
            </Box>
        </PageShell>
    );
}

export default function AdminSettingsPage() {
    const [searchParams, setSearchParams] = useSearchParams();
    const requestedTab = searchParams.get("tab");
    const normalizedRequestedTab =
        requestedTab === "ai" ? "providers" : requestedTab === "github" ? "github_sync" : requestedTab;
    const {
        data: configData,
        isLoading: configLoading,
        error: configError,
    } = useQuery({
        queryKey: ["settings", "config"],
        queryFn: getConfigSettings,
    });
    const {
        data: databaseSettings,
        isLoading: databaseLoading,
        error: databaseError,
    } = useQuery({
        queryKey: ["settings", "database"],
        queryFn: listDatabaseSettings,
    });

    if ((configLoading && !configData) || (databaseLoading && !databaseSettings)) {
        return (
            <PageShell maxWidth="xl">
                <Stack spacing={2}>
                    <Skeleton variant="rounded" height={180} sx={{ borderRadius: 6 }} />
                    <Skeleton variant="rounded" height={320} sx={{ borderRadius: 6 }} />
                </Stack>
            </PageShell>
        );
    }

    if (!configData || !databaseSettings) {
        return null;
    }

    const configGroups = buildConfigGroups(configData.items);
    const resolvedActiveTab =
        normalizedRequestedTab === "database" ||
        normalizedRequestedTab === "providers" ||
        normalizedRequestedTab === "github_sync" ||
        normalizedRequestedTab === "platform" ||
        configGroups.some((group) => group.id === normalizedRequestedTab)
            ? (normalizedRequestedTab as SettingsTabValue)
            : configGroups[0]?.id ?? "database";
    const settingsKey = `${configData.items.map((item) => `${item.key}:${item.value}`).join("|")}::${databaseSettings
        .map((item) => `${item.id}:${item.updated_at}`)
        .join("|")}`;

    return (
        <AdminSettingsContent
            key={settingsKey}
            configData={configData}
            databaseSettings={databaseSettings}
            configErrorMessage={
                configError instanceof Error ? configError.message : "Couldn't load config. Refresh to retry."
            }
            databaseErrorMessage={
                databaseError instanceof Error ? databaseError.message : "Couldn't load settings. Refresh to retry."
            }
            hasConfigError={Boolean(configError)}
            hasDatabaseError={Boolean(databaseError)}
            activeTab={resolvedActiveTab}
            onTabChange={(nextTab) => {
                const next = new URLSearchParams(searchParams);
                next.set("tab", nextTab);
                setSearchParams(next, { replace: true });
            }}
        />
    );
}
