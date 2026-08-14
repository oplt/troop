import { Alert, Divider, Paper, Stack, Typography } from "@mui/material";

import type { AgentValidationState } from "./types";

type AgentValidationPanelProps = {
    validation: AgentValidationState | null;
    dryRun: string;
};

export function AgentValidationPanel({ validation, dryRun }: AgentValidationPanelProps) {
    return (
        <Stack spacing={1.5}>
            <Typography color="text.secondary">
                Lint checks markdown, tools, models, budgets, filters, output format, memory scope, permissions, and
                escalation before activation.
            </Typography>
            {validation && (
                <>
                    <Alert severity={validation.ready ? "success" : "warning"}>
                        {validation.ready ? "Activation-ready" : "Needs attention"}
                    </Alert>
                    {validation.errors.map((item) => (
                        <Alert key={item} severity="error">
                            {item}
                        </Alert>
                    ))}
                    {validation.warnings.map((item) => (
                        <Alert key={item} severity="warning">
                            {item}
                        </Alert>
                    ))}
                </>
            )}
            {dryRun && (
                <>
                    <Divider />
                    <Typography variant="subtitle2">Dry-run output</Typography>
                    <Paper variant="outlined" sx={{ p: 2, whiteSpace: "pre-wrap", fontFamily: "monospace", fontSize: 13 }}>
                        {dryRun}
                    </Paper>
                </>
            )}
        </Stack>
    );
}
