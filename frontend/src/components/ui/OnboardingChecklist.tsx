import { Button, Checkbox, FormControlLabel, Paper, Stack, Typography } from "@mui/material";
import { useNavigate } from "react-router-dom";

export type OnboardingStep = {
    id: string;
    label: string;
    done: boolean;
    path: string;
    cta: string;
};

type OnboardingChecklistProps = {
    steps: OnboardingStep[];
    title?: string;
    description?: string;
};

/** Post-login empty-org guided checklist. */
export function OnboardingChecklist({
    steps,
    title = "Get your workspace ready",
    description = "Three steps unlock the daily loop: org context, a project, then integrations when you need them.",
}: OnboardingChecklistProps) {
    const navigate = useNavigate();
    const next = steps.find((step) => !step.done) ?? steps[steps.length - 1];

    return (
        <Paper
            variant="outlined"
            sx={{ p: 2.5, borderRadius: 1, borderColor: "primary.main", borderWidth: 1 }}
            role="region"
            aria-label="Onboarding checklist"
        >
            <Stack spacing={2}>
                <BoxHeader title={title} description={description} />
                <Stack spacing={0.5}>
                    {steps.map((step) => (
                        <FormControlLabel
                            key={step.id}
                            control={<Checkbox checked={step.done} disableRipple tabIndex={-1} />}
                            label={step.label}
                            sx={{
                                m: 0,
                                opacity: step.done ? 0.7 : 1,
                                "& .MuiFormControlLabel-label": { typography: "body2" },
                            }}
                        />
                    ))}
                </Stack>
                {next ? (
                    <Button variant="contained" onClick={() => navigate(next.path)} sx={{ alignSelf: "flex-start" }}>
                        {next.done ? "Review setup" : next.cta}
                    </Button>
                ) : null}
            </Stack>
        </Paper>
    );
}

function BoxHeader({ title, description }: { title: string; description: string }) {
    return (
        <Stack spacing={0.5}>
            <Typography variant="h6">{title}</Typography>
            <Typography variant="body2" color="text.secondary">
                {description}
            </Typography>
        </Stack>
    );
}
