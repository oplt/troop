import { Stack } from "@mui/material";

import type { EmailTemplate } from "../../../api/platform";
import { SectionCard } from "../../../components/ui/SectionCard";
import type { TemplateDraft } from "../draftBuilders";
import type { NewTemplateDraft } from "../types";
import { EmailTemplateCreateForm, EmailTemplateEditForm } from "./EmailTemplateEditor";

type EmailTemplatesPanelProps = {
    templates: EmailTemplate[];
    templateDrafts: Record<string, TemplateDraft>;
    newTemplate: NewTemplateDraft;
    isCreating: boolean;
    savingTemplateId: string | null;
    onNewTemplateChange: (updater: (current: NewTemplateDraft) => NewTemplateDraft) => void;
    onTemplateDraftChange: (templateId: string, updater: (current: TemplateDraft) => TemplateDraft) => void;
    onCreateTemplate: () => void;
    onSaveTemplate: (templateId: string, draft: TemplateDraft) => void;
};

export function EmailTemplatesPanel({
    templates,
    templateDrafts,
    newTemplate,
    isCreating,
    savingTemplateId,
    onNewTemplateChange,
    onTemplateDraftChange,
    onCreateTemplate,
    onSaveTemplate,
}: EmailTemplatesPanelProps) {
    return (
        <SectionCard
            title="Email templates"
            description="Create and update reusable transactional email templates."
        >
            <Stack spacing={2.5}>
                <EmailTemplateCreateForm
                    newTemplate={newTemplate}
                    isCreating={isCreating}
                    onNewTemplateChange={onNewTemplateChange}
                    onCreate={onCreateTemplate}
                />
                <Stack spacing={1.5}>
                    {templates.map((template) => {
                        const draft = templateDrafts[template.id];
                        return (
                            <EmailTemplateEditForm
                                key={template.id}
                                template={template}
                                draft={draft}
                                isSaving={savingTemplateId === template.id}
                                onDraftChange={(updater) => onTemplateDraftChange(template.id, updater)}
                                onSave={() => onSaveTemplate(template.id, draft)}
                            />
                        );
                    })}
                </Stack>
            </Stack>
        </SectionCard>
    );
}
