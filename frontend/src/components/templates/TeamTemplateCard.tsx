import { Button, Chip, Paper, Stack, Typography } from "@mui/material";
import { DeleteOutline as RemoveIcon } from "@mui/icons-material";

import type { StaticTeamTemplate } from "./types";

type TeamTemplateCardProps = {
    template: StaticTeamTemplate;
    agentTemplates: Array<{ slug: string; name: string }>;
    onDragEnd: () => void;
    onDropAgentTemplate: (teamTemplateId: string, templateSlug: string) => void;
    onRemoveAgentTemplate: (teamTemplateId: string, templateSlug: string) => void;
    activeAgentTemplateSlug: string | null;
    onRemove: () => void;
};

export function TeamTemplateCard({
    template,
    agentTemplates,
    onDragEnd,
    onDropAgentTemplate,
    onRemoveAgentTemplate,
    activeAgentTemplateSlug,
    onRemove,
}: TeamTemplateCardProps) {
    return (
        <Paper
            onDragOver={(event) => {
                if (!activeAgentTemplateSlug) {
                    return;
                }
                event.preventDefault();
                event.dataTransfer.dropEffect = "move";
            }}
            onDrop={(event) => {
                const payload = event.dataTransfer.getData("text/plain");
                const droppedTemplateSlug = payload.startsWith("agent-template:") ? payload.replace("agent-template:", "") : activeAgentTemplateSlug;
                if (!droppedTemplateSlug) {
                    return;
                }
                event.preventDefault();
                onDropAgentTemplate(template.id, droppedTemplateSlug);
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
                borderColor: activeAgentTemplateSlug ? "primary.main" : "divider",
                bgcolor: activeAgentTemplateSlug ? "action.hover" : "background.paper",
            }}
        >
            <Stack direction="row" justifyContent="space-between" spacing={1}>
                <Typography variant="subtitle2">{template.name}</Typography>
                <Chip label={template.outcome} size="small" color="primary" variant="outlined" />
            </Stack>
            <Typography variant="body2" color="text.secondary" sx={{ flex: 1 }}>
                {template.description}
            </Typography>
            <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                {template.roles.map((role) => (
                    <Chip key={`${template.id}-${role}`} label={role} size="small" variant="outlined" />
                ))}
                {template.tools.slice(0, 2).map((tool) => (
                    <Chip key={`${template.id}-${tool}`} label={tool} size="small" color="secondary" variant="outlined" />
                ))}
            </Stack>
            <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                {agentTemplates.map((agentTemplate) => (
                    <Chip
                        key={`${template.id}-${agentTemplate.slug}`}
                        label={agentTemplate.name}
                        size="small"
                        color="success"
                        variant="outlined"
                        onDelete={() => onRemoveAgentTemplate(template.id, agentTemplate.slug)}
                    />
                ))}
            </Stack>
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                <Button size="small" variant="text">
                    {template.autonomy}
                </Button>
                <Typography variant="caption" color={activeAgentTemplateSlug ? "primary.main" : "text.secondary"} sx={{ alignSelf: "center" }}>
                    Drop agent templates here
                </Typography>
            </Stack>
            <Stack direction="row" justifyContent="flex-end" sx={{ mt: "auto" }}>
                <Button size="small" color="error" startIcon={<RemoveIcon />} onClick={onRemove}>
                    Remove
                </Button>
            </Stack>
        </Paper>
    );
}
