import { useQuery } from "@tanstack/react-query";
import { Skeleton, Stack } from "@mui/material";

import {
    getPlatformConfig,
    listAdminEmailTemplates,
    listAdminFeatureFlags,
    listAdminPlans,
} from "../api/platform";
import { PageShell } from "../components/ui/PageShell";
import { AdminPlatformContent } from "../features/adminPlatform/AdminPlatformContent";

export default function AdminPlatformPage() {
    const { data: configData, isLoading: configLoading } = useQuery({
        queryKey: ["platform", "admin", "config"],
        queryFn: getPlatformConfig,
    });
    const { data: plans, isLoading: plansLoading } = useQuery({
        queryKey: ["platform", "admin", "plans"],
        queryFn: listAdminPlans,
    });
    const { data: flags, isLoading: flagsLoading } = useQuery({
        queryKey: ["platform", "admin", "feature-flags"],
        queryFn: listAdminFeatureFlags,
    });
    const { data: templates, isLoading: templatesLoading } = useQuery({
        queryKey: ["platform", "admin", "email-templates"],
        queryFn: listAdminEmailTemplates,
    });

    if (configLoading || plansLoading || flagsLoading || templatesLoading) {
        return (
            <PageShell maxWidth="xl">
                <Stack spacing={2}>
                    <Skeleton variant="rounded" height={180} sx={{ borderRadius: 6 }} />
                    <Skeleton variant="rounded" height={240} sx={{ borderRadius: 6 }} />
                    <Skeleton variant="rounded" height={240} sx={{ borderRadius: 6 }} />
                </Stack>
            </PageShell>
        );
    }

    if (!configData || !plans || !flags || !templates) {
        return null;
    }

    const pageKey = [
        configData.app_name,
        configData.module_pack,
        configData.module_catalog.map((item) => `${item.key}:${item.enabled}`).join("|"),
        plans.map((plan) => `${plan.id}:${plan.updated_at}`).join("|"),
        flags.map((flag) => `${flag.id}:${flag.updated_at}`).join("|"),
        templates.map((template) => `${template.id}:${template.updated_at}`).join("|"),
    ].join("::");

    return (
        <AdminPlatformContent
            key={pageKey}
            configData={configData}
            plans={plans}
            flags={flags}
            templates={templates}
        />
    );
}
