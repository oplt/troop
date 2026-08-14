import { Button, Stack, TextField } from "@mui/material";

import type { TemplateFormState } from "../types";

type PromptTemplateFormProps = {
    templateForm: TemplateFormState;
    isCreating: boolean;
    onTemplateFormChange: (updater: (current: TemplateFormState) => TemplateFormState) => void;
    onCreateTemplate: () => void;
};

export function PromptTemplateForm({
    templateForm,
    isCreating,
    onTemplateFormChange,
    onCreateTemplate,
}: PromptTemplateFormProps) {
    return (
        <Stack spacing={2} sx={{ "& > .MuiButton-root": { alignSelf: "flex-start" } }}>
            <Stack direction={{ xs: "column", md: "row" }} spacing={1.5}>
                <TextField
                    label="Template key"
                    value={templateForm.key}
                    onChange={(event) => onTemplateFormChange((current) => ({ ...current, key: event.target.value }))}
                    fullWidth
                />
                <TextField
                    label="Name"
                    value={templateForm.name}
                    onChange={(event) => onTemplateFormChange((current) => ({ ...current, name: event.target.value }))}
                    fullWidth
                />
            </Stack>
            <TextField
                label="Description"
                value={templateForm.description}
                onChange={(event) =>
                    onTemplateFormChange((current) => ({ ...current, description: event.target.value }))
                }
                fullWidth
                multiline
                minRows={2}
            />
            <Button
                variant="contained"
                onClick={onCreateTemplate}
                disabled={isCreating || !templateForm.key.trim() || !templateForm.name.trim()}
            >
                {isCreating ? "Creating..." : "Create prompt template"}
            </Button>
        </Stack>
    );
}
