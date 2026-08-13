import { Box, type SxProps, type Theme } from "@mui/material";

type InspectorSplitProps = {
    primary: React.ReactNode;
    secondary?: React.ReactNode;
    /** Secondary column width on desktop. Default 360. */
    secondaryWidth?: number | string;
    /** Hide secondary below md (mobile list-first). Default true. */
    hideSecondaryOnMobile?: boolean;
    sx?: SxProps<Theme>;
};

/**
 * Fluid primary + optional side inspector for tool pages.
 */
export function InspectorSplit({
    primary,
    secondary,
    secondaryWidth = 360,
    hideSecondaryOnMobile = true,
    sx,
}: InspectorSplitProps) {
    return (
        <Box
            sx={[
                {
                    display: "grid",
                    gap: 2,
                    alignItems: "start",
                    gridTemplateColumns: {
                        xs: "1fr",
                        md: secondary
                            ? `minmax(0, 1fr) ${typeof secondaryWidth === "number" ? `${secondaryWidth}px` : secondaryWidth}`
                            : "1fr",
                    },
                },
                ...(Array.isArray(sx) ? sx : sx ? [sx] : []),
            ]}
        >
            <Box sx={{ minWidth: 0 }}>{primary}</Box>
            {secondary ? (
                <Box
                    sx={{
                        minWidth: 0,
                        display: hideSecondaryOnMobile ? { xs: "none", md: "block" } : "block",
                    }}
                >
                    {secondary}
                </Box>
            ) : null}
        </Box>
    );
}
