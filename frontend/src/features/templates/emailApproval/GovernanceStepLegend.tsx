import { Chip, Stack, Typography } from "@mui/material";

import {
    TEMPLATE_STEP_ACTOR_COLORS,
    TEMPLATE_STEP_ACTOR_LABELS,
    type EmailApprovalTemplatePack,
    type TemplateStepActor,
} from "./types";

type GovernanceStepLegendProps = {
    pack: EmailApprovalTemplatePack;
    compact?: boolean;
};

export function GovernanceStepLegend({ pack, compact = false }: GovernanceStepLegendProps) {
    const actorCounts = pack.steps.reduce<Record<TemplateStepActor, number>>(
        (acc, step) => {
            acc[step.actor] += 1;
            return acc;
        },
        { system: 0, deterministic: 0, ai: 0, human: 0 },
    );

    return (
        <Stack spacing={compact ? 1 : 1.5}>
            {!compact && (
                <Typography variant="body2" color="text.secondary">
                    {pack.summary}
                </Typography>
            )}
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                {(Object.keys(actorCounts) as TemplateStepActor[]).map((actor) => (
                    <Chip
                        key={actor}
                        size="small"
                        color={TEMPLATE_STEP_ACTOR_COLORS[actor]}
                        label={`${TEMPLATE_STEP_ACTOR_LABELS[actor]} · ${actorCounts[actor]}`}
                    />
                ))}
            </Stack>
            {!compact && (
                <Stack spacing={1}>
                    {pack.steps.map((step) => (
                        <Stack key={step.id} spacing={0.25}>
                            <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                                <Typography variant="subtitle2">{step.label}</Typography>
                                <Chip
                                    size="small"
                                    variant="outlined"
                                    color={TEMPLATE_STEP_ACTOR_COLORS[step.actor]}
                                    label={TEMPLATE_STEP_ACTOR_LABELS[step.actor]}
                                />
                            </Stack>
                            <Typography variant="body2" color="text.secondary">
                                {step.description}
                            </Typography>
                        </Stack>
                    ))}
                </Stack>
            )}
        </Stack>
    );
}
