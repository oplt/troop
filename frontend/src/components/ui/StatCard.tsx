import { Box, Paper, Skeleton, Stack, Tooltip, Typography } from "@mui/material";
import { InfoOutlined } from "@mui/icons-material";
import { alpha, useTheme } from "@mui/material/styles";

type AccentColor = "primary" | "secondary" | "success" | "warning" | "error" | "info";

type StatCardProps = {
    label: string;
    value: React.ReactNode;
    description?: React.ReactNode;
    info?: React.ReactNode;
    icon: React.ReactNode;
    loading?: boolean;
    color?: AccentColor;
};

export function StatCard({
    label,
    value,
    description,
    info,
    icon,
    loading = false,
    color = "primary",
}: StatCardProps) {
    const theme = useTheme();
    const accent = theme.palette[color].main;
    const tooltipContent = info ?? description;

    return (
        <Paper
            sx={{
                position: "relative",
                p: 2.5,
                minHeight: "100%",
                overflow: "hidden",
                backgroundColor: theme.palette.background.paper,
            }}
        >
            <Stack spacing={2}>
                <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={2}>
                    <Stack direction="row" alignItems="center" spacing={0.5} sx={{ minWidth: 0 }}>
                        <Typography
                            variant="caption"
                            sx={{
                                color: "text.secondary",
                                fontWeight: 500,
                            }}
                        >
                            {label}
                        </Typography>
                        {tooltipContent && (
                            <Tooltip title={tooltipContent} placement="top">
                                <InfoOutlined
                                    sx={{ fontSize: 14, color: "text.secondary", cursor: "help" }}
                                    aria-label="Stat details"
                                />
                            </Tooltip>
                        )}
                    </Stack>
                    <Box
                        sx={{
                            width: 40,
                            height: 40,
                            display: "grid",
                            placeItems: "center",
                            borderRadius: 1,
                            color: accent,
                            backgroundColor: alpha(accent, theme.palette.mode === "dark" ? 0.16 : 0.08),
                        }}
                    >
                        {icon}
                    </Box>
                </Stack>
                {loading ? (
                    <Skeleton variant="text" width={120} height={42} />
                ) : (
                    <Typography
                        variant="h4"
                        sx={{ fontWeight: 500, fontVariantNumeric: "tabular-nums", lineHeight: 1.1 }}
                    >
                        {value}
                    </Typography>
                )}
            </Stack>
        </Paper>
    );
}
