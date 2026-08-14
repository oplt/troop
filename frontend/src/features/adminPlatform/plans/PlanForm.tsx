import { Box, Button, Chip, FormControlLabel, Stack, Switch, TextField, Typography } from "@mui/material";

import type { SubscriptionPlan } from "../../../api/platform";
import type { PlanDraft } from "../draftBuilders";
import { borderedPanelSx } from "../styles";
import type { NewPlanDraft } from "../types";

type PlanCreateFormProps = {
    newPlan: NewPlanDraft;
    isCreating: boolean;
    onNewPlanChange: (updater: (current: NewPlanDraft) => NewPlanDraft) => void;
    onCreate: () => void;
};

export function PlanCreateForm({ newPlan, isCreating, onNewPlanChange, onCreate }: PlanCreateFormProps) {
    return (
        <Box sx={borderedPanelSx}>
            <Stack spacing={1.5}>
                <Typography variant="subtitle2">Create plan</Typography>
                <Box
                    sx={{
                        display: "grid",
                        gap: 1.5,
                        gridTemplateColumns: { xs: "1fr", md: "repeat(2, minmax(0, 1fr))" },
                    }}
                >
                    <TextField
                        label="Code"
                        value={newPlan.code}
                        onChange={(event) => onNewPlanChange((current) => ({ ...current, code: event.target.value }))}
                        fullWidth
                    />
                    <TextField
                        label="Name"
                        value={newPlan.name}
                        onChange={(event) => onNewPlanChange((current) => ({ ...current, name: event.target.value }))}
                        fullWidth
                    />
                    <TextField
                        label="Price (cents)"
                        value={newPlan.price_cents}
                        onChange={(event) =>
                            onNewPlanChange((current) => ({ ...current, price_cents: event.target.value }))
                        }
                        fullWidth
                    />
                    <TextField
                        label="Interval"
                        value={newPlan.interval}
                        onChange={(event) =>
                            onNewPlanChange((current) => ({ ...current, interval: event.target.value }))
                        }
                        fullWidth
                    />
                </Box>
                <TextField
                    label="Description"
                    value={newPlan.description}
                    onChange={(event) =>
                        onNewPlanChange((current) => ({ ...current, description: event.target.value }))
                    }
                    fullWidth
                />
                <TextField
                    label="Features"
                    value={newPlan.features}
                    onChange={(event) =>
                        onNewPlanChange((current) => ({ ...current, features: event.target.value }))
                    }
                    helperText="Comma-separated feature labels"
                    fullWidth
                />
                <FormControlLabel
                    control={
                        <Switch
                            checked={newPlan.is_default}
                            onChange={(event) =>
                                onNewPlanChange((current) => ({ ...current, is_default: event.target.checked }))
                            }
                        />
                    }
                    label="Default plan"
                />
                <Button
                    variant="contained"
                    disabled={isCreating || newPlan.code.trim().length < 2}
                    onClick={onCreate}
                >
                    {isCreating ? "Creating..." : "Create plan"}
                </Button>
            </Stack>
        </Box>
    );
}

type PlanEditFormProps = {
    plan: SubscriptionPlan;
    draft: PlanDraft;
    isSaving: boolean;
    onDraftChange: (updater: (current: PlanDraft) => PlanDraft) => void;
    onSave: () => void;
};

export function PlanEditForm({ plan, draft, isSaving, onDraftChange, onSave }: PlanEditFormProps) {
    return (
        <Box sx={borderedPanelSx}>
            <Stack spacing={1.5}>
                <Stack direction="row" spacing={1} alignItems="center">
                    <Typography variant="subtitle2">{plan.code}</Typography>
                    {plan.is_default ? <Chip label="Default" size="small" color="primary" /> : null}
                </Stack>
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
                        label="Price (cents)"
                        value={draft.price_cents}
                        onChange={(event) =>
                            onDraftChange((current) => ({ ...current, price_cents: event.target.value }))
                        }
                        fullWidth
                    />
                    <TextField
                        label="Interval"
                        value={draft.interval}
                        onChange={(event) =>
                            onDraftChange((current) => ({ ...current, interval: event.target.value }))
                        }
                        fullWidth
                    />
                    <TextField
                        label="Features"
                        value={draft.features}
                        onChange={(event) =>
                            onDraftChange((current) => ({ ...current, features: event.target.value }))
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
                <Stack direction="row" spacing={2}>
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
                    <FormControlLabel
                        control={
                            <Switch
                                checked={draft.is_default}
                                onChange={(event) =>
                                    onDraftChange((current) => ({ ...current, is_default: event.target.checked }))
                                }
                            />
                        }
                        label="Default"
                    />
                </Stack>
                <Button variant="outlined" disabled={isSaving} onClick={onSave}>
                    {isSaving ? "Saving..." : "Save plan"}
                </Button>
            </Stack>
        </Box>
    );
}
