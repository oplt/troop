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
                borderRadius: 3,
                minHeight: "100%",
                overflow: "hidden",
                background: `linear-gradient(180deg, ${alpha(accent, theme.palette.mode === "dark" ? 0.14 : 0.06)} 0%, ${alpha(
                    theme.palette.background.paper,
                    0.96
                )} 100%)`,
                "&::before": {
                    content: '""',
                    position: "absolute",
                    top: 0,
                    left: 0,
                    width: 3,
                    height: "100%",
                    backgroundColor: accent,
                    opacity: 0.9,
                },
            }}
        >
            <Stack spacing={2}>
                <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={2}>
                    <Stack direction="row" alignItems="center" spacing={0.5} sx={{ minWidth: 0 }}>
                        <Typography
                            variant="caption"
                            sx={{
                                color: "text.secondary",
                                textTransform: "uppercase",
                                letterSpacing: "0.08em",
                                fontWeight: 600,
                                fontSize: "0.7rem",
                            }}
                        >
                            {label}
                        </Typography>
                        {tooltipContent && (
                            <Tooltip title={tooltipContent} arrow placement="top">
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
                            borderRadius: 2,
                            color: accent,
                            backgroundColor: alpha(accent, theme.palette.mode === "dark" ? 0.22 : 0.14),
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
                        sx={{ fontWeight: 700, fontVariantNumeric: "tabular-nums", lineHeight: 1.1 }}
                    >
                        {value}
                    </Typography>
                )}
            </Stack>
        </Paper>
    );
}
