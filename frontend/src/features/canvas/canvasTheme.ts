import type { Theme } from "@mui/material/styles";
import { alpha } from "@mui/material/styles";

/** Side-effect: load XYFlow base CSS + Troop canvas overrides once. */
import "./canvas.css";

/**
 * Shared XYFlow / React Flow chrome tokens from the MUI palette.
 * Prefer this over hardcoded slate/blue hex values so dark mode and brand stay aligned.
 */
export function getCanvasTheme(theme: Theme) {
    const isDark = theme.palette.mode === "dark";
    return {
        surfaceBg: alpha(theme.palette.background.default, isDark ? 0.92 : 0.85),
        surfaceBgSoft: alpha(theme.palette.background.default, isDark ? 0.8 : 0.7),
        backgroundDot: theme.palette.divider,
        selectionBorder: theme.palette.primary.main,
        nodeBorder: theme.palette.divider,
        idleStatusDot: theme.palette.grey[400],
        controls: {
            background: theme.palette.background.paper,
            color: theme.palette.text.secondary,
            border: theme.palette.divider,
        },
        miniMap: {
            maskColor: alpha(theme.palette.common.black, isDark ? 0.45 : 0.12),
            nodeColor: theme.palette.primary.main,
        },
    };
}

export type CanvasTheme = ReturnType<typeof getCanvasTheme>;
