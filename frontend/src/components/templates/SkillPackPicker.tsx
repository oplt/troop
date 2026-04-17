import { MenuItem, Paper, Stack, TextField, Typography } from "@mui/material";

import type { SkillPack } from "../../api/orchestration";
import type { TemplateBuilderFormState } from "./types";

type SkillPackPickerProps = {
    form: TemplateBuilderFormState;
    setForm: React.Dispatch<React.SetStateAction<TemplateBuilderFormState>>;
    skills: SkillPack[];
};

export function SkillPackPicker({ form, setForm, skills }: SkillPackPickerProps) {
    return (
        <Stack spacing={2}>
            <TextField
                select
                SelectProps={{ multiple: true }}
                label="Skill packs"
                value={form.skills}
                onChange={(event) =>
                    setForm((current) => ({
                        ...current,
                        skills: typeof event.target.value === "string" ? [event.target.value] : event.target.value,
                    }))
                }
                helperText="Reusable behavior packs for capabilities, tools, tags."
            >
                {skills.map((skill) => (
                    <MenuItem key={skill.slug} value={skill.slug}>
                        {skill.name}
                    </MenuItem>
                ))}
            </TextField>
            <Stack spacing={1}>
                {skills.filter((skill) => form.skills.includes(skill.slug)).map((skill) => (
                    <Paper key={skill.slug} sx={{ p: 1.5, borderRadius: 3 }}>
                        <Typography variant="subtitle2">{skill.name}</Typography>
                        <Typography variant="body2" color="text.secondary">
                            {skill.description}
                        </Typography>
                    </Paper>
                ))}
            </Stack>
        </Stack>
    );
}
