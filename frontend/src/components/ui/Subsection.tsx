import { Box, IconButton, Stack, Tooltip, Typography, type SxProps, type Theme } from "@mui/material";
import { InfoOutlined } from "@mui/icons-material";

type SubsectionProps = {
    title?: React.ReactNode;
    info?: React.ReactNode;
    action?: React.ReactNode;
    children: React.ReactNode;
    sx?: SxProps<Theme>;
    titleVariant?: "subtitle1" | "subtitle2" | "h6";
};

export function Subsection({
    title,
    info,
    action,
    children,
    sx,
    titleVariant = "subtitle1",
}: SubsectionProps) {
    return (
        <Box sx={sx}>
            {(title || action || info) && (
                <Stack
                    direction="row"
                    alignItems="center"
                    justifyContent="space-between"
                    spacing={1}
                    sx={{ mb: 1.5 }}
                >
                    <Stack direction="row" alignItems="center" spacing={0.75} sx={{ minWidth: 0 }}>
                        {title && (
                            <Typography variant={titleVariant} sx={{ fontWeight: 600 }}>
                                {title}
                            </Typography>
                        )}
                        {info && (
                            <Tooltip title={info} arrow placement="top">
                                <IconButton
                                    size="small"
                                    aria-label="Details"
                                    sx={{ color: "text.secondary", p: 0.25 }}
                                >
                                    <InfoOutlined sx={{ fontSize: 16 }} />
                                </IconButton>
                            </Tooltip>
                        )}
                    </Stack>
                    {action}
                </Stack>
            )}
            {children}
        </Box>
    );
}
