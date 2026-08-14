import { Stack } from "@mui/material";

import type { FeatureFlag } from "../../../api/platform";
import { SectionCard } from "../../../components/ui/SectionCard";
import type { FlagDraft } from "../draftBuilders";
import type { NewFlagDraft } from "../types";
import { FeatureFlagCreateForm, FeatureFlagEditForm } from "./FeatureFlagForm";

type FeatureFlagsPanelProps = {
    flags: FeatureFlag[];
    flagDrafts: Record<string, FlagDraft>;
    newFlag: NewFlagDraft;
    isCreating: boolean;
    savingFlagId: string | null;
    onNewFlagChange: (updater: (current: NewFlagDraft) => NewFlagDraft) => void;
    onFlagDraftChange: (flagId: string, updater: (current: FlagDraft) => FlagDraft) => void;
    onCreateFlag: () => void;
    onSaveFlag: (flagId: string, draft: FlagDraft) => void;
};

export function FeatureFlagsPanel({
    flags,
    flagDrafts,
    newFlag,
    isCreating,
    savingFlagId,
    onNewFlagChange,
    onFlagDraftChange,
    onCreateFlag,
    onSaveFlag,
}: FeatureFlagsPanelProps) {
    return (
        <SectionCard title="Feature flags" description="Create rollout controls and tune existing flags.">
            <Stack spacing={2.5}>
                <FeatureFlagCreateForm
                    newFlag={newFlag}
                    isCreating={isCreating}
                    onNewFlagChange={onNewFlagChange}
                    onCreate={onCreateFlag}
                />
                <Stack spacing={1.5}>
                    {flags.map((flag) => {
                        const draft = flagDrafts[flag.id];
                        return (
                            <FeatureFlagEditForm
                                key={flag.id}
                                flag={flag}
                                draft={draft}
                                isSaving={savingFlagId === flag.id}
                                onDraftChange={(updater) => onFlagDraftChange(flag.id, updater)}
                                onSave={() => onSaveFlag(flag.id, draft)}
                            />
                        );
                    })}
                </Stack>
            </Stack>
        </SectionCard>
    );
}
