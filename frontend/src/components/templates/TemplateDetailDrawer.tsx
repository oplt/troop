import { Button, Chip, Divider, Drawer, Stack, Typography } from "@mui/material";

import type { AgentTemplate } from "../../api/orchestration";

type TemplateDetailDrawerProps = {
    open: boolean;
    template: AgentTemplate | null;
    onClose: () => void;
    onLoadTemplate: (templateSlug: string) => void;
    onCreateFromTemplate: (templateSlug: string) => void;
    onCopyTemplateContract: (template: AgentTemplate) => void;
};

export function TemplateDetailDrawer({
    open,
    template,
    onClose,
    onLoadTemplate,
    onCreateFromTemplate,
    onCopyTemplateContract,
}: TemplateDetailDrawerProps) {
    return (
        <Drawer anchor="right" open={open} onClose={onClose}>
            <Stack spacing={2} sx={{ width: { xs: "100vw", sm: 420 }, p: 3 }}>
                {template ? (
                    <>
                        <div>
                            <Typography variant="h6">{template.name}</Typography>
                            <Typography variant="body2" color="text.secondary">
                                {template.slug} • {template.role}
                            </Typography>
                        </div>
                        <Typography variant="body2">{template.description || "No description provided."}</Typography>
                        <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                            {template.skills.map((item) => (
                                <Chip key={`${template.slug}-skill-${item}`} label={item} size="small" color="secondary" variant="outlined" />
                            ))}
                            {template.tags.map((item) => (
                                <Chip key={`${template.slug}-tag-${item}`} label={item} size="small" variant="outlined" />
                            ))}
                        </Stack>
                        <Divider />
                        <div>
                            <Typography variant="subtitle2" sx={{ mb: 1 }}>Capabilities</Typography>
                            <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                                {template.capabilities.map((item) => (
                                    <Chip key={`${template.slug}-cap-${item}`} label={item} size="small" />
                                ))}
                            </Stack>
                        </div>
                        <div>
                            <Typography variant="subtitle2" sx={{ mb: 1 }}>Tools</Typography>
                            <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                                {template.allowed_tools.map((item) => (
                                    <Chip key={`${template.slug}-tool-${item}`} label={item} size="small" />
                                ))}
                            </Stack>
                        </div>
                        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                            <Button variant="contained" onClick={() => onCreateFromTemplate(template.slug)}>
                                Use template
                            </Button>
                            <Button variant="outlined" onClick={() => onLoadTemplate(template.slug)}>
                                Load in builder
                            </Button>
                            <Button variant="text" onClick={() => onCopyTemplateContract(template)}>
                                Copy markdown
                            </Button>
                        </Stack>
                    </>
                ) : (
                    <Typography color="text.secondary">Select template.</Typography>
                )}
            </Stack>
        </Drawer>
    );
}
