import type { Theme } from "@mui/material/styles";

export const borderedPanelSx = (theme: Theme) => ({
    p: 2,
    borderRadius: 4,
    border: `1px solid ${theme.palette.divider}`,
});

export const compactDocumentRowSx = (theme: Theme) => ({
    p: 1.5,
    borderRadius: 1,
    border: `1px solid ${theme.palette.divider}`,
});
