import { Button, FormControlLabel, MenuItem, Stack, Switch, TextField } from "@mui/material";

import type { AiPromptTemplate } from "../../../api/ai";
import type { AiProvider, VersionFormState } from "../types";

type PromptVersionFormProps = {
    templates: AiPromptTemplate[];
    providers: AiProvider[];
    selectedTemplateId: string;
    versionForm: VersionFormState;
    isCreating: boolean;
    onSelectedTemplateChange: (templateId: string) => void;
    onVersionFormChange: (updater: (current: VersionFormState) => VersionFormState) => void;
    onCreateVersion: () => void;
};

export function PromptVersionForm({
    templates,
    providers,
    selectedTemplateId,
    versionForm,
    isCreating,
    onSelectedTemplateChange,
    onVersionFormChange,
    onCreateVersion,
}: PromptVersionFormProps) {
    return (
        <Stack spacing={2} sx={{ "& > .MuiButton-root": { alignSelf: "flex-start" } }}>
            <TextField
                select
                label="Selected template"
                value={selectedTemplateId}
                onChange={(event) => onSelectedTemplateChange(event.target.value)}
                fullWidth
            >
                {templates.map((template) => (
                    <MenuItem key={template.id} value={template.id}>
                        {template.name}
                    </MenuItem>
                ))}
            </TextField>
            <TextField
                select
                label="Provider"
                value={versionForm.provider_key}
                onChange={(event) =>
                    onVersionFormChange((current) => ({ ...current, provider_key: event.target.value }))
                }
                fullWidth
            >
                {providers.map((provider) => (
                    <MenuItem key={provider.key} value={provider.key}>
                        {provider.label}
                    </MenuItem>
                ))}
            </TextField>
            <TextField
                label="Model name"
                value={versionForm.model_name}
                onChange={(event) =>
                    onVersionFormChange((current) => ({ ...current, model_name: event.target.value }))
                }
                fullWidth
            />
            <TextField
                label="System prompt"
                value={versionForm.system_prompt}
                onChange={(event) =>
                    onVersionFormChange((current) => ({ ...current, system_prompt: event.target.value }))
                }
                fullWidth
                multiline
                minRows={3}
            />
            <TextField
                label="User prompt template"
                value={versionForm.user_prompt_template}
                onChange={(event) =>
                    onVersionFormChange((current) => ({ ...current, user_prompt_template: event.target.value }))
                }
                fullWidth
                multiline
                minRows={5}
            />
            <TextField
                label="Variable names (comma separated)"
                value={versionForm.variable_names}
                onChange={(event) =>
                    onVersionFormChange((current) => ({ ...current, variable_names: event.target.value }))
                }
                fullWidth
            />
            <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}>
                <TextField
                    select
                    label="Response format"
                    value={versionForm.response_format}
                    onChange={(event) =>
                        onVersionFormChange((current) => ({
                            ...current,
                            response_format: event.target.value as "text" | "json",
                        }))
                    }
                    fullWidth
                >
                    <MenuItem value="text">Text</MenuItem>
                    <MenuItem value="json">JSON</MenuItem>
                </TextField>
                <TextField
                    label="Temperature"
                    value={versionForm.temperature}
                    onChange={(event) =>
                        onVersionFormChange((current) => ({ ...current, temperature: event.target.value }))
                    }
                    fullWidth
                />
            </Stack>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}>
                <TextField
                    label="Rollout %"
                    value={versionForm.rollout_percentage}
                    onChange={(event) =>
                        onVersionFormChange((current) => ({ ...current, rollout_percentage: event.target.value }))
                    }
                    fullWidth
                />
                <FormControlLabel
                    control={
                        <Switch
                            checked={versionForm.is_published}
                            onChange={(event) =>
                                onVersionFormChange((current) => ({
                                    ...current,
                                    is_published: event.target.checked,
                                }))
                            }
                        />
                    }
                    label="Published"
                />
            </Stack>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}>
                <TextField
                    label="Input cost / million"
                    value={versionForm.input_cost_per_million}
                    onChange={(event) =>
                        onVersionFormChange((current) => ({
                            ...current,
                            input_cost_per_million: event.target.value,
                        }))
                    }
                    fullWidth
                />
                <TextField
                    label="Output cost / million"
                    value={versionForm.output_cost_per_million}
                    onChange={(event) =>
                        onVersionFormChange((current) => ({
                            ...current,
                            output_cost_per_million: event.target.value,
                        }))
                    }
                    fullWidth
                />
            </Stack>
            <Button
                variant="contained"
                disabled={
                    isCreating ||
                    !selectedTemplateId ||
                    !versionForm.model_name.trim() ||
                    !versionForm.user_prompt_template.trim()
                }
                onClick={onCreateVersion}
            >
                {isCreating ? "Saving..." : "Create prompt version"}
            </Button>
        </Stack>
    );
}
