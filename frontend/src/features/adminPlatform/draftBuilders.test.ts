import { describe, expect, it } from "vitest";

import type { EmailTemplate, FeatureFlag, PlatformConfig, SubscriptionPlan } from "../../api/platform";
import {
    buildConfigDraft,
    buildFlagDrafts,
    buildPlanDrafts,
    buildTemplateDrafts,
} from "./draftBuilders";

const platformConfig: PlatformConfig = {
    app_name: "Troop",
    core_domain_singular: "Project",
    core_domain_plural: "Projects",
    module_pack: "full_platform",
    enabled_modules: ["orchestration"],
    module_catalog: [
        {
            key: "orchestration",
            label: "Orchestration",
            description: "Runs and tasks",
            user_visible: true,
            enabled: true,
        },
        {
            key: "ai",
            label: "AI Studio",
            description: "Prompts and runs",
            user_visible: true,
            enabled: false,
        },
    ],
    available_module_packs: [],
    mfa_enabled: true,
    module_overrides: {},
};

describe("adminPlatform draftBuilders", () => {
    it("buildConfigDraft maps module catalog to module_states", () => {
        expect(buildConfigDraft(platformConfig)).toEqual({
            app_name: "Troop",
            core_domain_singular: "Project",
            core_domain_plural: "Projects",
            module_pack: "full_platform",
            module_states: {
                orchestration: true,
                ai: false,
            },
            mfa_enabled: true,
        });
    });

    it("buildPlanDrafts serializes price and features", () => {
        const plans: SubscriptionPlan[] = [
            {
                id: "plan-1",
                code: "starter",
                name: "Starter",
                description: "Entry tier",
                price_cents: 9900,
                interval: "month",
                is_active: true,
                is_default: true,
                features: ["orchestration", "ai"],
                created_at: "2026-01-01T00:00:00Z",
                updated_at: "2026-01-01T00:00:00Z",
            },
        ];

        expect(buildPlanDrafts(plans)["plan-1"]).toEqual({
            name: "Starter",
            description: "Entry tier",
            price_cents: "9900",
            interval: "month",
            is_active: true,
            is_default: true,
            features: "orchestration, ai",
        });
    });

    it("buildFlagDrafts and buildTemplateDrafts preserve editable fields", () => {
        const flags: FeatureFlag[] = [
            {
                id: "flag-1",
                key: "beta_ui",
                name: "Beta UI",
                description: "New shell",
                module_key: "platform",
                is_enabled: true,
                rollout_percentage: 25,
                updated_at: "2026-01-01T00:00:00Z",
            },
        ];
        const templates: EmailTemplate[] = [
            {
                id: "tmpl-1",
                key: "verify_email",
                name: "Verify email",
                subject_template: "Verify your account",
                html_template: "<p>Hello</p>",
                text_template: "Hello",
                is_active: true,
                updated_at: "2026-01-01T00:00:00Z",
            },
        ];

        expect(buildFlagDrafts(flags)["flag-1"].rollout_percentage).toBe("25");
        expect(buildTemplateDrafts(templates)["tmpl-1"].subject_template).toBe("Verify your account");
    });
});
