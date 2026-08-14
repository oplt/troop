import { lazy, Suspense, useState } from "react";
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
    listDatabaseSettings,
    listParameterCatalog,
    updateDatabaseSetting,
    type DatabaseSetting,
    type ParameterCatalogEntry,
} from "../api/settings";
import { listGithubConnections, listProviders } from "../api/orchestration";
import { EmptyState } from "../components/ui/EmptyState";
import { ConfirmDestructiveDialog } from "../components/ui/ConfirmDestructiveDialog";
import { PageHeader } from "../components/ui/PageHeader";
import { CompaniesPanel } from "./CompaniesPage";
import { GithubSyncPanel } from "./GithubSyncPage";
import { ProviderSettingsPanel } from "./ProviderSettingsPanel";
import { ProfileContent } from "./ProfilePage";
import { PageShell } from "../components/ui/PageShell";
import { SectionCard } from "../components/ui/SectionCard";
import { formatDateTime } from "../utils/formatters";
const AdminPlatformPage = lazy(() => import("./AdminPlatformPage"));
const AdminUsersPage = lazy(() => import("./AdminUsersPage"));

type DatabaseSettingDrafts = Record<
    string,
    {
        value: string;
        description: string;
    }
>;

type ParameterCatalogMap = Record<string, ParameterCatalogEntry>;

