import { Box, Button, FormControlLabel, Stack, Switch, TextField, Typography } from "@mui/material";

import type { FeatureFlag } from "../../../api/platform";
import type { FlagDraft } from "../draftBuilders";
import { borderedPanelSx } from "../styles";
import type { NewFlagDraft } from "../types";

type FeatureFlagCreateFormProps = {
    newFlag: NewFlagDraft;
    isCreating: boolean;
    onNewFlagChange: (updater: (current: NewFlagDraft) => NewFlagDraft) => void;
    onCreate: () => void;
};

export function FeatureFlagCreateForm({
    newFlag,
    isCreating,
    onNewFlagChange,
    onCreate,
}: FeatureFlagCreateFormProps) {
    return (
        <Box sx={borderedPanelSx}>
            <Stack spacing={1.5}>
                <Typography variant="subtitle2">Create feature flag</Typography>
                <Box
                    sx={{
                        display: "grid",
                        gap: 1.5,
                        gridTemplateColumns: { xs: "1fr", md: "repeat(2, minmax(0, 1fr))" },
                    }}
                >
                    <TextField
                        label="Key"
                        value={newFlag.key}
                        onChange={(event) => onNewFlagChange((current) => ({ ...current, key: event.target.value }))}
                        fullWidth
                    />
                    <TextField
                        label="Name"
                        value={newFlag.name}
                        onChange={(event) => onNewFlagChange((current) => ({ ...current, name: event.target.value }))}
                        fullWidth
                    />
                    <TextField
                        label="Module key"
                        value={newFlag.module_key}
                        onChange={(event) =>
                            onNewFlagChange((current) => ({ ...current, module_key: event.target.value }))
                        }
                        fullWidth
                    />
                    <TextField
                        label="Rollout %"
                        value={newFlag.rollout_percentage}
                        onChange={(event) =>
                            onNewFlagChange((current) => ({ ...current, rollout_percentage: event.target.value }))
                        }
                        fullWidth
                    />
                </Box>
                <TextField
                    label="Description"
                    value={newFlag.description}
                    onChange={(event) =>
                        onNewFlagChange((current) => ({ ...current, description: event.target.value }))
                    }
                    fullWidth
                />
                <FormControlLabel
                    control={
                        <Switch
                            checked={newFlag.is_enabled}
                            onChange={(event) =>
                                onNewFlagChange((current) => ({ ...current, is_enabled: event.target.checked }))
                            }
                        />
                    }
                    label="Enabled"
                />
                <Button
                    variant="contained"
                    disabled={isCreating || newFlag.key.trim().length < 2}
                    onClick={onCreate}
                >
                    {isCreating ? "Creating..." : "Create flag"}
                </Button>
            </Stack>
        </Box>
    );
}

type FeatureFlagEditFormProps = {
    flag: FeatureFlag;
    draft: FlagDraft;
    isSaving: boolean;
    onDraftChange: (updater: (current: FlagDraft) => FlagDraft) => void;
    onSave: () => void;
};

export function FeatureFlagEditForm({ flag, draft, isSaving, onDraftChange, onSave }: FeatureFlagEditFormProps) {
    return (
        <Box sx={borderedPanelSx}>
            <Stack spacing={1.5}>
                <Typography variant="subtitle2">{flag.key}</Typography>
                <Box
                    sx={{
                        display: "grid",
                        gap: 1.5,
                        gridTemplateColumns: { xs: "1fr", md: "repeat(2, minmax(0, 1fr))" },
                    }}
                >
                    <TextField
                        label="Name"
                        value={draft.name}
                        onChange={(event) => onDraftChange((current) => ({ ...current, name: event.target.value }))}
                        fullWidth
                    />
                    <TextField
                        label="Module key"
                        value={draft.module_key}
                        onChange={(event) =>
                            onDraftChange((current) => ({ ...current, module_key: event.target.value }))
                        }
                        fullWidth
                    />
                    <TextField
                        label="Rollout %"
                        value={draft.rollout_percentage}
                        onChange={(event) =>
                            onDraftChange((current) => ({ ...current, rollout_percentage: event.target.value }))
                        }
                        fullWidth
                    />
                </Box>
                <TextField
                    label="Description"
                    value={draft.description}
                    onChange={(event) =>
                        onDraftChange((current) => ({ ...current, description: event.target.value }))
                    }
                    fullWidth
                />
                <FormControlLabel
                    control={
                        <Switch
                            checked={draft.is_enabled}
                            onChange={(event) =>
                                onDraftChange((current) => ({ ...current, is_enabled: event.target.checked }))
                            }
                        />
                    }
                    label="Enabled"
                />
                <Button variant="outlined" disabled={isSaving} onClick={onSave}>
                    {isSaving ? "Saving..." : "Save flag"}
                </Button>
            </Stack>
        </Box>
    );
}
