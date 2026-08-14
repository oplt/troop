import { Box, MenuItem, TextField } from "@mui/material";

import { PERMISSIONS } from "../contractOptions";
import type { AgentProfileForm } from "./types";

type AgentIdentityFormProps = {
    form: AgentProfileForm;
    onChange: <K extends keyof AgentProfileForm>(key: K, value: AgentProfileForm[K]) => void;
};

export function AgentIdentityForm({ form, onChange }: AgentIdentityFormProps) {
    return (
        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" }, gap: 2 }}>
            <TextField
                label="Name"
                size="small"
                value={form.name}
                onChange={(event) => onChange("name", event.target.value)}
            />
            <TextField
                label="Slug"
                size="small"
                value={form.slug}
                onChange={(event) => onChange("slug", event.target.value)}
            />
            <TextField
                label="Role"
                size="small"
                value={form.role}
                onChange={(event) => onChange("role", event.target.value)}
            />
            <TextField
                select
                label="Permission level"
                size="small"
                value={form.permissions}
                onChange={(event) => onChange("permissions", event.target.value)}
            >
                {PERMISSIONS.map((value) => (
                    <MenuItem key={value} value={value}>
                        {value}
                    </MenuItem>
                ))}
            </TextField>
        </Box>
    );
}
