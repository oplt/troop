import type { Theme } from "@mui/material/styles";
import { alpha } from "@mui/material/styles";

export const settingsShellSx = (theme: Theme) => ({
    display: "flex",
    gap: 2,
    alignItems: "start",
    border: `1px solid ${theme.palette.divider}`,
    borderRadius: 4,
    backgroundColor: alpha(theme.palette.background.paper, 0.82),
    overflow: "hidden",
});

export const settingsTabsSx = (theme: Theme) => ({
    minWidth: 200,
    borderRight: `1px solid ${theme.palette.divider}`,
    flexShrink: 0,
    "& .MuiTab-root": {
        alignItems: "flex-start",
        textAlign: "left",
        px: 2.5,
        py: 1.5,
    },
});

export const databaseEditorSx = (theme: Theme) => ({
    p: 2.25,
    borderRadius: 4,
    border: `1px solid ${theme.palette.divider}`,
});