type SettingsTabValue = "database" | "providers" | "github_sync" | "platform" | "users" | "companies" | "profile";

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
                        <MenuItem key="true" value="true">
                            true
                        </MenuItem>,
                        <MenuItem key="false" value="false">
                            false
                        </MenuItem>,
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
                                  databaseSettings,
                                  databaseErrorMessage,
                                  hasDatabaseError,
                                  activeTab,
                                  onTabChange,
                              }: {
    databaseSettings: DatabaseSetting[];
    databaseErrorMessage: string;
    hasDatabaseError: boolean;
    activeTab: SettingsTabValue;
    onTabChange: (nextTab: SettingsTabValue) => void;
}) {
    const queryClient = useQueryClient();
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
    const [deleteTarget, setDeleteTarget] = useState<DatabaseSetting | null>(null);
    const [leaveTabTarget, setLeaveTabTarget] = useState<SettingsTabValue | null>(null);
    const databaseDirty = databaseSettings.some((item) => {
        const draft = databaseDrafts[item.id];
        if (!draft) return false;
        return draft.value !== item.value || draft.description !== (item.description ?? "");
    });
    const requestTabChange = (nextTab: SettingsTabValue) => {
        if (nextTab === activeTab) return;
        if (databaseDirty && activeTab === "database") {
            setLeaveTabTarget(nextTab);
            return;
        }
        onTabChange(nextTab);
    };
    const parameterCatalogMap: ParameterCatalogMap = Object.fromEntries(
        parameterCatalog.map((item) => [item.key, item])
    );
    const selectedParameterSpec = parameterCatalogMap[newSetting.key] ?? null;

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
            {hasDatabaseError && <Alert severity="error">{databaseErrorMessage}</Alert>}
            {databaseDirty && activeTab === "database" && (
                <Alert severity="warning" sx={{ mb: 1 }}>
                    Unsaved parameter edits — save before switching tabs or leaving.
                </Alert>
            )}
            <PageHeader title="Admin settings" description="Providers, sync, platform modules, users, and runtime parameters." />

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
                    onChange={(_, value: SettingsTabValue) => requestTabChange(value)}
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
                    <Tab value="providers" label={`AI providers (${providers.length})`} />
                    <Tab value="github_sync" label={`GitHub sync (${githubConnections.length})`} />
                    <Tab value="platform" label="Platform" />
                    <Tab value="users" label="Users" />
                    <Tab value="database" label={`Parameters (${databaseSettings.length})`} />
                    <Tab value="companies" label="Companies" />
                    <Tab value="profile" label="Profile" />
                </Tabs>

                <Box sx={{ flex: 1, py: 1.5, pr: 1.5, minWidth: 0 }}>
                    {activeTab === "providers" ? (
                        <ProviderSettingsPanel />
                    ) : activeTab === "github_sync" ? (
                        <GithubSyncPanel />
                    ) : activeTab === "platform" ? (
                        <Suspense fallback={<Skeleton variant="rounded" height={320} sx={{ borderRadius: 1 }} />}>
                            <AdminPlatformPage />
                        </Suspense>
                    ) : activeTab === "users" ? (
                        <Suspense fallback={<Skeleton variant="rounded" height={320} sx={{ borderRadius: 1 }} />}>
                            <AdminUsersPage />
                        </Suspense>
                    ) : activeTab === "companies" ? (
                        <CompaniesPanel />
                    ) : activeTab === "profile" ? (
                        <ProfileContent />
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
                                            <MenuItem key="new-true" value="true">
                                                true
                                            </MenuItem>,
                                            <MenuItem key="new-false" value="false">
                                                false
                                            </MenuItem>,
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
                                                    onDelete={() => setDeleteTarget(item)}
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
            <ConfirmDestructiveDialog
                open={Boolean(deleteTarget)}
                title="Delete parameter"
                description={deleteTarget ? `Remove “${deleteTarget.key}”? Runtime code that reads this key will fall back to defaults.` : ""}
                confirmLabel="Delete"
                loading={deleteDatabaseMutation.isPending}
                onClose={() => setDeleteTarget(null)}
                onConfirm={() => {
                    if (!deleteTarget) return;
                    deleteDatabaseMutation.mutate(deleteTarget.id, {
                        onSettled: () => setDeleteTarget(null),
                    });
                }}
            />
            <ConfirmDestructiveDialog
                open={Boolean(leaveTabTarget)}
                title="Leave without saving?"
                description="You have unsaved parameter edits. Leave this tab without saving?"
                confirmLabel="Leave"
                cancelLabel="Stay"
                confirmColor="primary"
                onClose={() => setLeaveTabTarget(null)}
                onConfirm={() => {
                    if (!leaveTabTarget) return;
                    onTabChange(leaveTabTarget);
                    setLeaveTabTarget(null);
                }}
            />
        </PageShell>
    );
}

export default function AdminSettingsPage() {
    const [searchParams, setSearchParams] = useSearchParams();
    const requestedTab = searchParams.get("tab");
    const normalizedRequestedTab =
        requestedTab === "ai" ? "providers" :
            requestedTab === "github" || requestedTab === "integrations" ? "github_sync" :
                requestedTab;
    const {
        data: databaseSettings,
        isLoading: databaseLoading,
        error: databaseError,
    } = useQuery({
        queryKey: ["settings", "database"],
        queryFn: listDatabaseSettings,
    });

    if (databaseLoading && !databaseSettings) {
        return (
            <PageShell maxWidth="xl">
                <Stack spacing={2}>
                    <Skeleton variant="rounded" height={180} sx={{ borderRadius: 6 }} />
                    <Skeleton variant="rounded" height={320} sx={{ borderRadius: 6 }} />
                </Stack>
            </PageShell>
        );
    }

    if (!databaseSettings) {
        return null;
    }

    const resolvedActiveTab =
        normalizedRequestedTab === "database" ||
        normalizedRequestedTab === "providers" ||
        normalizedRequestedTab === "github_sync" ||
        normalizedRequestedTab === "platform" ||
        normalizedRequestedTab === "users" ||
        normalizedRequestedTab === "companies" ||
        normalizedRequestedTab === "profile"
            ? (normalizedRequestedTab as SettingsTabValue)
            : "database";
    const settingsKey = databaseSettings.map((item) => `${item.id}:${item.updated_at}`).join("|");

    return (
        <AdminSettingsContent
            key={settingsKey}
            databaseSettings={databaseSettings}
            databaseErrorMessage={
                databaseError instanceof Error ? databaseError.message : "Couldn't load settings. Refresh to retry."
            }
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