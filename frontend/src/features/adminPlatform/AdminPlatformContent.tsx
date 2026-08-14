import type { EmailTemplate, FeatureFlag, PlatformConfig, SubscriptionPlan } from "../../api/platform";
import { DensePageMobileNotice } from "../../components/ui/DensePageMobileNotice";
import { PageHeader } from "../../components/ui/PageHeader";
import { PageShell } from "../../components/ui/PageShell";
import { AdminPlatformOverview } from "./AdminPlatformOverview";
import { PlatformConfigPanel } from "./config/PlatformConfigPanel";
import { EmailTemplatesPanel } from "./emailTemplates/EmailTemplatesPanel";
import { FeatureFlagsPanel } from "./featureFlags/FeatureFlagsPanel";
import { usePlatformAdmin } from "./hooks/usePlatformAdmin";
import { PlansPanel } from "./plans/PlansPanel";

type AdminPlatformContentProps = {
    configData: PlatformConfig;
    plans: SubscriptionPlan[];
    flags: FeatureFlag[];
    templates: EmailTemplate[];
};

export function AdminPlatformContent({
    configData,
    plans,
    flags,
    templates,
}: AdminPlatformContentProps) {
    const admin = usePlatformAdmin({ configData, plans, flags, templates });

    return (
        <PageShell maxWidth="xl">
            <PageHeader
                title="Platform"
                description="Module packs, plans, and commercial overrides for this deployment."
            />
            <DensePageMobileNotice surface="Admin platform" />

            <AdminPlatformOverview
                configDraft={admin.configDraft}
                planCount={plans.length}
                flagCount={flags.length}
                templateCount={templates.length}
            />

            <PlatformConfigPanel
                configDraft={admin.configDraft}
                moduleCatalog={admin.moduleCatalog}
                packOptions={admin.packOptions}
                activePackSummary={admin.activePackSummary}
                isSaving={admin.saveConfigMutation.isPending}
                saveError={admin.saveConfigMutation.error}
                onConfigDraftChange={admin.setConfigDraft}
                onSave={() =>
                    admin.saveConfigMutation.mutate({
                        app_name: admin.configDraft.app_name,
                        core_domain_singular: admin.configDraft.core_domain_singular,
                        core_domain_plural: admin.configDraft.core_domain_plural,
                        module_pack: admin.configDraft.module_pack,
                        module_overrides: admin.configDraft.module_states,
                        mfa_enabled: admin.configDraft.mfa_enabled,
                    })
                }
            />

            <PlansPanel
                plans={plans}
                planDrafts={admin.planDrafts}
                newPlan={admin.newPlan}
                isCreating={admin.createPlanMutation.isPending}
                savingPlanId={
                    admin.updatePlanMutation.isPending ? (admin.updatePlanMutation.variables?.id ?? null) : null
                }
                onNewPlanChange={admin.setNewPlan}
                onPlanDraftChange={(planId, updater) =>
                    admin.setPlanDrafts((current) => ({
                        ...current,
                        [planId]: updater(current[planId]),
                    }))
                }
                onCreatePlan={() =>
                    admin.createPlanMutation.mutate({
                        code: admin.newPlan.code.trim(),
                        name: admin.newPlan.name.trim(),
                        description: admin.newPlan.description.trim() || undefined,
                        price_cents: Number(admin.newPlan.price_cents),
                        interval: admin.newPlan.interval.trim(),
                        is_default: admin.newPlan.is_default,
                        features: admin.newPlan.features.split(",").map((item) => item.trim()).filter(Boolean),
                    })
                }
                onSavePlan={(planId, draft) => admin.updatePlanMutation.mutate({ id: planId, draft })}
            />

            <FeatureFlagsPanel
                flags={flags}
                flagDrafts={admin.flagDrafts}
                newFlag={admin.newFlag}
                isCreating={admin.createFlagMutation.isPending}
                savingFlagId={
                    admin.updateFlagMutation.isPending ? (admin.updateFlagMutation.variables?.id ?? null) : null
                }
                onNewFlagChange={admin.setNewFlag}
                onFlagDraftChange={(flagId, updater) =>
                    admin.setFlagDrafts((current) => ({
                        ...current,
                        [flagId]: updater(current[flagId]),
                    }))
                }
                onCreateFlag={() =>
                    admin.createFlagMutation.mutate({
                        key: admin.newFlag.key.trim(),
                        name: admin.newFlag.name.trim(),
                        description: admin.newFlag.description.trim() || undefined,
                        module_key: admin.newFlag.module_key.trim() || null,
                        is_enabled: admin.newFlag.is_enabled,
                        rollout_percentage: Number(admin.newFlag.rollout_percentage),
                    })
                }
                onSaveFlag={(flagId, draft) => admin.updateFlagMutation.mutate({ id: flagId, draft })}
            />

            <EmailTemplatesPanel
                templates={templates}
                templateDrafts={admin.templateDrafts}
                newTemplate={admin.newTemplate}
                isCreating={admin.createTemplateMutation.isPending}
                savingTemplateId={
                    admin.updateTemplateMutation.isPending
                        ? (admin.updateTemplateMutation.variables?.id ?? null)
                        : null
                }
                onNewTemplateChange={admin.setNewTemplate}
                onTemplateDraftChange={(templateId, updater) =>
                    admin.setTemplateDrafts((current) => ({
                        ...current,
                        [templateId]: updater(current[templateId]),
                    }))
                }
                onCreateTemplate={() =>
                    admin.createTemplateMutation.mutate({
                        key: admin.newTemplate.key.trim(),
                        name: admin.newTemplate.name.trim(),
                        subject_template: admin.newTemplate.subject_template,
                        html_template: admin.newTemplate.html_template,
                        text_template: admin.newTemplate.text_template || null,
                        is_active: admin.newTemplate.is_active,
                    })
                }
                onSaveTemplate={(templateId, draft) => admin.updateTemplateMutation.mutate({ id: templateId, draft })}
            />
        </PageShell>
    );
}
