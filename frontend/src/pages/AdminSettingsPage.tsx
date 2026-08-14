import { useQuery } from "@tanstack/react-query";
import { Skeleton, Stack } from "@mui/material";
import { useSearchParams } from "react-router-dom";

import { listDatabaseSettings } from "../api/settings";
import { PageShell } from "../components/ui/PageShell";
import { AdminSettingsContent } from "../features/settings/AdminSettingsContent";
import { parseSettingsTab } from "../features/settings/types";

export default function AdminSettingsPage() {
    const [searchParams, setSearchParams] = useSearchParams();
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

    const resolvedActiveTab = parseSettingsTab(searchParams.get("tab"));
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
