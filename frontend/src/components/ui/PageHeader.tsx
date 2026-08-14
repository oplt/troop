import { Box, Stack, Typography } from "@mui/material";
import type { ReactNode } from "react";

type PageHeaderProps = {
    eyebrow?: ReactNode;
    title: ReactNode;
    description?: ReactNode;
    actions?: ReactNode;
};

export function PageHeader({ eyebrow, title, description, actions }: PageHeaderProps) {
    return (
        <Stack
            direction={{ xs: "column", sm: "row" }}
            spacing={2}
            justifyContent="space-between"
            alignItems={{ xs: "flex-start", sm: "center" }}
            sx={{ mb: 3 }}
        >
            <Box sx={{ minWidth: 0 }}>
                {eyebrow && (
                    <Typography variant="overline" color="text.secondary">
                        {eyebrow}
                    </Typography>
                )}
                <Typography variant="h3" component="h1" sx={{ overflowWrap: "anywhere" }}>
                    {title}
                </Typography>
                {description && (
                    <Typography color="text.secondary" sx={{ mt: 0.75, maxWidth: 760 }}>
                        {description}
                    </Typography>
                )}
            </Box>
            {actions && <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>{actions}</Stack>}
        </Stack>
    );
}
