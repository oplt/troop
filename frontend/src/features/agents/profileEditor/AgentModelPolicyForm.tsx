import { Box, MenuItem, TextField } from "@mui/material";

import type { AgentProfileForm } from "./types";

type AgentModelPolicyFormProps = {
    form: AgentProfileForm;
    onChange: <K extends keyof AgentProfileForm>(key: K, value: AgentProfileForm[K]) => void;
};

export function AgentModelPolicyForm({ form, onChange }: AgentModelPolicyFormProps) {
    return (
        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "repeat(2, minmax(0, 1fr))" }, gap: 2 }}>
            <TextField
                label="Provider"
                size="small"
                value={form.provider}
                onChange={(event) => onChange("provider", event.target.value)}
            />
            <TextField
                label="Primary model"
                size="small"
                value={form.model}
                onChange={(event) => onChange("model", event.target.value)}
            />
            <TextField
                label="Fallback model"
                size="small"
                value={form.fallback_model}
                onChange={(event) => onChange("fallback_model", event.target.value)}
            />
            <TextField
                label="Max context tokens"
                size="small"
                type="number"
                value={form.max_context}
                onChange={(event) => onChange("max_context", event.target.value)}
            />
            <TextField
                label="Max output tokens"
                size="small"
                type="number"
                value={form.max_tokens}
                onChange={(event) => onChange("max_tokens", event.target.value)}
                inputProps={{ min: 128 }}
            />
            <TextField
                label="Temperature"
                size="small"
                type="number"
                value={form.temperature}
                onChange={(event) => onChange("temperature", event.target.value)}
                inputProps={{ min: 0, max: 2, step: 0.1 }}
            />
            <TextField
                label="Reasoning effort"
                size="small"
                value={form.reasoning_effort}
                onChange={(event) => {
                    onChange("reasoning_effort", event.target.value);
                    onChange("reasoning_level", event.target.value);
                }}
                helperText="Provider-specific effort such as low, medium, or high."
            />
            <TextField
                label="Timeout (seconds)"
                size="small"
                type="number"
                value={form.timeout_seconds}
                onChange={(event) => onChange("timeout_seconds", event.target.value)}
                inputProps={{ min: 10, max: 14400 }}
            />
            <TextField
                label="Retry count"
                size="small"
                type="number"
                value={form.retry_count}
                onChange={(event) => onChange("retry_count", event.target.value)}
                inputProps={{ min: 0, max: 10 }}
            />
            <TextField
                select
                label="Tool calling"
                size="small"
                value={String(form.tool_calling)}
                onChange={(event) => onChange("tool_calling", event.target.value === "true")}
            >
                <MenuItem value="true">Enabled</MenuItem>
                <MenuItem value="false">Disabled</MenuItem>
            </TextField>
            <TextField
                select
                label="Structured output"
                size="small"
                value={String(form.structured_output)}
                onChange={(event) => onChange("structured_output", event.target.value === "true")}
            >
                <MenuItem value="true">Enabled (JSON)</MenuItem>
                <MenuItem value="false">Disabled (text)</MenuItem>
            </TextField>
        </Box>
    );
}
