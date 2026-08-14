import { useCallback, useState, type ReactNode } from "react";
import { Box, Button, Chip, IconButton, Stack, Tooltip, Typography, type SxProps, type Theme } from "@mui/material";
import {
    CenterFocusStrong as FitIcon,
    Map as MiniMapIcon,
    WarningAmber as ValidationIcon,
} from "@mui/icons-material";
import { useReactFlow, useStore } from "@xyflow/react";
import { KeyboardShortcutsMenu } from "../ui/KeyboardShortcutsMenu";

type CanvasChromeProps = {
    children: ReactNode | ((ctx: { showMiniMap: boolean }) => ReactNode);
    /** Show unsaved pill when the graph has local edits. */
    dirty?: boolean;
    /** Client validation issue count (0 hides the chip). */
    validationCount?: number;
    /** Controlled MiniMap visibility. Default true. */
    showMiniMap?: boolean;
    onShowMiniMapChange?: (next: boolean) => void;
    /** Optional trailing actions (Save, Validate, etc.). */
    actions?: ReactNode;
    height?: number | string | Record<string, number | string>;
    sx?: SxProps<Theme>;
    "aria-label"?: string;
};

function prefersReducedMotion() {
    if (typeof window === "undefined" || !window.matchMedia) return false;
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function ZoomLabel() {
    const zoom = useStore((state) => state.transform[2]);
    const percent = Math.round((zoom || 1) * 100);
    return (
        <Chip
            size="small"
            variant="outlined"
            label={`${percent}%`}
            sx={{ fontVariantNumeric: "tabular-nums" }}
        />
    );
}

function FitControl() {
    const { fitView } = useReactFlow();
    return (
        <Button
            size="small"
            variant="outlined"
            startIcon={<FitIcon fontSize="small" />}
            onClick={() =>
                fitView({
                    padding: 0.18,
                    duration: prefersReducedMotion() ? 0 : 240,
                })
            }
        >
            Fit
        </Button>
    );
}

/**
 * Presentational toolbar + surface frame for XYFlow builders.
 * Must render under ReactFlowProvider (toolbar uses useReactFlow / useStore).
 */
export function CanvasChrome({
    children,
    dirty = false,
    validationCount = 0,
    showMiniMap: showMiniMapProp,
    onShowMiniMapChange,
    actions,
    height = { xs: 520, xl: 680 },
    sx,
    "aria-label": ariaLabel = "Graph canvas",
}: CanvasChromeProps) {
    const [internalMiniMap, setInternalMiniMap] = useState(true);
    const showMiniMap = showMiniMapProp ?? internalMiniMap;
    const setShowMiniMap = onShowMiniMapChange ?? setInternalMiniMap;

    const toggleMiniMap = useCallback(() => {
        setShowMiniMap(!showMiniMap);
    }, [setShowMiniMap, showMiniMap]);

    return (
        <Stack spacing={1} sx={sx}>
            <Stack
                direction="row"
                spacing={1}
                alignItems="center"
                flexWrap="wrap"
                useFlexGap
                sx={{
                    px: 1,
                    py: 0.75,
                    border: "1px solid",
                    borderColor: "divider",
                    borderRadius: 1,
                    bgcolor: "background.paper",
                }}
            >
                <Typography variant="caption" color="text.secondary" sx={{ mr: 0.5 }}>
                    Canvas
                </Typography>
                <ZoomLabel />
                <FitControl />
                <Tooltip title={showMiniMap ? "Hide minimap" : "Show minimap"}>
                    <IconButton
                        size="small"
                        aria-pressed={showMiniMap}
                        aria-label="Toggle minimap"
                        onClick={toggleMiniMap}
                        color={showMiniMap ? "primary" : "default"}
                    >
                        <MiniMapIcon fontSize="small" />
                    </IconButton>
                </Tooltip>
                <KeyboardShortcutsMenu
                    title="Canvas shortcuts"
                    shortcuts={[
                        { keys: "Delete / Backspace", label: "Remove selected nodes or edges" },
                        { keys: "Fit", label: "Fit graph in view" },
                        { keys: "Scroll / pinch", label: "Zoom" },
                        { keys: "Drag pane", label: "Pan" },
                    ]}
                />
                {dirty ? <Chip size="small" color="warning" label="Unsaved" /> : null}
                {validationCount > 0 ? (
                    <Chip
                        size="small"
                        color="error"
                        variant="outlined"
                        icon={<ValidationIcon />}
                        label={`${validationCount} issue${validationCount === 1 ? "" : "s"}`}
                    />
                ) : null}
                <Box sx={{ flex: 1 }} />
                {actions}
            </Stack>
            <Box
                aria-label={ariaLabel}
                sx={{
                    position: "relative",
                    height,
                    borderRadius: 1,
                    overflow: "hidden",
                    border: "1px solid",
                    borderColor: "divider",
                }}
                data-show-minimap={showMiniMap ? "true" : "false"}
            >
                {typeof children === "function" ? children({ showMiniMap }) : children}
            </Box>
        </Stack>
    );
}
