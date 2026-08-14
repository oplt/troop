import type {
    EmailTemplate,
    FeatureFlag,
    PlatformConfig,
    SubscriptionPlan,
} from "../../api/platform";

export type PlanDraft = {
    name: string;
    description: string;
    price_cents: string;
    interval: string;
    is_active: boolean;
    is_default: boolean;
    features: string;
};

export type FlagDraft = {
    name: string;
    description: string;
    module_key: string;
    is_enabled: boolean;
    rollout_percentage: string;
};

export type TemplateDraft = {
    name: string;
    subject_template: string;
    html_template: string;
    text_template: string;
    is_active: boolean;
};

export function buildConfigDraft(configData: PlatformConfig) {
    return {
        app_name: configData.app_name,
        core_domain_singular: configData.core_domain_singular,
        core_domain_plural: configData.core_domain_plural,
        module_pack: configData.module_pack,
        module_states: Object.fromEntries(
            configData.module_catalog.map((item) => [item.key, item.enabled]),
        ),
        mfa_enabled: configData.mfa_enabled,
    };
}

export function buildPlanDrafts(plans: SubscriptionPlan[]) {
    return Object.fromEntries(
        plans.map((plan) => [
            plan.id,
            {
                name: plan.name,
                description: plan.description ?? "",
                price_cents: String(plan.price_cents),
                interval: plan.interval,
                is_active: plan.is_active,
                is_default: plan.is_default,
                features: plan.features.join(", "),
            },
        ]),
    ) as Record<string, PlanDraft>;
}

export function buildFlagDrafts(flags: FeatureFlag[]) {
    return Object.fromEntries(
        flags.map((flag) => [
            flag.id,
            {
                name: flag.name,
                description: flag.description ?? "",
                module_key: flag.module_key ?? "",
                is_enabled: flag.is_enabled,
                rollout_percentage: String(flag.rollout_percentage),
            },
        ]),
    ) as Record<string, FlagDraft>;
}

export function buildTemplateDrafts(templates: EmailTemplate[]) {
    return Object.fromEntries(
        templates.map((template) => [
            template.id,
            {
                name: template.name,
                subject_template: template.subject_template,
                html_template: template.html_template,
                text_template: template.text_template ?? "",
                is_active: template.is_active,
            },
        ]),
    ) as Record<string, TemplateDraft>;
}
