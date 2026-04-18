import { Box, IconButton, Paper, Stack, Tooltip, Typography, type SxProps, type Theme } from "@mui/material";
import { InfoOutlined } from "@mui/icons-material";

type SectionCardProps = {
    title?: React.ReactNode;
    description?: React.ReactNode;
    info?: React.ReactNode;
    action?: React.ReactNode;
    children: React.ReactNode;
    sx?: SxProps<Theme>;
    contentSx?: SxProps<Theme>;
};

export function SectionCard({
    title,
    description,
    info,
    action,
    children,
    sx,
    contentSx,
}: SectionCardProps) {
    const tooltipContent = info ?? description;
    return (
        <Paper
            sx={[
                {
                    p: { xs: 2.5, md: 3 },
                    borderRadius: { xs: 4, md: 5 },
                },
                ...(Array.isArray(sx) ? sx : sx ? [sx] : []),
            ]}
        >
            {(title || action || tooltipContent) && (
                <Stack
                    direction={{ xs: "column", sm: "row" }}
                    justifyContent="space-between"
                    alignItems={{ xs: "flex-start", sm: "center" }}
                    spacing={2}
                    sx={{ mb: 2.5 }}
                >
                    <Box sx={{ minWidth: 0, flex: 1 }}>
                        {title && (
                            <Stack direction="row" alignItems="center" spacing={0.75}>
                                <Typography variant="h5">{title}</Typography>
                                {tooltipContent && (
                                    <Tooltip title={tooltipContent} arrow placement="top">
                                        <IconButton
                                            size="small"
                                            aria-label="Section details"
                                            sx={{ color: "text.secondary", p: 0.25 }}
                                        >
                                            <InfoOutlined sx={{ fontSize: 18 }} />
                                        </IconButton>
                                    </Tooltip>
                                )}
                            </Stack>
                        )}
                    </Box>
                    {action}
                </Stack>
            )}
            <Box
                sx={[
                    ...(Array.isArray(contentSx) ? contentSx : contentSx ? [contentSx] : []),
                ]}
            >
                {children}
            </Box>
        </Paper>
    );
}
