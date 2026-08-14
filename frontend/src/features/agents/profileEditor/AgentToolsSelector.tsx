import { Chip, Stack, Typography } from "@mui/material";

import type { ToolSpec } from "../../../api/orchestration";
import { TOOL_ALIASES, type AgentProfileForm } from "./types";

type AgentToolsSelectorProps = {
    form: AgentProfileForm;
    tools: ToolSpec[];
    onChange: <K extends keyof AgentProfileForm>(key: K, value: AgentProfileForm[K]) => void;
};

export function AgentToolsSelector({ form, tools, onChange }: AgentToolsSelectorProps) {
    return (
        <>
            <Typography variant="subtitle2">Allowed tools</Typography>
            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                {tools.map((tool) => {
                    const name = TOOL_ALIASES[tool.name] ?? tool.name;
                    const selected = form.allowed_tools.includes(name);
                    return (
                        <Chip
                            key={tool.name}
                            label={name}
                            color={selected ? "primary" : "default"}
                            variant={selected ? "filled" : "outlined"}
                            onClick={() =>
                                onChange(
                                    "allowed_tools",
                                    selected
                                        ? form.allowed_tools.filter((item) => item !== name)
                                        : [...form.allowed_tools, name],
                                )
                            }
                        />
                    );
                })}
            </Stack>
        </>
    );
}
