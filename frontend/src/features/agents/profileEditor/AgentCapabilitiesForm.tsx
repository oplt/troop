import { TextField } from "@mui/material";

import type { AgentProfileForm } from "./types";

type AgentCapabilitiesFormProps = {
    form: AgentProfileForm;
    onChange: <K extends keyof AgentProfileForm>(key: K, value: AgentProfileForm[K]) => void;
};

export function AgentCapabilitiesForm({ form, onChange }: AgentCapabilitiesFormProps) {
    return (
        <>
            <TextField
                label="Description"
                size="small"
                value={form.description}
                onChange={(event) => onChange("description", event.target.value)}
                multiline
                minRows={2}
            />
            <TextField
                label="Capabilities"
                size="small"
                value={form.capabilities}
                onChange={(event) => onChange("capabilities", event.target.value)}
                helperText="Comma-separated capabilities"
            />
            <TextField
                label="Escalation path"
                size="small"
                value={form.escalation_path}
                onChange={(event) => onChange("escalation_path", event.target.value)}
            />
            <TextField
                label="Task filters"
                size="small"
                value={form.task_filters}
                onChange={(event) => onChange("task_filters", event.target.value)}
                helperText="Comma-separated tags or regular expressions"
            />
        </>
    );
}
