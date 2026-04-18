import { Box, IconButton, Stack, Tooltip, Typography } from "@mui/material";
import { InfoOutlined } from "@mui/icons-material";
import { alpha } from "@mui/material/styles";

type PageHeaderProps = {
    eyebrow?: string;
    title: React.ReactNode;
    description?: React.ReactNode;
    info?: React.ReactNode;
    actions?: React.ReactNode;
    meta?: React.ReactNode;
};

export function PageHeader({ eyebrow, title, description, info, actions, meta }: PageHeaderProps) {
    const tooltipContent = info ?? description;
    return (
        <Box
            sx={(theme) => ({
                position: "relative",
                overflow: "hidden",
                borderRadius: { xs: 4, md: 5 },
                border: `1px solid ${theme.palette.divider}`,
                px: { xs: 2.5, md: 4 },
                py: { xs: 3, md: 4 },
                background:
                    theme.palette.mode === "dark"
                        ? `linear-gradient(135deg, ${alpha(theme.palette.primary.main, 0.05)} 0%, ${alpha(
                              theme.palette.background.paper,
                              0.98
                          )} 50%, ${alpha(theme.palette.secondary.main, 0.04)} 100%)`
                        : `linear-gradient(135deg, ${alpha(theme.palette.primary.main, 0.025)} 0%, ${alpha(
                              theme.palette.background.paper,
                              1
                          )} 50%, ${alpha(theme.palette.secondary.main, 0.02)} 100%)`,
                boxShadow:
                    theme.palette.mode === "dark"
                        ? "0 1px 2px rgba(0, 0, 0, 0.4), 0 12px 32px rgba(2, 6, 23, 0.35)"
                        : "0 1px 2px rgba(15, 23, 42, 0.04), 0 12px 28px rgba(15, 23, 42, 0.06)",
                "&::before": {
                    content: '""',
                    position: "absolute",
                    inset: 0,
                    pointerEvents: "none",
                    backgroundImage: `radial-gradient(circle at 1px 1px, ${alpha(
                        theme.palette.text.primary,
                        theme.palette.mode === "dark" ? 0.04 : 0.025
                    )} 1px, transparent 0)`,
                    backgroundSize: "24px 24px",
                    opacity: 0.6,
                },
            })}
        >
            <Stack
                direction={{ xs: "column", lg: actions ? "row" : "column" }}
                justifyContent="space-between"
                alignItems={{ xs: "flex-start", lg: "flex-end" }}
                spacing={3}
                sx={{ position: "relative", zIndex: 1 }}
            >
                <Box sx={{ maxWidth: 760 }}>
                    {eyebrow && (
                        <Typography
                            variant="caption"
                            sx={(theme) => ({
                                display: "inline-block",
                                mb: 1.5,
                                px: 1.25,
                                py: 0.5,
                                borderRadius: 1,
                                color: theme.palette.primary.main,
                                backgroundColor: alpha(theme.palette.primary.main, theme.palette.mode === "dark" ? 0.12 : 0.08),
                                textTransform: "uppercase",
                                letterSpacing: "0.1em",
                                fontWeight: 600,
                                fontSize: "0.7rem",
                            })}
                        >
                            {eyebrow}
                        </Typography>
                    )}
                    <Stack direction="row" alignItems="center" spacing={1}>
                        <Typography variant="h3" sx={{ fontWeight: 700, letterSpacing: "-0.02em" }}>
                            {title}
                        </Typography>
                        {tooltipContent && (
                            <Tooltip title={tooltipContent} arrow placement="bottom-start">
                                <IconButton
                                    size="small"
                                    aria-label="Page details"
                                    sx={{ color: "text.secondary" }}
                                >
                                    <InfoOutlined sx={{ fontSize: 20 }} />
                                </IconButton>
                            </Tooltip>
                        )}
                    </Stack>
                    {meta && (
                        <Stack direction="row" flexWrap="wrap" gap={1.25} sx={{ mt: 2.5 }}>
                            {meta}
                        </Stack>
                    )}
                </Box>
                {actions && (
                    <Stack direction={{ xs: "column", sm: "row" }} spacing={1.25} sx={{ width: { xs: "100%", lg: "auto" } }}>
                        {actions}
                    </Stack>
                )}
            </Stack>
        </Box>
    );
}
