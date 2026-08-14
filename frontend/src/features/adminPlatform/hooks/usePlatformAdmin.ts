import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import {
    createAdminEmailTemplate,
    createAdminFeatureFlag,
    createAdminPlan,
    updateAdminEmailTemplate,
    updateAdminFeatureFlag,
    updateAdminPlan,
    updatePlatformConfig,
    type EmailTemplate,
    type FeatureFlag,
    type PlatformConfig,
    type SubscriptionPlan,
} from "../../../api/platform";
import { useSnackbar } from "../../../app/snackbarContext";
import {
    buildConfigDraft,
    buildFlagDrafts,
    buildPlanDrafts,
    buildTemplateDrafts,
    type FlagDraft,
    type PlanDraft,
    type TemplateDraft,
} from "../draftBuilders";
import type { ConfigDraft, NewFlagDraft, NewPlanDraft, NewTemplateDraft } from "../types";

const EMPTY_NEW_PLAN: NewPlanDraft = {
    code: "",
    name: "",
    description: "",
    price_cents: "0",
    interval: "month",
    is_default: false,
    features: "",
};

const EMPTY_NEW_FLAG: NewFlagDraft = {
    key: "",
    name: "",
    description: "",
    module_key: "",
    is_enabled: false,
    rollout_percentage: "100",
};

const EMPTY_NEW_TEMPLATE: NewTemplateDraft = {
    key: "",
    name: "",
    subject_template: "",
    html_template: "",
    text_template: "",
    is_active: true,
};

type UsePlatformAdminArgs = {
    configData: PlatformConfig;
    plans: SubscriptionPlan[];
    flags: FeatureFlag[];
    templates: EmailTemplate[];
};

export function usePlatformAdmin({ configData, plans, flags, templates }: UsePlatformAdminArgs) {
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();
    const [configDraft, setConfigDraft] = useState<ConfigDraft>(() => buildConfigDraft(configData));
    const [planDrafts, setPlanDrafts] = useState<Record<string, PlanDraft>>(() => buildPlanDrafts(plans));
    const [flagDrafts, setFlagDrafts] = useState<Record<string, FlagDraft>>(() => buildFlagDrafts(flags));
    const [templateDrafts, setTemplateDrafts] = useState<Record<string, TemplateDraft>>(() =>
        buildTemplateDrafts(templates),
    );
    const [newPlan, setNewPlan] = useState<NewPlanDraft>(EMPTY_NEW_PLAN);
    const [newFlag, setNewFlag] = useState<NewFlagDraft>(EMPTY_NEW_FLAG);
    const [newTemplate, setNewTemplate] = useState<NewTemplateDraft>(EMPTY_NEW_TEMPLATE);

    const moduleCatalog = configData.module_catalog;
    const packOptions = configData.available_module_packs;
    const activePackSummary = packOptions.find((pack) => pack.key === configDraft.module_pack);

    const saveConfigMutation = useMutation({
        mutationFn: updatePlatformConfig,
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["platform"] });
            showToast({ message: "Platform configuration updated.", severity: "success" });
        },
    });
    const createPlanMutation = useMutation({
        mutationFn: createAdminPlan,
        onSuccess: async () => {
            setNewPlan(EMPTY_NEW_PLAN);
            await queryClient.invalidateQueries({ queryKey: ["platform", "admin", "plans"] });
            showToast({ message: "Plan created.", severity: "success" });
        },
    });
    const updatePlanMutation = useMutation({
        mutationFn: ({ id, draft }: { id: string; draft: PlanDraft }) =>
            updateAdminPlan(id, {
                name: draft.name,
                description: draft.description || null,
                price_cents: Number(draft.price_cents),
                interval: draft.interval,
                is_active: draft.is_active,
                is_default: draft.is_default,
                features: draft.features.split(",").map((item) => item.trim()).filter(Boolean),
            }),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["platform", "admin", "plans"] });
            showToast({ message: "Plan updated.", severity: "success" });
        },
    });
    const createFlagMutation = useMutation({
        mutationFn: createAdminFeatureFlag,
        onSuccess: async () => {
            setNewFlag(EMPTY_NEW_FLAG);
            await queryClient.invalidateQueries({ queryKey: ["platform", "admin", "feature-flags"] });
            showToast({ message: "Feature flag created.", severity: "success" });
        },
    });
    const updateFlagMutation = useMutation({
        mutationFn: ({ id, draft }: { id: string; draft: FlagDraft }) =>
            updateAdminFeatureFlag(id, {
                name: draft.name,
                description: draft.description || null,
                module_key: draft.module_key || null,
                is_enabled: draft.is_enabled,
                rollout_percentage: Number(draft.rollout_percentage),
            }),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["platform", "admin", "feature-flags"] });
            showToast({ message: "Feature flag updated.", severity: "success" });
        },
    });
    const createTemplateMutation = useMutation({
        mutationFn: createAdminEmailTemplate,
        onSuccess: async () => {
            setNewTemplate(EMPTY_NEW_TEMPLATE);
            await queryClient.invalidateQueries({ queryKey: ["platform", "admin", "email-templates"] });
            showToast({ message: "Email template created.", severity: "success" });
        },
    });
    const updateTemplateMutation = useMutation({
        mutationFn: ({ id, draft }: { id: string; draft: TemplateDraft }) =>
            updateAdminEmailTemplate(id, {
                name: draft.name,
                subject_template: draft.subject_template,
                html_template: draft.html_template,
                text_template: draft.text_template || null,
                is_active: draft.is_active,
            }),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["platform", "admin", "email-templates"] });
            showToast({ message: "Email template updated.", severity: "success" });
        },
    });

    return {
        configDraft,
        setConfigDraft,
        planDrafts,
        setPlanDrafts,
        flagDrafts,
        setFlagDrafts,
        templateDrafts,
        setTemplateDrafts,
        newPlan,
        setNewPlan,
        newFlag,
        setNewFlag,
        newTemplate,
        setNewTemplate,
        moduleCatalog,
        packOptions,
        activePackSummary,
        saveConfigMutation,
        createPlanMutation,
        updatePlanMutation,
        createFlagMutation,
        updateFlagMutation,
        createTemplateMutation,
        updateTemplateMutation,
    };
}
