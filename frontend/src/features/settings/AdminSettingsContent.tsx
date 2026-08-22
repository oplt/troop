import { lazy, Suspense } from "react";
import { useQuery } from "@tanstack/react-query";
import { Alert, Box, Skeleton, Tab, Tabs } from "@mui/material";

import { listGithubConnections, listProviders } from "../../api/orchestration";
import { ConfirmDestructiveDialog } from "../../components/ui/ConfirmDestructiveDialog";
import { PageHeader } from "../../components/ui/PageHeader";
import { PageShell } from "../../components/ui/PageShell";
import { CompaniesPanel } from "../../pages/CompaniesPage";
import { GithubSyncPanel } from "./github/GithubSyncPanel";
import { ProviderSettingsPanel } from "../../pages/ProviderSettingsPanel";
import { ProfileContent } from "../../pages/ProfilePage";
import type { DatabaseSetting } from "../../api/settings";
import { DatabaseSettingsPanel } from "./database/DatabaseSettingsPanel";
import { useDatabaseSettings } from "./database/useDatabaseSettings";
import { SecurityPosturePanel } from "./SecurityPosturePanel";
import { AuditExportPanel, IdentityProvidersPanel } from "./EnterpriseAuthPanels";
import { settingsShellSx, settingsTabsSx } from "./styles";
import type { SettingsTabValue } from "./types";

const AdminPlatformPage = lazy(() => import("../../pages/AdminPlatformPage"));
const AdminUsersPage = lazy(() => import("../../pages/AdminUsersPage"));

type AdminSettingsContentProps = {
    databaseSettings: DatabaseSetting[];
    databaseErrorMessage: string;
    hasDatabaseError: boolean;
    activeTab: SettingsTabValue;
    onTabChange: (nextTab: SettingsTabValue) => void;
};

export function AdminSettingsContent({
    databaseSettings,
    databaseErrorMessage,
    hasDatabaseError,
    activeTab,
    onTabChange,
}: AdminSettingsContentProps) {
    const { data: providers = [] } = useQuery({
        queryKey: ["orchestration", "providers"],
        queryFn: () => listProviders(),
    });
    const { data: githubConnections = [] } = useQuery({
        queryKey: ["orchestration", "github", "connections"],
        queryFn: () => listGithubConnections(),
    });

    const database = useDatabaseSettings();

    return (
        <PageShell maxWidth="xl">
            {hasDatabaseError && <Alert severity="error">{databaseErrorMessage}</Alert>}
            {database.databaseDirty && activeTab === "database" && (
                <Alert severity="warning" sx={{ mb: 1 }}>
                    Unsaved parameter edits — save before switching tabs or leaving.
                </Alert>
            )}
            <PageHeader
                title="Admin settings"
                description="Providers, sync, platform modules, users, and runtime parameters."
            />

            <Box sx={settingsShellSx}>
                <Tabs
                    value={activeTab}
                    onChange={(_, value: SettingsTabValue) =>
                        database.requestTabChange(activeTab, value, onTabChange)
                    }
                    orientation="vertical"
                    variant="scrollable"
                    scrollButtons="auto"
                    sx={settingsTabsSx}
                >
                    <Tab value="providers" label={`AI providers (${providers.length})`} />
                    <Tab value="github_sync" label={`GitHub sync (${githubConnections.length})`} />
                    <Tab value="platform" label="Platform" />
                    <Tab value="users" label="Users" />
                    <Tab value="security" label="Security posture" />
                    <Tab value="audit" label="Audit export" />
                    <Tab value="identity" label="SSO / IdP" />
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
                    ) : activeTab === "security" ? (
                        <SecurityPosturePanel />
                    ) : activeTab === "audit" ? (
                        <AuditExportPanel />
                    ) : activeTab === "identity" ? (
                        <IdentityProvidersPanel />
                    ) : activeTab === "companies" ? (
                        <CompaniesPanel />
                    ) : activeTab === "profile" ? (
                        <ProfileContent />
                    ) : (
                        <DatabaseSettingsPanel
                            settings={databaseSettings}
                            onDirtyChange={database.setDatabaseDirty}
                        />
                    )}
                </Box>
            </Box>

            <ConfirmDestructiveDialog
                open={Boolean(database.leaveTabTarget)}
                title="Leave without saving?"
                description="You have unsaved parameter edits. Leave this tab without saving?"
                confirmLabel="Leave"
                cancelLabel="Stay"
                confirmColor="primary"
                onClose={() => database.setLeaveTabTarget(null)}
                onConfirm={() => database.confirmLeaveTab(onTabChange)}
            />
        </PageShell>
    );
}
