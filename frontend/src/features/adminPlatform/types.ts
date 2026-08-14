export type ConfigDraft = {
    app_name: string;
    core_domain_singular: string;
    core_domain_plural: string;
    module_pack: string;
    module_states: Record<string, boolean>;
    mfa_enabled: boolean;
};

export type NewPlanDraft = {
    code: string;
    name: string;
    description: string;
    price_cents: string;
    interval: string;
    is_default: boolean;
    features: string;
};

export type NewFlagDraft = {
    key: string;
    name: string;
    description: string;
    module_key: string;
    is_enabled: boolean;
    rollout_percentage: string;
};

export type NewTemplateDraft = {
    key: string;
    name: string;
    subject_template: string;
    html_template: string;
    text_template: string;
    is_active: boolean;
};
