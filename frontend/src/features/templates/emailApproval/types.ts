export const EMAIL_APPROVAL_FLAGSHIP_SLUG = "email-reply-telegram-approval";

export type TemplateStepActor = "system" | "deterministic" | "ai" | "human";

export type TemplatePackStep = {
    id: string;
    label: string;
    actor: TemplateStepActor;
    description: string;
};

export type EmailApprovalTemplatePack = {
    flagship: boolean;
    title: string;
    summary: string;
    requirements: {
        connectors: string[];
        optional_connectors: string[];
        skill_slugs: string[];
    };
    steps: TemplatePackStep[];
};

export type EmailApprovalBootstrapResult = {
    status: string;
    kind: string;
    slug: string;
    workflow_id: string;
    published: boolean;
    configuration_required: string[];
    project_id: string;
    task_id: string;
    agent_id: string;
    approval_channel: string;
    template_pack?: EmailApprovalTemplatePack;
};

export const TEMPLATE_STEP_ACTOR_LABELS: Record<TemplateStepActor, string> = {
    system: "System",
    deterministic: "Deterministic",
    ai: "AI",
    human: "Human",
};

export const TEMPLATE_STEP_ACTOR_COLORS: Record<
    TemplateStepActor,
    "default" | "info" | "secondary" | "warning" | "success"
> = {
    system: "default",
    deterministic: "info",
    ai: "secondary",
    human: "warning",
};

export function isGmailConnected(status: string | undefined): boolean {
    return Boolean(status && ["connected", "active", "healthy"].includes(status));
}

export function isTelegramConnected(status: string | undefined): boolean {
    return Boolean(status && ["connected", "active", "healthy", "linked"].includes(status));
}

export function isEmailApprovalTemplatePack(value: unknown): value is EmailApprovalTemplatePack {
    if (!value || typeof value !== "object" || Array.isArray(value)) return false;
    const pack = value as Partial<EmailApprovalTemplatePack>;
    return (
        typeof pack.flagship === "boolean" &&
        typeof pack.title === "string" &&
        typeof pack.summary === "string" &&
        Array.isArray(pack.steps) &&
        Boolean(pack.requirements) &&
        Array.isArray(pack.requirements?.connectors) &&
        Array.isArray(pack.requirements?.optional_connectors) &&
        Array.isArray(pack.requirements?.skill_slugs)
    );
}

export function findFlagshipWorkflow<T extends { slug?: unknown; template_pack?: unknown }>(
    workflows: T[],
): T | undefined {
    return workflows.find(
        (item) =>
            item.slug === EMAIL_APPROVAL_FLAGSHIP_SLUG ||
            (isEmailApprovalTemplatePack(item.template_pack) && item.template_pack.flagship),
    );
}
