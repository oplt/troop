import type { Theme } from "@mui/material/styles";

export const borderedPanelSx = (theme: Theme) => ({
    p: 2.5,
    borderRadius: 4,
    border: `1px solid ${theme.palette.divider}`,
});

export const compactBorderedPanelSx = (theme: Theme) => ({
    p: 2,
    borderRadius: 4,
    border: `1px solid ${theme.palette.divider}`,
});
