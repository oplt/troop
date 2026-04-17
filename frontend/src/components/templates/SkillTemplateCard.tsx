import { Button, Chip, Paper, Stack, Typography } from "@mui/material";
import { DeleteOutline as RemoveIcon } from "@mui/icons-material";

import type { SkillPack } from "../../api/orchestration";

type SkillTemplateCardProps = {
    skill: SkillPack;
    onAdd: (skill: SkillPack) => void;
    onEdit: (skill: SkillPack) => void;
    onDragStart: (skillSlug: string) => void;
    onDragEnd: () => void;
    onRemove: () => void;
};

export function SkillTemplateCard({
    skill,
    onAdd,
    onEdit,
    onDragStart,
    onDragEnd,
    onRemove,
}: SkillTemplateCardProps) {
    return (
        <Paper
            draggable
            onDragStart={(event) => {
                event.dataTransfer.setData("text/plain", `skill:${skill.slug}`);
                event.dataTransfer.effectAllowed = "copy";
                onDragStart(skill.slug);
            }}
            onDragEnd={onDragEnd}
            sx={{ p: 2, borderRadius: 3, display: "flex", flexDirection: "column", gap: 1, height: "100%" }}
        >
            <Stack direction="row" justifyContent="space-between" spacing={1}>
                <Typography variant="subtitle2">{skill.name}</Typography>
                <Chip label="Skill" size="small" color="info" variant="outlined" />
            </Stack>
            <Typography variant="body2" color="text.secondary" sx={{ flex: 1 }}>
                {skill.description || "No description provided."}
            </Typography>
            <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                {skill.capabilities.slice(0, 3).map((item) => (
                    <Chip key={`${skill.slug}-${item}`} label={item} size="small" variant="outlined" />
                ))}
                {skill.tags.slice(0, 3).map((item) => (
                    <Chip key={`${skill.slug}-tag-${item}`} label={item} size="small" color="secondary" variant="outlined" />
                ))}
            </Stack>
            <Stack direction="row" justifyContent="space-between" spacing={1} sx={{ mt: "auto" }}>
                <Button size="small" variant="contained" onClick={() => onAdd(skill)}>
                    Duplicate
                </Button>
                <Button size="small" variant="outlined" onClick={() => onEdit(skill)}>
                    Edit
                </Button>
                <Button size="small" color="error" startIcon={<RemoveIcon />} onClick={onRemove}>
                    Remove
                </Button>
            </Stack>
        </Paper>
    );
}
