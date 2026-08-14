import { Box, Button, Chip, Stack, Typography } from "@mui/material";

import type { AiPromptTemplate, AiPromptVersion } from "../../../api/ai";
import { SectionCard } from "../../../components/ui/SectionCard";
import { borderedPanelSx } from "../styles";
import type { AiProvider, VersionFormState } from "../types";
import { PromptVersionForm } from "./PromptVersionForm";

type PromptVersionsPanelProps = {
    templates: AiPromptTemplate[];
    providers: AiProvider[];
    versions: AiPromptVersion[];
    selectedTemplateId: string;
    versionForm: VersionFormState;
    isCreating: boolean;
    onSelectedTemplateChange: (templateId: string) => void;
    onVersionFormChange: (updater: (current: VersionFormState) => VersionFormState) => void;
    onCreateVersion: () => void;
    onActivateVersion: (versionId: string) => void;
    onTogglePublish: (versionId: string, isPublished: boolean) => void;
};

export function PromptVersionsPanel({
    templates,
    providers,
    versions,
    selectedTemplateId,
    versionForm,
    isCreating,
    onSelectedTemplateChange,
    onVersionFormChange,
    onCreateVersion,
    onActivateVersion,
    onTogglePublish,
}: PromptVersionsPanelProps) {
    return (
        <SectionCard
            title="Version builder"
            description="Attach deployable versions to a prompt template with model selection, rollout state, and provider pricing."
        >
            <Stack spacing={2}>
                <PromptVersionForm
                    templates={templates}
                    providers={providers}
                    selectedTemplateId={selectedTemplateId}
                    versionForm={versionForm}
                    isCreating={isCreating}
                    onSelectedTemplateChange={onSelectedTemplateChange}
                    onVersionFormChange={onVersionFormChange}
                    onCreateVersion={onCreateVersion}
                />
                {versions.length > 0 && (
                    <Stack spacing={1.25}>
                        {versions.map((version) => (
                            <Box key={version.id} sx={borderedPanelSx}>
                                <Stack spacing={1}>
                                    <Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" spacing={1}>
                                        <Typography variant="subtitle2">
                                            v{version.version_number} • {version.provider_key}/{version.model_name}
                                        </Typography>
                                        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                                            {version.is_published && (
                                                <Chip label="published" size="small" color="success" variant="outlined" />
                                            )}
                                            <Chip
                                                label={`${version.rollout_percentage}% rollout`}
                                                size="small"
                                                variant="outlined"
                                            />
                                        </Stack>
                                    </Stack>
                                    <Typography variant="body2" color="text.secondary">
                                        {version.user_prompt_template.slice(0, 180)}
                                    </Typography>
                                    <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
                                        <Button size="small" variant="outlined" onClick={() => onActivateVersion(version.id)}>
                                            Set active
                                        </Button>
                                        <Button
                                            size="small"
                                            variant="outlined"
                                            onClick={() => onTogglePublish(version.id, !version.is_published)}
                                        >
                                            {version.is_published ? "Unpublish" : "Publish"}
                                        </Button>
                                    </Stack>
                                </Stack>
                            </Box>
                        ))}
                    </Stack>
                )}
            </Stack>
        </SectionCard>
    );
}
