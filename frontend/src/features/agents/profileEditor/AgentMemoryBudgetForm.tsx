import { Box, MenuItem, TextField } from "@mui/material";

import { MEMORIES, OUTPUTS } from "../contractOptions";
import type { AgentProfileForm } from "./types";

type AgentMemoryBudgetFormProps = {
    form: AgentProfileForm;
    onChange: <K extends keyof AgentProfileForm>(key: K, value: AgentProfileForm[K]) => void;
};

export function AgentMemoryBudgetForm({ form, onChange }: AgentMemoryBudgetFormProps) {
    return (
        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "repeat(2, 1fr)" }, gap: 2 }}>
            <TextField
                select
                label="Memory scope"
                size="small"
                value={form.memory_scope}
                onChange={(event) => onChange("memory_scope", event.target.value)}
            >
                {MEMORIES.map((value) => (
                    <MenuItem key={value} value={value}>
                        {value}
                    </MenuItem>
                ))}
            </TextField>
            <TextField
                select
                label="Output schema"
                size="small"
                value={form.output_format}
                onChange={(event) => onChange("output_format", event.target.value)}
            >
                {OUTPUTS.map((value) => (
                    <MenuItem key={value} value={value}>
                        {value}
                    </MenuItem>
                ))}
            </TextField>
            <TextField
                label="Token budget"
                size="small"
                type="number"
                value={form.token_budget}
                onChange={(event) => onChange("token_budget", event.target.value)}
            />
            <TextField
                label="Budget cap (USD)"
                size="small"
                type="number"
                value={form.budget_cap_usd}
                onChange={(event) => onChange("budget_cap_usd", event.target.value)}
                inputProps={{ min: 0, step: 0.01 }}
            />
            <TextField
                label="Time budget (seconds)"
                size="small"
                type="number"
                value={form.time_budget_seconds}
                onChange={(event) => onChange("time_budget_seconds", event.target.value)}
            />
            <TextField
                label="Retry budget"
                size="small"
                type="number"
                value={form.retry_budget}
                onChange={(event) => onChange("retry_budget", event.target.value)}
            />
        </Box>
    );
}
