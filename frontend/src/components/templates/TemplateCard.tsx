import { Button, Chip, Paper, Stack, Typography } from "@mui/material";
import { DeleteOutline as RemoveIcon } from "@mui/icons-material";

import type { AgentTemplate } from "../../api/orchestration";

type TemplateCardProps = {
    template: AgentTemplate;
    onOpenDetails: (templateSlug: string) => void;
    onLoadTemplate: (templateSlug: string) => void;
    onCreateFromTemplate: (templateSlug: string) => void;
    onCopyTemplateContract: (template: AgentTemplate) => void;
    onRemove: (templateSlug: string) => void;
    onRemoveSkill: (templateSlug: string, skillSlug: string) => void;
    onDragStart: (templateSlug: string) => void;
    onDragEnd: () => void;
    onDropSkill: (templateSlug: string, skillSlug: string) => void;
    activeSkillSlug: string | null;
    compact?: boolean;
};

export function TemplateCard({
    template,
    onOpenDetails,
    onLoadTemplate,
    onCreateFromTemplate,
    onCopyTemplateContract,
    onRemove,
    onRemoveSkill,
    onDragStart,
    onDragEnd,
    onDropSkill,
    activeSkillSlug,
    compact = false,
}: TemplateCardProps) {
    return (
        <Paper
            draggable
            onDragStart={(event) => {
                event.dataTransfer.setData("text/plain", `agent-template:${template.slug}`);
                event.dataTransfer.effectAllowed = "move";
                onDragStart(template.slug);
            }}
            onDragEnd={onDragEnd}
            onDragOver={(event) => {
                if (!activeSkillSlug) {
                    return;
                }
                event.preventDefault();
                event.dataTransfer.dropEffect = "copy";
            }}
            onDrop={(event) => {
                const payload = event.dataTransfer.getData("text/plain");
                const droppedSkillSlug = payload.startsWith("skill:") ? payload.replace("skill:", "") : activeSkillSlug;
                if (!droppedSkillSlug) {
                    return;
                }
                event.preventDefault();
                onDropSkill(template.slug, droppedSkillSlug);
                onDragEnd();
            }}
            sx={{
                p: 2,
                borderRadius: 3,
                display: "flex",
                flexDirection: "column",
                gap: 1,
                height: "100%",
                border: "1px solid",
                borderColor: activeSkillSlug ? "primary.main" : "divider",
                bgcolor: activeSkillSlug ? "action.hover" : "background.paper",
            }}
        >
            <Stack direction="row" justifyContent="space-between" spacing={1}>
                <Typography variant="subtitle2">{template.name}</Typography>
                <Chip label={template.role} size="small" variant="outlined" />
            </Stack>
            <Typography variant="body2" color="text.secondary" sx={{ flex: 1 }}>
                {template.description || "No description provided."}
            </Typography>
            <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                {template.skills.slice(0, compact ? 2 : 3).map((skill) => (
                    <Chip
                        key={`${template.slug}-${skill}`}
                        label={skill}
                        size="small"
                        color="secondary"
                        variant="outlined"
                        onDelete={() => onRemoveSkill(template.slug, skill)}
                    />
                ))}
                {template.tags.slice(0, compact ? 2 : 3).map((tag) => (
                    <Chip key={`${template.slug}-${tag}`} label={tag} size="small" variant="outlined" />
                ))}
            </Stack>
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                    <Button size="small" variant="text" onClick={() => onOpenDetails(template.slug)}>
                        Preview
                    </Button>
                    <Button size="small" variant="outlined" onClick={() => onLoadTemplate(template.slug)}>
                        Edit
                </Button>
                <Button size="small" variant="contained" onClick={() => onCreateFromTemplate(template.slug)}>
                    Use
                </Button>
                <Button size="small" variant="text" onClick={() => onCopyTemplateContract(template)}>
                    Copy
                </Button>
            </Stack>
            {activeSkillSlug ? (
                <Typography variant="caption" color="primary.main">
                    Drop skill here
                </Typography>
            ) : null}
            <Stack direction="row" justifyContent="flex-end" sx={{ mt: "auto" }}>
                <Button
                    size="small"
                    color="error"
                    startIcon={<RemoveIcon />}
                    onClick={() => onRemove(template.slug)}
                >
                    Remove
                </Button>
            </Stack>
        </Paper>
    );
}
