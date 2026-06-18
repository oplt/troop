import { Box, Stack, Typography } from "@mui/material";
import { alpha } from "@mui/material/styles";

type EmptyStateProps = {
    icon: React.ReactNode;
    title: string;
    description: string;
    action?: React.ReactNode;
};

export function EmptyState({ icon, title, description, action }: EmptyStateProps) {
    return (
        <Box
            role="status"
            sx={(theme) => ({
                border: `1px dashed ${alpha(theme.palette.text.primary, theme.palette.mode === "dark" ? 0.14 : 0.12)}`,
                borderRadius: 1,
                px: 3,
                py: 4,
                textAlign: "center",
                backgroundColor: theme.palette.mode === "dark"
                    ? alpha(theme.palette.background.paper, 0.5)
                    : theme.palette.grey[50],
            })}
        >
            <Stack spacing={1.5} alignItems="center">
                <Box
                    sx={(theme) => ({
                        width: 52,
                        height: 52,
                        borderRadius: 1,
                        display: "grid",
                        placeItems: "center",
                        color: "primary.main",
                        backgroundColor: alpha(theme.palette.primary.main, theme.palette.mode === "dark" ? 0.14 : 0.08),
                    })}
                >
                    {icon}
                </Box>
                <Typography variant="h6">{title}</Typography>
                <Typography color="text.secondary" sx={{ maxWidth: 460 }}>
                    {description}
                </Typography>
                {action && (
                    <Box sx={{ pt: 0.5 }}>
                        {action}
                    </Box>
                )}
            </Stack>
        </Box>
    );
}
