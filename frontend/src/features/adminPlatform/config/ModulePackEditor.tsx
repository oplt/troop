import { Box, Stack, Switch, Typography } from "@mui/material";

import type { ModuleCatalogItem } from "../../../api/platform";
import { compactBorderedPanelSx } from "../styles";
import type { ConfigDraft } from "../types";

type ModulePackEditorProps = {
    moduleCatalog: ModuleCatalogItem[];
    configDraft: ConfigDraft;
    onConfigDraftChange: (updater: (current: ConfigDraft) => ConfigDraft) => void;
};

export function ModulePackEditor({
    moduleCatalog,
    configDraft,
    onConfigDraftChange,
}: ModulePackEditorProps) {
    return (
        <Box>
            <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
                Module access
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1.25 }}>
                Off = hidden from nav for everyone on this pack. On = area visible; users still need their role
                permissions to act.
            </Typography>
            <Box
                sx={{
                    display: "grid",
                    gap: 1.25,
                    gridTemplateColumns: { xs: "1fr", md: "repeat(2, minmax(0, 1fr))" },
                }}
            >
                {moduleCatalog.map((moduleItem) => (
                    <Box key={moduleItem.key} sx={compactBorderedPanelSx}>
                        <Stack direction="row" justifyContent="space-between" spacing={1.5}>
                            <Box>
                                <Typography variant="subtitle2">{moduleItem.label}</Typography>
                                <Typography variant="body2" color="text.secondary">
                                    {moduleItem.description}
                                </Typography>
                            </Box>
                            <Switch
                                checked={configDraft.module_states[moduleItem.key] ?? false}
                                onChange={(event) =>
                                    onConfigDraftChange((current) => ({
                                        ...current,
                                        module_states: {
                                            ...current.module_states,
                                            [moduleItem.key]: event.target.checked,
                                        },
                                    }))
                                }
                            />
                        </Stack>
                    </Box>
                ))}
            </Box>
        </Box>
    );
}
