import { PsychologyAlt as PromptIcon } from "@mui/icons-material";
import { Box, Button, Chip, Stack, Typography } from "@mui/material";

import type { AiPromptTemplate } from "../../../api/ai";
import { EmptyState } from "../../../components/ui/EmptyState";
import { SectionCard } from "../../../components/ui/SectionCard";
import { borderedPanelSx } from "../styles";
import type { TemplateFormState } from "../types";
import { PromptTemplateForm } from "./PromptTemplateForm";

type PromptTemplatesPanelProps = {
    templates: AiPromptTemplate[];
    templateForm: TemplateFormState;
    selectedTemplateId: string;
    isCreating: boolean;
    onTemplateFormChange: (updater: (current: TemplateFormState) => TemplateFormState) => void;
    onCreateTemplate: () => void;
    onSelectTemplate: (templateId: string) => void;
};

export function PromptTemplatesPanel({
    templates,
    templateForm,
    selectedTemplateId,
    isCreating,
    onTemplateFormChange,
    onCreateTemplate,
    onSelectTemplate,
}: PromptTemplatesPanelProps) {
    return (
        <SectionCard
            title="Prompt library"
            description="Create reusable prompt templates and publish versioned variants with rollout and pricing metadata."
        >
            <Stack spacing={2}>
                <PromptTemplateForm
                    templateForm={templateForm}
                    isCreating={isCreating}
                    onTemplateFormChange={onTemplateFormChange}
                    onCreateTemplate={onCreateTemplate}
                />
                {templates.length > 0 ? (
                    <Stack spacing={1.25}>
                        {templates.map((template) => (
                            <Box key={template.id} sx={borderedPanelSx}>
                                <Stack spacing={1}>
                                    <Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" spacing={1}>
                                        <Box>
                                            <Typography variant="subtitle1">{template.name}</Typography>
                                            <Typography variant="body2" color="text.secondary">
                                                {template.key}
                                            </Typography>
                                        </Box>
                                        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                                            {template.is_active && (
                                                <Chip label="active" size="small" color="success" variant="outlined" />
                                            )}
                                            {template.active_version_id && (
                                                <Chip label="version pinned" size="small" variant="outlined" />
                                            )}
                                        </Stack>
                                    </Stack>
                                    {template.description && (
                                        <Typography variant="body2" color="text.secondary">
                                            {template.description}
                                        </Typography>
                                    )}
                                    <Button variant="outlined" size="small" onClick={() => onSelectTemplate(template.id)}>
                                        {selectedTemplateId === template.id ? "Selected" : "Manage versions"}
                                    </Button>
                                </Stack>
                            </Box>
                        ))}
                    </Stack>
                ) : (
                    <EmptyState
                        icon={<PromptIcon />}
                        title="No prompts yet"
                        description="Create your first prompt template to start building reusable AI behaviors."
                    />
                )}
            </Stack>
        </SectionCard>
    );
}
