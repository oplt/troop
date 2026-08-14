import { Box, Button, FormControlLabel, Stack, Switch, TextField, Typography } from "@mui/material";

import type { EmailTemplate } from "../../../api/platform";
import type { TemplateDraft } from "../draftBuilders";
import { borderedPanelSx } from "../styles";
import type { NewTemplateDraft } from "../types";

type EmailTemplateCreateFormProps = {
    newTemplate: NewTemplateDraft;
    isCreating: boolean;
    onNewTemplateChange: (updater: (current: NewTemplateDraft) => NewTemplateDraft) => void;
    onCreate: () => void;
};

export function EmailTemplateCreateForm({
    newTemplate,
    isCreating,
    onNewTemplateChange,
    onCreate,
}: EmailTemplateCreateFormProps) {
    return (
        <Box sx={borderedPanelSx}>
            <Stack spacing={1.5}>
                <Typography variant="subtitle2">Create template</Typography>
                <Box
                    sx={{
                        display: "grid",
                        gap: 1.5,
                        gridTemplateColumns: { xs: "1fr", md: "repeat(2, minmax(0, 1fr))" },
                    }}
                >
                    <TextField
                        label="Key"
                        value={newTemplate.key}
                        onChange={(event) =>
                            onNewTemplateChange((current) => ({ ...current, key: event.target.value }))
                        }
                        fullWidth
                    />
                    <TextField
                        label="Name"
                        value={newTemplate.name}
                        onChange={(event) =>
                            onNewTemplateChange((current) => ({ ...current, name: event.target.value }))
                        }
                        fullWidth
                    />
                </Box>
                <TextField
                    label="Subject"
                    value={newTemplate.subject_template}
                    onChange={(event) =>
                        onNewTemplateChange((current) => ({ ...current, subject_template: event.target.value }))
                    }
                    fullWidth
                />
                <TextField
                    label="HTML body"
                    value={newTemplate.html_template}
                    onChange={(event) =>
                        onNewTemplateChange((current) => ({ ...current, html_template: event.target.value }))
                    }
                    fullWidth
                    multiline
                    minRows={4}
                />
                <TextField
                    label="Text body"
                    value={newTemplate.text_template}
                    onChange={(event) =>
                        onNewTemplateChange((current) => ({ ...current, text_template: event.target.value }))
                    }
                    fullWidth
                    multiline
                    minRows={3}
                />
                <FormControlLabel
                    control={
                        <Switch
                            checked={newTemplate.is_active}
                            onChange={(event) =>
                                onNewTemplateChange((current) => ({ ...current, is_active: event.target.checked }))
                            }
                        />
                    }
                    label="Active"
                />
                <Button
                    variant="contained"
                    disabled={isCreating || newTemplate.key.trim().length < 2}
                    onClick={onCreate}
                >
                    {isCreating ? "Creating..." : "Create template"}
                </Button>
            </Stack>
        </Box>
    );
}

type EmailTemplateEditFormProps = {
    template: EmailTemplate;
    draft: TemplateDraft;
    isSaving: boolean;
    onDraftChange: (updater: (current: TemplateDraft) => TemplateDraft) => void;
    onSave: () => void;
};

export function EmailTemplateEditForm({
    template,
    draft,
    isSaving,
    onDraftChange,
    onSave,
}: EmailTemplateEditFormProps) {
    return (
        <Box sx={borderedPanelSx}>
            <Stack spacing={1.5}>
                <Typography variant="subtitle2">{template.key}</Typography>
                <TextField
                    label="Name"
                    value={draft.name}
                    onChange={(event) => onDraftChange((current) => ({ ...current, name: event.target.value }))}
                    fullWidth
                />
                <TextField
                    label="Subject"
                    value={draft.subject_template}
                    onChange={(event) =>
                        onDraftChange((current) => ({ ...current, subject_template: event.target.value }))
                    }
                    fullWidth
                />
                <TextField
                    label="HTML body"
                    value={draft.html_template}
                    onChange={(event) =>
                        onDraftChange((current) => ({ ...current, html_template: event.target.value }))
                    }
                    fullWidth
                    multiline
                    minRows={4}
                />
                <TextField
                    label="Text body"
                    value={draft.text_template}
                    onChange={(event) =>
                        onDraftChange((current) => ({ ...current, text_template: event.target.value }))
                    }
                    fullWidth
                    multiline
                    minRows={3}
                />
                <FormControlLabel
                    control={
                        <Switch
                            checked={draft.is_active}
                            onChange={(event) =>
                                onDraftChange((current) => ({ ...current, is_active: event.target.checked }))
                            }
                        />
                    }
                    label="Active"
                />
                <Button variant="outlined" disabled={isSaving} onClick={onSave}>
                    {isSaving ? "Saving..." : "Save template"}
                </Button>
            </Stack>
        </Box>
    );
}
