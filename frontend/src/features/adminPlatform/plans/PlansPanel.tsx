import { Stack } from "@mui/material";

import type { SubscriptionPlan } from "../../../api/platform";
import { SectionCard } from "../../../components/ui/SectionCard";
import type { PlanDraft } from "../draftBuilders";
import type { NewPlanDraft } from "../types";
import { PlanCreateForm, PlanEditForm } from "./PlanForm";

type PlansPanelProps = {
    plans: SubscriptionPlan[];
    planDrafts: Record<string, PlanDraft>;
    newPlan: NewPlanDraft;
    isCreating: boolean;
    savingPlanId: string | null;
    onNewPlanChange: (updater: (current: NewPlanDraft) => NewPlanDraft) => void;
    onPlanDraftChange: (planId: string, updater: (current: PlanDraft) => PlanDraft) => void;
    onCreatePlan: () => void;
    onSavePlan: (planId: string, draft: PlanDraft) => void;
};

export function PlansPanel({
    plans,
    planDrafts,
    newPlan,
    isCreating,
    savingPlanId,
    onNewPlanChange,
    onPlanDraftChange,
    onCreatePlan,
    onSavePlan,
}: PlansPanelProps) {
    return (
        <SectionCard title="Subscription plans" description="Create new commercial tiers and tune existing plans.">
            <Stack spacing={2.5}>
                <PlanCreateForm
                    newPlan={newPlan}
                    isCreating={isCreating}
                    onNewPlanChange={onNewPlanChange}
                    onCreate={onCreatePlan}
                />
                <Stack spacing={1.5}>
                    {plans.map((plan) => {
                        const draft = planDrafts[plan.id];
                        return (
                            <PlanEditForm
                                key={plan.id}
                                plan={plan}
                                draft={draft}
                                isSaving={savingPlanId === plan.id}
                                onDraftChange={(updater) => onPlanDraftChange(plan.id, updater)}
                                onSave={() => onSavePlan(plan.id, draft)}
                            />
                        );
                    })}
                </Stack>
            </Stack>
        </SectionCard>
    );
}
