import { Box, type SxProps, type Theme } from "@mui/material";

type AnalyticsKpiStripProps = {
    children: React.ReactNode;
    columns?: { xs?: number; sm?: number; md?: number; lg?: number };
    sx?: SxProps<Theme>;
};

/** Consistent KPI / StatCard strip for analytics surfaces. */
export function AnalyticsKpiStrip({
    children,
    columns = { xs: 1, sm: 2, md: 3, lg: 4 },
    sx,
}: AnalyticsKpiStripProps) {
    const xs = columns.xs ?? 1;
    const sm = columns.sm ?? 2;
    const md = columns.md ?? 3;
    const lg = columns.lg ?? 4;
    return (
        <Box
            sx={[
                {
                    display: "grid",
                    gap: 2,
                    gridTemplateColumns: {
                        xs: `repeat(${xs}, minmax(0, 1fr))`,
                        sm: `repeat(${sm}, minmax(0, 1fr))`,
                        md: `repeat(${md}, minmax(0, 1fr))`,
                        lg: `repeat(${lg}, minmax(0, 1fr))`,
                    },
                },
                ...(Array.isArray(sx) ? sx : sx ? [sx] : []),
            ]}
        >
            {children}
        </Box>
    );
}
